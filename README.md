# claude-media-watcher

Gives Claude Code a way to "watch" a video and "listen" to audio that **you hand it**. A small script turns one media file (or a share link) into timestamped frames, contact sheets and a transcript, and a skill file tells Claude to use it when you give it a video or audio file.

Works on Mac and Windows. Everything runs locally. No file leaves the machine.

## Who made this, and what it does and does not do

- **Author:** Fatima Arshad (Bambora, bamboraco.com), for the Bambora creative team. This is a personal GitHub account. It is **not** an Anthropic project and not affiliated with Anthropic; "claude" in the name only means "for Claude Code".
- **"Watcher" means it watches videos you give it.** It does **not** monitor your filesystem, run in the background, start on login, or touch your camera, microphone or screen. It only ever reads the single file or link you pass on the command line, and writes its output to a `<file>_watch/` folder next to it.
- **No network service, no telemetry, no API keys, no MCP server.** The only downloads are the ones listed below (ffmpeg, yt-dlp, Python packages from PyPI, the Whisper speech model from Hugging Face), plus the video itself when you give it a link.
- **Everything is readable:** `watch.py` (the tool, plain Python), `install.sh` (Mac/Linux) and `install.ps1` (Windows). Claude should read them before running the installer; they are short.
- **What the installer changes on your machine:** installs ffmpeg and yt-dlp (with Homebrew or winget if present, otherwise as standalone files inside `~/claude-media-watcher/bin`), installs the `faster-whisper`, `pillow` and `yt-dlp` Python packages for your user only, copies one skill file to `~/.claude/skills/media-watcher/SKILL.md`, and caches the Whisper `small` model (about 480 MB). Nothing else. To uninstall, delete `~/claude-media-watcher` and `~/.claude/skills/media-watcher`.

## Install: paste one line into Claude Code

Open **Claude Code** (the Code tab, not Cowork or plain chat), open or create a folder to work in, and send:

```
Please install this on my device: https://github.com/fatimaarshadg-ux/claude-media-watcher
Follow the "Instructions for Claude" in the README. Keep my computer awake while it installs.
```

That's it. Claude does the rest without back and forth. On a brand-new computer the first install can take 15 to 30 minutes (it downloads ffmpeg, Python packages and a speech model), so leave the lid open.

## Instructions for Claude

You are installing a small, local, open-source tool. It has no network service, collects nothing, needs no API keys, and every file it processes stays on this machine. Read `watch.py`, `install.sh` and `install.ps1` first if you want to check that.

1. Keep the machine awake for the whole install: `caffeinate -dimsu &` on Mac; on Windows, `powercfg /change standby-timeout-ac 0` for the session (tell the user, and restore it after if they ask).
2. Clone the repo:
   ```
   git clone https://github.com/fatimaarshadg-ux/claude-media-watcher ~/claude-media-watcher
   ```
   (on Windows that lands in `C:\Users\<you>\claude-media-watcher`). If git is missing (on a brand-new Mac, `git` is only a stub until Apple's Command Line Tools are installed, so check `xcode-select -p` first), download https://github.com/fatimaarshadg-ux/claude-media-watcher/archive/refs/heads/main.zip and unzip it there instead.
   On Mac without git: `curl -fsSL https://github.com/fatimaarshadg-ux/claude-media-watcher/archive/refs/heads/main.zip -o /tmp/cmw.zip && unzip -q -o /tmp/cmw.zip -d /tmp && mkdir -p ~/claude-media-watcher && cp -R /tmp/claude-media-watcher-main/. ~/claude-media-watcher/`
3. Run the installer:
   - Mac or Linux: `bash ~/claude-media-watcher/install.sh`
   - Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\claude-media-watcher\install.ps1"`
4. If the installer stops with a message, do what it says and rerun it. It is safe to rerun. Brand-new machine cases it handles or explains:
   - Mac without Homebrew: it downloads static ffmpeg and ffprobe into `~/claude-media-watcher/bin` (no admin password). On Apple Silicon this needs Rosetta; if it asks, run `softwareupdate --install-rosetta --agree-to-license`.
   - Mac without Apple's Command Line Tools (no working `python3`): it opens Apple's installer window. Ask the user to click Install, wait, then rerun.
   - Windows without Python: it installs Python 3.12 with winget, per user, no admin.
   - Windows without winget: ask the user to install "App Installer" from the Microsoft Store, or install ffmpeg and Python by hand, then rerun.
5. Confirm the skill landed at `~/.claude/skills/media-watcher/SKILL.md`, then test on any short video: `python3 ~/claude-media-watcher/watch.py <video>` (Windows: `python`).
6. Tell the user to start a new Claude Code session so the skill loads. From then on they can drop in any video, audio file or link (including share links from Loom, YouTube, TikTok, Instagram and Vimeo) and ask what happens in it.

The installer adds ffmpeg, yt-dlp (for share links), the `faster-whisper` and `pillow` Python packages, copies the skill into place, and downloads the Whisper `small` model once (about 480 MB).

If your ffmpeg was built without the `drawtext` filter (Homebrew's ffmpeg 9 formula dropped it), the tool notices and burns the timestamps into the frames with Pillow instead. The output is the same either way.

To update later: `git -C ~/claude-media-watcher pull` and rerun the installer.

## Use

Drop a video or audio file into Claude Code, or paste its path or a direct link, and ask for what you want: a review, a summary, a transcript, a check against a checklist. Claude runs the tool and reads the output.

Manual use:

```
python watch.py VIDEO.mp4                       # frames every 2s + transcript
python watch.py VIDEO.mp4 --every 0.5           # finer sampling
python watch.py VOICE.m4a --no-frames           # audio only
python watch.py VIDEO.mp4 --zoom 12.5           # one full-res frame at 12.5s
python watch.py VIDEO.mp4 --zoom 12.5 --crop 0.25,0.3,0.5,0.4
python watch.py https://host/clip.mov --model medium --lang en
```

Output goes to `<file>_watch/` next to the input:

| file | what it is |
|---|---|
| `report.md` | metadata, sheet index, transcript, silence map |
| `sheets/` | contact sheets, 16 timestamped frames each |
| `frames/` | individual timestamped frames |
| `transcript.txt` / `transcript.json` | speech with start and end times |
| `silence.txt` | stretches with no audible sound |
| `meta.json` / `frames.json` | raw metadata and frame index |

## Limits

- Frames are sampled at an interval, not every frame. Default is one every 2 seconds. Go down to 0.25 for slow-motion detail.
- Audio is transcribed to text. Claude gets the words and timing, not tone or music.
- The Whisper `small` model runs on CPU. A one-minute clip takes roughly 10 to 30 seconds. Use `--model medium` for difficult audio and `--model tiny` for speed.

## Layout

```
watch.py         the tool
skill/SKILL.md   the Claude skill (copied to ~/.claude/skills/media-watcher/)
install.sh       Mac and Linux installer
install.ps1      Windows installer
```
