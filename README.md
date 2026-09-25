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
Install this on my Claude Code: https://github.com/fatimaarshadg-ux/claude-media-watcher
```

On a brand-new computer the first install can take 15 to 30 minutes (ffmpeg, Python packages and a speech model download once). The installer keeps a Mac awake while it runs; on Windows, keep the laptop plugged in and awake.

## Installation steps

Read `watch.py`, `install.sh` and `install.ps1` first if you want to check them; they are short.

1. Get the code into `~/claude-media-watcher` (on Windows `C:\Users\<you>\claude-media-watcher`):
   - Already there (a previous install): `git -C ~/claude-media-watcher pull`
   - Otherwise: `git clone https://github.com/fatimaarshadg-ux/claude-media-watcher ~/claude-media-watcher`
   - No working git (on a brand-new Mac, `git` is only a stub until Apple's Command Line Tools are installed; `xcode-select -p` fails): `curl -fsSL https://github.com/fatimaarshadg-ux/claude-media-watcher/archive/refs/heads/main.zip -o /tmp/cmw.zip && unzip -q -o /tmp/cmw.zip -d /tmp && mkdir -p ~/claude-media-watcher && cp -R /tmp/claude-media-watcher-main/. ~/claude-media-watcher/`
2. Run the installer. It is safe to rerun.
   - Mac or Linux: `bash ~/claude-media-watcher/install.sh`
   - Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\claude-media-watcher\install.ps1"`
3. If it stops with a message, it says what to do. The cases on a brand-new machine:
   - Mac without Homebrew: handled. It downloads native static ffmpeg and ffprobe (Apple Silicon from ffmpeg.martin-riedl.de, Intel from evermeet.cx; both are the macOS builds linked from ffmpeg.org) and yt-dlp from its official GitHub releases into `~/claude-media-watcher/bin`. No admin password.
   - Mac without Apple's Command Line Tools: it opens Apple's installer window. The user clicks Install, waits, and you rerun.
   - Windows without Python: handled. It installs Python 3.12 with winget, per user, no admin.
   - Windows without winget: the user installs "App Installer" from the Microsoft Store, then rerun.
4. Check `~/.claude/skills/media-watcher/SKILL.md` exists, and test on any short video: `python3 ~/claude-media-watcher/watch.py <video>` (Windows: `python`).
5. Tell the user to start a new Claude Code session so the skill loads. After that they can drop in any video, audio file or link (including Loom, YouTube, TikTok, Instagram and Vimeo share links) and ask what happens in it.

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
