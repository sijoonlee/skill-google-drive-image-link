---
name: google-drive-image-link
description: Upload a local image file to Google Drive through the Google Drive connector, share it with anyone who has the link, and return a direct image link (https://lh3.googleusercontent.com/d/<ID>) that renders inline in Markdown, GitHub and Slack. Files can be up to 7,000 KB (about 7 MB); a GIF stays animated. Use when asked to upload an image or screenshot to Drive, or to get a shareable or embeddable link for a local image.
---

# Google Drive image link

Input: a local path to a PNG, JPEG, GIF or WebP file. Optional: a Drive folder ID to upload into instead of the default folder.

**Size limit: 7,000 KB (about 7 MB).** The connector rejects any request over 10,000,000 bytes, and the file is sent as base64, which is 4/3 its size. A PNG, JPEG or WebP over the limit is shrunk to a JPEG. A GIF over the limit is refused, because shrinking would drop its animation. If the user names a file over the limit, tell them before step 1: they can make it smaller, such as a GIF with fewer frames or a smaller size, or upload it to Drive by hand.

Uploads go to a folder named `google-drive-image-link` at the top level of My Drive, unless the user gives another folder ID.

`scripts/google_drive_image_link.py` does the local work. The upload and the sharing go through the Google Drive connector tools `create_file` and `share_file`. If those tools aren't available, stop and say the Google Drive connector needs to be connected.

## Steps

1. **Prepare.** Run:

   ```
   python3 <this skill>/scripts/google_drive_image_link.py prepare <image path>
   ```

   It prints JSON with `title`, `contentMimeType`, `uploadPath`, `bytes`, `shrunk`, `sha256` and `fileRef`. `fileRef` is a file reference, `sha256:<hash>:<absolute path>`, that `create_file` reads the bytes from, so the image never passes through your context.

   The size cap is 7,000 KB. The connector rejects any request over 10,000,000 bytes, and the file goes in as base64, which is 4/3 its size. Don't raise the cap past that. A PNG, JPEG or WebP over the cap is re-encoded as JPEG and scaled down with `sips` until it fits; `shrunk` is then true. A GIF over the cap is never shrunk, because re-encoding drops its animation: the command fails instead. Pass `--max-kb <n>` to lower the cap, or `--no-shrink` to fail instead of shrinking. If the command fails, report its error and stop.

2. **Find the folder.** Skip this step if the user gave a folder ID. Otherwise call `search_files` with the query `title = 'google-drive-image-link' and mimeType = 'application/vnd.google-apps.folder' and parentId = 'root' and owner = 'me'`, and use the first result's `id`. If there's no result, create the folder with `create_file`, setting `title: "google-drive-image-link"` and `contentMimeType: "application/vnd.google-apps.folder"`, and use its `id`.

3. **Upload.** Call `create_file` with:
   - `title`: the JSON's `title`
   - `contentMimeType`: the JSON's `contentMimeType`
   - `base64Content`: the JSON's `fileRef`, copied exactly. Never put the image's base64 text here.
   - `disableConversionToGoogleType`: `true`
   - `parentId`: the folder ID from step 2

   Keep the `id` from the result.

4. **Share.** Call `share_file` with `fileId` set to that `id`, `permissionId: "anyoneWithLink"` and `role: "reader"`.

5. **Verify.** Run `google_drive_image_link.py verify <id> <uploadPath>`. It downloads the file without signing in and compares it with the prepared file. If it fails, report the error. When it says the files differ, trash the upload with `trash_file`, run step 1 again, and start again from step 3.

6. **Link.** Run `google_drive_image_link.py link <id>` and give the user both links:
   - `imageLink` (`https://lh3.googleusercontent.com/d/<id>`): the image itself, for Markdown `![](...)`, GitHub and Slack
   - `viewerLink`: the Drive viewer page, as a fallback

   Say whether the image was shrunk, with its original and uploaded sizes.

## Things to know

- Anyone with either link can see the image. Don't upload anything the user hasn't said can be public.
- The lh3 link format isn't documented by Google. It has worked for years, but if it stops rendering, the viewer link still works.
- The lh3 link serves a copy that Google re-encodes. An animated GIF keeps its frames but can come out much smaller, so its bytes won't match the upload. The verify step checks the Drive download, not the lh3 link.
