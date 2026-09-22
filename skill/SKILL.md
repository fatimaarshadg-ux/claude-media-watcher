---
name: media-watcher
description: Watch a video or listen to an audio file the user gives you. Use whenever the user shares, drops, pastes a path to, or links a video (mp4, mov, webm, mkv) or audio file (mp3, m4a, wav, ogg) and wants it analyzed, reviewed, summarized, checked, transcribed, or described. Also use for Trybe creator submissions, UGC review, ad review, and any "what happens in this clip" question. Runs a local script that samples timestamped frames and transcribes the audio so you can read both.
---

# Media watcher

You cannot play video or hear audio. This skill turns a media file into images and text you can read, so you can review it frame by frame and quote what was said.

## Where the tool is

The script is `watch.py` in the media-watcher install folder:

- Windows: `%USERPROFILE%\claude-media-watcher\watch.py`
- Mac and Linux: `~/claude-media-watcher/watch.py`

Run it with `python` on Windows and `python3` on Mac. It needs `ffmpeg` and `ffprobe` on PATH and the `faster-whisper` Python package. If any is missing, run the installer in that folder (`install.ps1` on Windows, `install.sh` on Mac) and try again.

## Workflow

1. **Get the file locally.** A dropped or pasted path is ready. A URL works directly as the argument (the script downloads it). For a Trybe submission, fetch a fresh signed `asset.url` from the Brand API first; they expire in about 20 minutes.

2. **Run the script.**
   ```
   python ~/claude-media-watcher/watch.py "<file or url>"
   ```
   Defaults: a frame every 2 seconds, contact sheets of 16 frames, Whisper `small` model. Useful flags:
   - `--every 1` or `--every 0.5` when the user wants finer detail or the clip is short.
   - `--model medium` for hard audio (accents, noise, mixed languages). `--model tiny` for a quick pass.
   - `--lang en` (or another code) if auto-detect picks wrong.
   - `--no-frames` for audio-only files. `--no-audio` for silent video.
   - `--out <dir>` to choose the output folder. Default is `<file>_watch` next to the input.

3. **Read the output in this order.**
   - `report.md`: metadata, sheet index, full transcript, silence map. Always read this first.
   - `sheets/sheetNNN.jpg`: read every sheet. Each is a grid of timestamped frames in reading order. This is the "watch" pass.
   - `frames/fNNNN.jpg`: open individual frames only where the sheets show something that needs a closer look. `frames.json` maps frame files to seconds.
   - For fine detail at one moment, run a zoom:
     ```
     python ~/claude-media-watcher/watch.py "<file>" --zoom 12.5
     python ~/claude-media-watcher/watch.py "<file>" --zoom 12.5 --crop 0.25,0.3,0.5,0.4
     ```
     `--crop x,y,w,h` are fractions of the frame (left, top, width, height). Read the printed path.

4. **Report to the user.** Cite timestamps for everything you claim, both visual (from the burned-in frame times) and spoken (from the transcript). Say what you saw and what you heard as separate things when it matters.

## Caveats to state in any review

- Frames are sampled, not continuous. At the default 2 seconds, a brief action can fall between samples. Say "at least" for counts of lapses, and offer a finer pass (`--every 0.5`) when it matters.
- The transcript is speech only. You get words and timing, not tone, music, or sound quality. The silence map tells you where nothing audible happened for 1.5 seconds or more.
- Whisper can mishear brand names and numbers. If a word matters, check it against the frames or ask.
- Portrait video from phones sometimes carries a rotation flag. `report.md` shows the corrected width and height and the rotation value.

## Related

For Trybe submissions, pair this with the `trybe-portal` skill for fetching the file and the Bambora content checklist for what to judge.
