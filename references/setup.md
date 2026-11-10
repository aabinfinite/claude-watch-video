# Prerequisites

Read when a run reports a missing dependency (exit 3, or a `warnings` entry naming ffmpeg, faster-whisper, yt-dlp, Pillow or Tesseract), or a URL that needs a login (exit 4 with `login_required`).

## Python packages: automatic

`watch_video.py` runs under any Python. When the interpreter that starts it lacks `yt_dlp` or `faster_whisper`, it:

1. creates `~/.watch-video/venv` with the first `python3.14` .. `python3.10` on PATH (`py -3.x` on Windows);
2. with none of those (e.g. only Python 3.15, whose PyAV wheels don't exist yet, or only macOS's 3.9), installs `uv` into `~/.watch-video/tools` and lets it download a managed Python 3.12 for the venv;
3. installs yt-dlp, faster-whisper, `av<19`, Pillow, imagehash and python-docx there, and re-runs the same command inside it.

Nothing goes into the user's own Python. Inside that venv, yt-dlp is upgraded when the last install is over 7 days old, because site extractors (Instagram, TikTok, X) break often. To repair a broken environment, delete `~/.watch-video/venv` and re-run. Set `WATCH_VIDEO_NO_BOOTSTRAP=1` to turn all of this off and manage packages yourself (below).

ffmpeg and Tesseract are system programs and still have to be installed by hand.

## Sites that need a login

Instagram, X, some TikTok and Facebook posts, and private, members-only or age-gated YouTube videos are only served to a logged-in session. Every URL is first fetched anonymously; when the site refuses, the run retries with login cookies if a source is configured, and otherwise exits 4 with `login_required: true` and instructions.

Cookie source, first match wins:

| Where | Example |
|---|---|
| `--cookies-from-browser BROWSER[:PROFILE]` | `--cookies-from-browser chrome`, `firefox`, `safari`, `edge`, `brave`, `chrome:Profile 1` |
| `--cookies FILE` | a Netscape `cookies.txt` exported from the browser |
| env `WATCH_VIDEO_COOKIES_FROM_BROWSER` / `WATCH_VIDEO_COOKIES` | `export WATCH_VIDEO_COOKIES_FROM_BROWSER=chrome` |
| `~/.watch-video/config.json` | `{"cookies_from_browser": "chrome"}` or `{"cookies": "~/cookies.txt"}` |

The user must be logged in to the site in that browser. On macOS, Chrome-family browsers ask for Keychain access the first time; Safari needs Full Disk Access for the terminal app. Firefox or a `cookies.txt` file avoids both. `meta.json` records `video.used_login_cookies`.

## Prereqs (manual, with `WATCH_VIDEO_NO_BOOTSTRAP=1`)

- **ffmpeg** on PATH: `sudo apt install ffmpeg` (Debian/Ubuntu; `dnf`/`pacman` equivalent) or `brew install ffmpeg`. Windows: `winget install Gyan.FFmpeg`.
- **Python 3.10+** as `python3`. (Windows: `py`; `python` there is often the Microsoft Store alias.)
- **All Python deps with tested pins in one go:** `python3 -m pip install -e "${CLAUDE_SKILL_DIR}/mcp-server[full]"` (use a virtualenv on distros that block `pip --user`). Or pick per feature:
- **faster-whisper**: `python3 -m pip install --user faster-whisper 'av<19'` (PyAV 19 breaks faster-whisper 1.2.x with `TypeError: ... 'metadata_errors'`)
- **yt-dlp**: `python3 -m pip install --user yt-dlp` (for URL mode)
- **Pillow + imagehash**: `python3 -m pip install --user Pillow imagehash` (for `--dedup`)
- **Tesseract + pytesseract** (for `--ocr`):
  - Linux: `sudo apt install tesseract-ocr` (or `dnf`/`pacman` equivalent)
  - macOS: `brew install tesseract`
  - Windows: `winget install UB-Mannheim.TesseractOCR`
  - Plus: `python3 -m pip install --user pytesseract Pillow`
  - Non-English languages: install the matching tessdata pack (Linux: `sudo apt install tesseract-ocr-<code>`; Windows: rerun installer with language options)

First whisper run downloads the model (~250 MB for `small`/`small.en`) to `~/.cache/huggingface/hub/`. Cached after that.
