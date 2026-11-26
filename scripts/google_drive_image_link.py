#!/usr/bin/env python3
"""Local half of the google-drive-image-link skill.

The upload and the sharing happen through the Google Drive connector, which a
script can't call. This script does the parts around those two calls:

  prepare <image>        check the file, shrink a PNG, JPEG or WebP with sips when
                         it is over the size cap, and print what create_file needs
                         as JSON, with a file reference instead of the bytes
  verify <id> <file>     download the shared file without signing in and check
                         it matches the prepared file byte for byte
  link <id>              print the direct image link and the Drive viewer link
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

MIME_BY_MAGIC = [
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
]
EXTENSION_BY_MIME = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}
SHRINK_WIDTHS = [2400, 2000, 1600, 1280, 1024, 800]
# The connector rejects requests over 10,000,000 bytes, and the file goes in as base64 (4/3 the size).
DEFAULT_MAX_KB = 7000
FILE_ID = re.compile(r"^[A-Za-z0-9_-]{10,}$")


class Failure(Exception):
    pass


def sniff_mime(data):
    for magic, mime in MIME_BY_MAGIC:
        if data.startswith(magic):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def shrink(path, max_bytes):
    """Re-encode as JPEG at falling widths until the file fits under max_bytes."""
    if shutil.which("sips") is None:
        raise Failure("the image is over the size cap and sips (macOS) isn't available to shrink it")
    out_dir = tempfile.mkdtemp(prefix="google-drive-image-link-")
    stem = os.path.splitext(os.path.basename(path))[0]
    out = os.path.join(out_dir, stem + ".jpg")
    for width in SHRINK_WIDTHS:
        # sips -Z caps the longer side and never enlarges a smaller image.
        result = subprocess.run(
            ["sips", "-s", "format", "jpeg", "-s", "formatOptions", "80", "-Z", str(width), path, "--out", out],
            capture_output=True, text=True)
        if result.returncode != 0:
            raise Failure("sips couldn't convert the image: " + (result.stderr.strip() or result.stdout.strip()))
        if os.path.getsize(out) <= max_bytes:
            return out
    raise Failure("still {} KB after shrinking to {} px wide; raise --max-kb or crop the image".format(
        os.path.getsize(out) // 1024, SHRINK_WIDTHS[-1]))


def prepare(path, max_kb, no_shrink):
    if not os.path.isfile(path):
        raise Failure("no file at " + path)
    with open(path, "rb") as handle:
        data = handle.read()
    mime = sniff_mime(data)
    if mime is None:
        raise Failure("not a PNG, JPEG, GIF or WebP image: " + path)
    max_bytes = max_kb * 1024
    upload_path, shrunk = path, False
    if len(data) > max_bytes:
        if mime == "image/gif":
            raise Failure("{} KB is over the {} KB cap. GIFs aren't shrunk, because re-encoding drops the "
                          "animation. Make the GIF smaller, for example with fewer frames or a smaller size, "
                          "or upload it to Drive by hand".format(len(data) // 1024, max_kb))
        if no_shrink:
            raise Failure("{} KB is over the {} KB cap; drop --no-shrink or raise --max-kb".format(
                len(data) // 1024, max_kb))
        upload_path, shrunk = shrink(path, max_bytes), True
        with open(upload_path, "rb") as handle:
            data = handle.read()
        mime = "image/jpeg"
    title = os.path.basename(path)
    if shrunk:
        title = os.path.splitext(title)[0] + EXTENSION_BY_MIME[mime]
    upload_path = os.path.abspath(upload_path)
    sha256 = hashlib.sha256(data).hexdigest()
    return {
        "title": title,
        "contentMimeType": mime,
        "uploadPath": upload_path,
        "bytes": len(data),
        "shrunk": shrunk,
        "originalBytes": os.path.getsize(path),
        "sha256": sha256,
        # create_file reads the bytes from this reference, so they never pass through the agent's context.
        "fileRef": "sha256:{}:{}".format(sha256, upload_path),
    }


def check_id(file_id):
    if not FILE_ID.match(file_id):
        raise Failure("doesn't look like a Drive file ID: " + file_id)


def links(file_id):
    check_id(file_id)
    return {
        "imageLink": "https://lh3.googleusercontent.com/d/" + file_id,
        "viewerLink": "https://drive.google.com/file/d/{}/view".format(file_id),
    }


def verify(file_id, path):
    check_id(file_id)
    with open(path, "rb") as handle:
        expected = hashlib.md5(handle.read()).hexdigest()
    url = "https://drive.google.com/uc?export=download&id=" + file_id
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            body = response.read()
            content_type = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as error:
        raise Failure("download without sign-in failed with HTTP {}; is the file shared with anyone with the link?".format(
            error.code))
    if not content_type.startswith("image/"):
        raise Failure("download returned {} instead of an image; the file may not be shared publicly".format(
            content_type or "no content type"))
    actual = hashlib.md5(body).hexdigest()
    if actual != expected:
        raise Failure("the uploaded file differs from {} (md5 {} vs {}); the base64 was likely copied wrong, so "
                      "trash the upload and try again".format(path, actual, expected))
    return {"ok": True, "md5": actual, "bytes": len(body)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare", help="check and shrink an image, print create_file arguments as JSON")
    p.add_argument("image")
    p.add_argument("--max-kb", type=int, default=DEFAULT_MAX_KB,
                   help="largest file to upload, in KB (default {})".format(DEFAULT_MAX_KB))
    p.add_argument("--no-shrink", action="store_true", help="fail instead of shrinking an image over the cap")
    v = sub.add_parser("verify", help="check the shared upload matches the prepared file")
    v.add_argument("file_id")
    v.add_argument("upload_path")
    l = sub.add_parser("link", help="print the direct image link and the viewer link")
    l.add_argument("file_id")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare(args.image, args.max_kb, args.no_shrink)
        elif args.command == "verify":
            result = verify(args.file_id, args.upload_path)
        else:
            result = links(args.file_id)
    except Failure as error:
        print("error: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
