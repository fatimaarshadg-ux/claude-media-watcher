# claude-media-watcher

**Let Claude Code watch videos and listen to audio.** Give it a video file, a voice note, or a YouTube / TikTok / Instagram / Loom / Vimeo link and ask anything: "what happens in this?", "summarize this meeting", "transcribe this", "review this ad", "does this video follow my checklist?".

It works by turning the video into timestamped pictures and a written transcript that Claude can read. It runs on your own computer, free, with no account or API key. Works on Mac, Windows and Linux.

## Install (one line)

Open **Claude Code** on your computer, open any folder, and send this message:

```
Install this for me: https://github.com/fatimaarshadg-ux/claude-media-watcher
```

That's it. Claude reads this page and does the rest. It takes about 3 to 15 minutes the first time, depending on your internet. When it's done, start a new Claude Code session and drop in a video.

### Where to paste it (important)

It has to be **Claude Code running on your own computer**, because it installs a tool on that computer:

| You are in | Works? | What to do |
|---|---|---|
| Claude desktop app, **Code** tab, with a folder on your computer | Yes | Paste the line there. |
| `claude` in a terminal | Yes | Paste the line there. |
| Claude desktop app, **Chat** or **Cowork** | No | These can't install tools on your computer. Switch to the **Code** tab (top of the app), pick any folder, and paste the same line. |
| claude.ai in a web browser, or a cloud / remote Claude Code session | No | Those run on a server, not your computer. Open the Claude desktop app, go to the **Code** tab, and paste it there. No desktop app yet? Get it at claude.ai/download. |

## For Claude: how to install this

You are probably reading this because the user pasted the link and asked you to install it. Follow these steps.

**0. Check where you are running.** If you are not Claude Code with shell access to the user's own computer (for example Cowork, the Claude chat, claude.ai on the web, or a cloud or remote session), do not try to install. Tell the user, kindly and briefly: this tool needs Claude Code on their own computer; open the Claude desktop app, click the **Code** tab, choose any folder, and paste the same message there. Then stop.

**1. Tell the user what is about to happen**, in plain words, before running anything. Something like:

> I'll install claude-media-watcher. It lets me watch videos and listen to audio by turning them into timestamped pictures and a transcript. Everything stays in one folder in your home directory (`claude-media-watcher`), no admin password is needed, and nothing you watch gets uploaded anywhere. The first install downloads about 700 MB (a video toolkit, a private copy of Python, and a speech-to-text model) and takes 3 to 15 minutes. You may be asked to approve a few commands; they're all from this project.

**2. Download the code and run the installer.** The installer is safe to rerun: if anything stops it (a timeout, a dropped connection), run the same command again and it continues where it left off. Run it with the longest command timeout you have (10 minutes), or in the background and wait for it.

- **Mac or Linux** (no git needed, works on a brand-new Mac):
  ```
  mkdir -p ~/claude-media-watcher && curl -fsSL https://github.com/fatimaarshadg-ux/claude-media-watcher/archive/refs/heads/main.tar.gz | tar -xz --strip-components=1 -C ~/claude-media-watcher && bash ~/claude-media-watcher/install.sh
  ```
- **Windows, from Git Bash** (Claude Code's usual shell on Windows):
  ```
  mkdir -p ~/claude-media-watcher && curl -fsSL https://github.com/fatimaarshadg-ux/claude-media-watcher/archive/refs/heads/main.tar.gz | tar -xz --strip-components=1 -C ~/claude-media-watcher && powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$USERPROFILE/claude-media-watcher/install.ps1"
  ```
- **Windows, from PowerShell:**
  ```
  $d="$env:USERPROFILE\claude-media-watcher"; New-Item -ItemType Directory -Force $d | Out-Null; curl.exe -fsSL https://github.com/fatimaarshadg-ux/claude-media-watcher/archive/refs/heads/main.tar.gz -o "$env:TEMP\cmw.tar.gz"; tar.exe -xzf "$env:TEMP\cmw.tar.gz" --strip-components=1 -C $d; powershell -NoProfile -ExecutionPolicy Bypass -File "$d\install.ps1"
  ```

While it runs, give the user a short update at each numbered step it prints (`[1/7]` to `[7/7]`) so they know it hasn't frozen. Step 6 (the speech model) is the slowest.

**3. If it prints `INSTALL STOPPED`**, the line after it says why. Almost always it is the internet connection, or a firewall or VPN blocking GitHub or huggingface.co: say so in plain words and rerun once it's fixed. Don't try other install methods first.

**4. When it prints `DONE`**, it has already tested itself on a generated clip. Tell the user:

> Installed and tested. Now start a new Claude Code session (the skill only loads when a session starts). Then drop in a video or audio file, or paste a link, and ask me what happens in it.

## What gets installed, and where

Everything lives in one folder, `~/claude-media-watcher` (on Windows `C:\Users\<you>\claude-media-watcher`):

- **ffmpeg** (reads video and audio). If the computer already has it, that one is used.
- **yt-dlp** (downloads videos from share links). Updated every time the installer is rerun.
- **A private Python** with **faster-whisper** (speech to text) and **Pillow** (images), set up with [uv](https://github.com/astral-sh/uv). It never touches any Python already on the computer.
- **The tool**: `watch.py` plus the launchers `watch` (Mac, Linux, Git Bash) and `watch.cmd` (Windows).

Outside that folder it writes only two things: the skill file at `~/.claude/skills/media-watcher/SKILL.md` (tells Claude Code when and how to use the tool) and the Whisper `small` speech model in `~/.cache/huggingface` (about 480 MB).

**No admin password, no Homebrew, no Xcode, no winget, no Microsoft Store.** Downloads come only from GitHub (ffmpeg builds, yt-dlp, uv, this repo), python.org builds via uv, PyPI, huggingface.co (the speech model) and, on Mac, the ffmpeg builds linked from ffmpeg.org.

**To update:** rerun the install command above. **To uninstall:** delete `~/claude-media-watcher`, `~/.claude/skills/media-watcher` and, if you want the space back, `~/.cache/huggingface`.

## Privacy

It only reads the one file or link you give it, and writes its output next to that file. It does not run in the background, watch folders, start on login, or use your camera, microphone or screen. No telemetry, no accounts, no API keys. The code is short and readable: `watch.py`, `install.sh`, `install.ps1`.

"Watcher" means it watches the videos you hand it. Made by Fatima Arshad. Not an Anthropic project; "claude" in the name only means it is built for Claude Code.

## Using it

Once installed, just talk to Claude Code: drop a file in, paste a path or a link, and ask. Claude runs the tool and reads the results.

By hand:

```
~/claude-media-watcher/watch VIDEO.mp4                      # frames every 2s + transcript
~/claude-media-watcher/watch VIDEO.mp4 --every 0.5          # finer sampling
~/claude-media-watcher/watch VOICE.m4a --no-frames          # audio only
~/claude-media-watcher/watch VIDEO.mp4 --zoom 12.5          # one full-size frame at 12.5s
~/claude-media-watcher/watch VIDEO.mp4 --zoom 12.5 --crop 0.25,0.3,0.5,0.4
~/claude-media-watcher/watch "https://www.youtube.com/watch?v=..." --model medium --lang en
```

On Windows PowerShell or cmd, use `%USERPROFILE%\claude-media-watcher\watch.cmd` instead of `~/claude-media-watcher/watch`.

Output goes to `<file>_watch/` next to the input (for links, under `watch_downloads/` in the current folder):

| file | what it is |
|---|---|
| `report.md` | metadata, sheet index, transcript, silence map |
| `sheets/` | contact sheets, up to 16 timestamped frames each |
| `frames/` | individual timestamped frames |
| `transcript.txt` / `transcript.json` | speech with start and end times |
| `silence.txt` | stretches with no audible sound |
| `meta.json` / `frames.json` | raw metadata and frame index |

## Limits

- Frames are sampled, not every frame: one every 2 seconds by default, and wider on videos over 10 minutes (about 300 frames in total). Use `--every 0.5` for fast action.
- Audio becomes text: Claude gets the words and their timing, not tone of voice or music.
- Speech recognition runs on the CPU. A one-minute clip takes roughly 10 to 30 seconds. `--model medium` for difficult audio, `--model tiny` for speed.
- Private or login-only links can't be downloaded. Download the video yourself and give Claude the file.

## Files

```
watch.py         the tool
watch            launcher for Mac, Linux and Git Bash
watch.cmd        launcher for Windows PowerShell and cmd
skill/SKILL.md   the Claude Code skill (copied to ~/.claude/skills/media-watcher/)
install.sh       Mac and Linux installer
install.ps1      Windows installer
```

## Deep ad watch

`adwatch` (Mac/Linux) or `adwatch.cmd` (Windows) does everything `watch` does at a frame every 0.5 seconds, plus: every cut with a frame, a voice and music split, music tempo and energy changes, words per minute, pauses, voice animation, cuts on beat, and a `timeline.png`. See the skill file for how Claude reads it.
