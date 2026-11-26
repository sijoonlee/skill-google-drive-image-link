import hashlib
import os
import shutil
import struct
import tempfile
import unittest
import zlib

import google_drive_image_link as d


def write_png(path, width, height, noisy=False):
    rows = b""
    seed = 1
    for y in range(height):
        row = bytearray(b"\x00")
        for x in range(width):
            if noisy:
                seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
                row += bytes([seed & 255, (seed >> 8) & 255, (seed >> 16) & 255])
            else:
                row += bytes([x % 256, y % 256, 160])
        rows += bytes(row)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))
    with open(path, "wb") as handle:
        handle.write(png)


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_small_png_is_passed_through(self):
        path = os.path.join(self.dir, "shot.png")
        write_png(path, 40, 20)
        result = d.prepare(path, 300, False)
        self.assertEqual(result["title"], "shot.png")
        self.assertEqual(result["contentMimeType"], "image/png")
        self.assertFalse(result["shrunk"])
        with open(path, "rb") as handle:
            digest = hashlib.sha256(handle.read()).hexdigest()
        self.assertEqual(result["sha256"], digest)
        self.assertEqual(result["fileRef"], "sha256:{}:{}".format(digest, os.path.abspath(path)))
        self.assertNotIn("base64Content", result)

    def test_gif_over_cap_is_never_shrunk(self):
        path = os.path.join(self.dir, "anim.gif")
        with open(path, "wb") as handle:
            handle.write(b"GIF89a" + b"\x00" * 20000)
        with self.assertRaises(d.Failure) as caught:
            d.prepare(path, 10, False)
        self.assertIn("animation", str(caught.exception))

    def test_gif_under_cap_is_passed_through(self):
        path = os.path.join(self.dir, "anim.gif")
        with open(path, "wb") as handle:
            handle.write(b"GIF89a" + b"\x00" * 20000)
        result = d.prepare(path, 100, False)
        self.assertEqual(result["contentMimeType"], "image/gif")
        self.assertFalse(result["shrunk"])

    def test_non_image_is_rejected(self):
        path = os.path.join(self.dir, "notes.png")
        with open(path, "w") as handle:
            handle.write("hello")
        with self.assertRaises(d.Failure):
            d.prepare(path, 300, False)

    def test_missing_file_is_rejected(self):
        with self.assertRaises(d.Failure):
            d.prepare(os.path.join(self.dir, "nope.png"), 300, False)

    def test_over_cap_with_no_shrink_fails(self):
        path = os.path.join(self.dir, "big.png")
        write_png(path, 300, 300, noisy=True)
        with self.assertRaises(d.Failure):
            d.prepare(path, 10, True)

    @unittest.skipUnless(shutil.which("sips"), "sips is macOS only")
    def test_over_cap_is_shrunk_to_jpeg(self):
        path = os.path.join(self.dir, "big.png")
        write_png(path, 3000, 1000, noisy=True)
        result = d.prepare(path, 300, False)
        self.assertTrue(result["shrunk"])
        self.assertEqual(result["title"], "big.jpg")
        self.assertEqual(result["contentMimeType"], "image/jpeg")
        self.assertLessEqual(result["bytes"], 300 * 1024)
        self.assertGreater(result["originalBytes"], 300 * 1024)


class LinkTests(unittest.TestCase):
    def test_links(self):
        result = d.links("17sV5qZNhbXxnkYynAzc04gW8PWW-iLxj")
        self.assertEqual(result["imageLink"], "https://lh3.googleusercontent.com/d/17sV5qZNhbXxnkYynAzc04gW8PWW-iLxj")
        self.assertTrue(result["viewerLink"].startswith("https://drive.google.com/file/d/"))

    def test_bad_id_is_rejected(self):
        with self.assertRaises(d.Failure):
            d.links("../etc")


if __name__ == "__main__":
    unittest.main()
