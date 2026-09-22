# claude-media-watcher

Gives Claude Code a way to "watch" a video and "listen" to audio. A small script turns a media file into timestamped frames, contact sheets, and a transcript, and a skill file tells Claude to use it whenever you hand it a video or audio file.

Works on Windows and Mac. Everything runs locally. No file leaves the machine.

## Install (tell Claude to do this)

Paste this repo link into Claude Code on any machine and say "install this". Claude should:

1. Clone the repo:
   ```
   git clone https://github.com/fatimaarshadg-ux/claude-media-watcher ~/claude-media-watcher
   ```
   (on Windows that lands in `C:\Users\<you>\claude-media-watcher`)
2. Run the installer for the platform:
   - Mac: `bash ~/claude-media-watcher/install.sh`
   - Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\claude-media-watcher\install.ps1"`
3. Confirm the skill landed at `~/.claude/skills/media-watcher/SKILL.md`.
4. Start a new Claude Code session so the skill is picked up.

The installer adds ffmpeg (Homebrew or winget), the `faster-whisper` Python package, copies the skill into place, and downloads the Whisper `small` model once (about 480 MB).

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
