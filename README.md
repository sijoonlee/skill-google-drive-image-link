# google-drive-image-link

Uploads a local image to Google Drive and returns a direct image link, `https://lh3.googleusercontent.com/d/<ID>`, that renders inline in Markdown, GitHub and Slack.

## Size limit

**Images can be up to 7,000 KB (about 7 MB).** The Google Drive connector rejects any request over 10,000,000 bytes, and the file is sent as base64, which is 4/3 its size.

| Image | Over 7,000 KB |
| --- | --- |
| PNG, JPEG or WebP | shrunk to a JPEG with `sips` until it fits |
| GIF | refused, because shrinking would drop the animation. Make it smaller, for example with fewer frames or a smaller size, or upload it to Drive by hand. |

Tested on 2026-11-26: a 6.8 MB animated GIF uploaded, and its image link showed it animated. A 10.45 MB GIF was refused by the connector with HTTP 400.

Google re-encodes what the image link serves. The 6.8 MB GIF came out at about 1.5 MB, with all its frames.

## Requirements

**The agent must have the Google Drive connector.** The skill doesn't work without it.

The upload, the sharing and the folder lookup are calls to the connector's tools (`search_files`, `create_file` and `share_file`), made by the agent. The script in `scripts/` can't upload on its own: it has no Google sign-in, and a script can't call a connector's tools. In Claude Code, the connector comes from your claude.ai account:

1. Connect Google Drive in claude.ai's connector settings.
2. Sign Claude Code in with the same claude.ai account.
3. In a new session, check that the Google Drive tools are listed, for example with `/mcp`.

If the agent doesn't have the connector, the skill stops at the upload step and says so.

Your Google Workspace must also allow sharing a file with anyone who has the link. If it doesn't, the share step fails.

On your computer, the skill needs:

| What | Why |
| --- | --- |
| Python 3.7 or newer | runs `scripts/google_drive_image_link.py`, which uses only the standard library |
| `sips` (comes with macOS) | shrinks a PNG, JPEG or WebP over the 7,000 KB cap; without it, larger images fail. GIFs are never shrunk, so their animation is kept |
| Internet access to `drive.google.com` | the verify step downloads the uploaded file without signing in |

It doesn't need a Google Cloud project, OAuth client, API key, `gcloud` or any Python packages.

## How the work is split

| Step | Done by |
| --- | --- |
| Check and shrink the image, and print a file reference to it | script (`prepare`) |
| Find or create the `google-drive-image-link` folder in My Drive | agent, through the connector |
| Upload the image to that folder | agent, through the connector |
| Share it with anyone who has the link | agent, through the connector |
| Download it without signing in and compare it with the local file | script (`verify`) |
| Print the image link and the Drive viewer link | script (`link`) |

The agent passes `create_file` a file reference, `sha256:<hash>:<absolute path>`, and the app fills in the file's bytes when the call runs. The image never passes through the agent's context, so a large GIF uploads as easily as a small screenshot. The connector still limits each request to 10,000,000 bytes, and the file is sent as base64, which is 4/3 its size. So the largest file it can upload is about 7 MB, and the skill caps files at 7,000 KB. Upload a larger file to Drive by hand. The verify step checks that the bytes on Drive match the local file, and that the link works without signing in.

## Tests

From `scripts/`, run `python3 -m unittest test_google_drive_image_link`. The tests don't call Google.
