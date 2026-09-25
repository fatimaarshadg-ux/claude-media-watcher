---
name: media-watcher
description: Watch a video or listen to an audio file the user gives you. Use whenever the user shares, drops, pastes a path to, or links a video (mp4, mov, webm, mkv, avi) or audio file (mp3, m4a, wav, ogg, flac), or pastes a YouTube, TikTok, Instagram, Loom, Vimeo or similar video link, and wants it analyzed, reviewed, summarized, checked, transcribed, described or compared. Also use for UGC and creator content review, ad review, screen recordings, meeting recordings, voice notes, and any "what happens in this clip" question. Runs a local tool that samples timestamped frames and transcribes the audio so you can read both.
---

# Media watcher

Claude Code has no built-in way to play a video or hear a sound file. This skill gives it one: a local tool turns the video or audio (or a link to it) into timestamped pictures and a written transcript, which you then read to review it frame by frame and quote what was said. Everything runs on this computer; nothing is uploaded.

## Running the tool

Use the launcher in the install folder. It picks the right Python by itself.

- Mac and Linux: `~/claude-media-watcher/watch "<file or link>"`
- Windows, from Git Bash (Claude Code's default shell on Windows): `~/claude-media-watcher/watch "<file or link>"`
- Windows, from PowerShell or cmd: `& "$env:USERPROFILE\claude-media-watcher\watch.cmd" "<file or link>"`

Always quote the path; file names often have spaces.

**If the launcher is missing or says it is not installed**, install it (this is safe and needs no admin rights), then run the tool again:

- Mac, Linux, or Windows Git Bash: `mkdir -p ~/claude-media-watcher && curl -fsSL https://github.com/fatimaarshadg-ux/claude-media-watcher/archive/refs/heads/main.tar.gz | tar -xz --strip-components=1 -C ~/claude-media-watcher`, then `bash ~/claude-media-watcher/install.sh` (Mac, Linux) or `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$USERPROFILE/claude-media-watcher/install.ps1"` (Windows).
- Full instructions, including Windows PowerShell: https://github.com/fatimaarshadg-ux/claude-media-watcher#for-claude-how-to-install-this

Run the installer with a long timeout (10 minutes); if it is cut off, run it again and it continues. Tell the user it is a one-time setup of a few minutes. If a link fails to download (private, login-only or removed), ask the user to download the video and give you the file instead.

## Workflow

1. **Get the input.** A dropped or pasted file path is ready to use. A link works directly as the argument: direct file links download as they are, and share pages (YouTube, TikTok, Instagram, Loom, Vimeo, X and many more) are resolved with yt-dlp. Signed or expiring links (cloud storage, some platform APIs) need to be used soon after they are made.

2. **Run it.** Defaults: a frame every 2 seconds (videos over 10 minutes get a wider gap, about 300 frames in total), contact sheets of up to 16 frames, Whisper `small` speech model, language auto-detected. Useful flags:
   - `--every 1` or `--every 0.5` for finer detail, short clips, or fast action. `--every 10` for a quick skim of a long video.
   - `--model medium` for hard audio (accents, noise, mixed languages). `--model tiny` for a quick pass.
   - `--lang en` (or another code) if auto-detect picks the wrong language.
   - `--no-frames` for audio only. `--no-audio` for a silent video or when only visuals matter.
   - `--out <dir>` to choose the output folder. Default is `<file>_watch` next to the input, and `watch_downloads/` in the current folder for links.

   Transcription runs on the CPU: roughly 10 to 30 seconds per minute of audio with `small`. For videos longer than about 20 minutes, tell the user it will take a while, or start with `--model base`.

3. **Read the output, in this order.**
   - `report.md`: metadata, sheet index, full transcript, silence map. Always read this first.
   - `sheets/sheetNNN.jpg`: read every sheet. Each is a grid of timestamped frames in reading order. This is the "watching" pass.
   - `frames/fNNNN.jpg`: open single frames only where a sheet shows something that needs a closer look. `frames.json` maps frame files to seconds.
   - For fine detail at one moment (small text on screen, a label, a hand position), zoom:
     ```
     ~/claude-media-watcher/watch "<file>" --zoom 12.5
     ~/claude-media-watcher/watch "<file>" --zoom 12.5 --crop 0.25,0.3,0.5,0.4
     ```
     `--crop x,y,w,h` are fractions of the frame (left, top, width, height). Read the image at the printed path.

4. **Answer the user.** Cite timestamps for what you claim, both visual (the time burned into each frame) and spoken (from the transcript). Keep what you saw and what you heard separate when it matters.

## Caveats to mention when they matter

- Frames are samples, not every frame. At a 2-second gap a brief action can fall between samples. Say "at least" when counting events, and offer a finer pass (`--every 0.5`) when precision matters.
- The transcript is words and timing only: no tone of voice, music, or sound quality. The silence map shows stretches of 1.5 seconds or more with nothing audible.
- Speech recognition can mishear names, brands and numbers. If a word matters, check it against on-screen text or ask.
- Phone videos can carry a rotation flag. `report.md` shows the corrected width, height and rotation.
