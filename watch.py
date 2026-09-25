#!/usr/bin/env python3
"""
watch.py: turn a video or audio file into things Claude can read.

Given a local file or a URL, this script writes an output folder containing:
  meta.json          ffprobe metadata (duration, resolution, rotation, fps, streams)
  sheets/            contact sheets: grids of timestamped frames, one image per 16 frames
  frames/            individual timestamped frames at readable size
  audio.wav          the audio track, 16 kHz mono
  transcript.txt     timestamped transcript (faster-whisper, runs locally)
  transcript.json    transcript segments with start/end seconds
  silence.txt        stretches of silence detected in the audio
  report.md          a summary that points at all of the above

Usage:
  python watch.py VIDEO.mp4
  python watch.py VIDEO.mp4 --every 1 --out C:/some/folder
  python watch.py https://example.com/clip.mov --model small --lang en
  python watch.py VOICE.m4a --no-frames
  python watch.py VIDEO.mp4 --zoom 12.5 --crop 0.3,0.4,0.4,0.3   # one frame at 12.5s, cropped

Options:
  --every N       seconds between sampled frames (default 2, min 0.25)
  --tile CxR      contact sheet grid (default 4x4)
  --frame-width W width of individual frames in px (default 720)
  --model NAME    faster-whisper model: tiny, base, small, medium, large-v3 (default small)
  --lang CODE     force transcript language (default: auto-detect)
  --no-frames     skip frame extraction (audio-only files)
  --no-audio      skip audio extraction and transcription
  --out DIR       output folder (default: <file>_watch next to the input, or in cwd for URLs)
  --zoom T        instead of a full run, extract one frame at T seconds (full resolution)
  --crop x,y,w,h  with --zoom: crop as fractions of width/height before saving
"""

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import urllib.request
import os
import warnings

os.environ.setdefault("HF_HUB_VERBOSITY", "error")  # hide the "unauthenticated requests to the HF Hub" notice

# faster-whisper's feature extractor trips harmless numpy divide/overflow warnings on some inputs.
warnings.filterwarnings("ignore", category=RuntimeWarning, module=r"faster_whisper\..*")
from pathlib import Path


def die(msg, code=1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def need(binary):
    # The installer drops a private ffmpeg into <install folder>/bin on machines without a package manager.
    local_bin = Path(__file__).resolve().parent / "bin"
    path = shutil.which(binary) or shutil.which(binary, path=str(local_bin))
    if not path:
        die(f"{binary} not found on PATH. See README for install steps.")
    return path


def run(cmd, capture=False):
    if capture:
        return subprocess.run(cmd, check=True, capture_output=True, text=True,
                              encoding="utf-8", errors="replace").stdout
    proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode:
        die(f"{Path(cmd[0]).name} failed ({proc.returncode}):\n" + proc.stderr.strip()[-1500:])


def hms(seconds):
    seconds = max(0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:05.2f}" if h else f"{m:02d}:{s:05.2f}"


MEDIA_EXT = re.compile(r"\.(mp4|mov|m4v|webm|mkv|avi|mp3|m4a|wav|ogg|aac|flac)$", re.I)


def fetch_page(url, dest_dir):
    """Share pages (Loom, YouTube, TikTok, Instagram, Vimeo...) are not files; yt-dlp resolves them."""
    # Prefer a standalone yt-dlp (Homebrew/winget): the pip one is frozen at an old release on Python 3.9,
    # and sites like Loom change often enough that old releases stop working.
    cli = shutil.which("yt-dlp") or shutil.which("yt-dlp", path=str(Path(__file__).resolve().parent / "bin"))
    if cli:
        print(f"resolving {url} with {cli}")
        # Point yt-dlp at the same ffmpeg we use, so it can join separate video and audio streams.
        out = run([cli, "-q", "--no-warnings", "--print", "after_move:filepath", "-f",
                   "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b", "--merge-output-format", "mp4",
                   "--ffmpeg-location", str(Path(need("ffmpeg")).parent),
                   "-o", str(dest_dir / "%(id)s.%(ext)s"), url], capture=True)
        lines = [l for l in out.splitlines() if l.strip()]
        if lines and Path(lines[-1]).exists():
            return Path(lines[-1])
        die(f"yt-dlp did not produce a file for {url}:\n{out.strip()[-800:]}")
    try:
        import yt_dlp
    except ImportError:
        die("this link is a share page, not a media file, and yt-dlp is not installed. "
            "Run: python3 -m pip install --user yt-dlp  (or rerun the installer)")
    print(f"resolving {url} with yt-dlp")
    opts = {"outtmpl": str(dest_dir / "%(id)s.%(ext)s"), "quiet": True, "no_warnings": True,
            "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b", "merge_output_format": "mp4"}
    local_bin = Path(__file__).resolve().parent / "bin"
    if not shutil.which("ffmpeg") and (local_bin / "ffmpeg").exists():
        opts["ffmpeg_location"] = str(local_bin)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = Path(ydl.prepare_filename(info))
    if not path.exists():
        path = path.with_suffix(".mp4")
    return path


def fetch(url, dest_dir):
    if not MEDIA_EXT.search(re.sub(r"[?#].*$", "", url)):
        return fetch_page(url, dest_dir)
    name = re.sub(r"[?#].*$", "", url.rsplit("/", 1)[-1]) or "download"
    if "." not in name:
        name += ".mp4"
    dest = dest_dir / name
    print(f"downloading {url} -> {dest}")
    req = urllib.request.Request(url, headers={"User-Agent": "claude-media-watcher/1.0"})
    with urllib.request.urlopen(req) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)
    return dest


def _ratio(w, h):
    g = math.gcd(w, h)
    return f"{w // g}:{h // g}"


def probe(ffprobe, src):
    raw = run([ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(src)],
              capture=True)
    data = json.loads(raw)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    fmt = data.get("format", {})
    duration = float(fmt.get("duration") or (video or audio or {}).get("duration") or 0)

    meta = {
        "file": str(src),
        "size_bytes": int(fmt.get("size") or 0),
        "duration_seconds": round(duration, 3),
        "duration": hms(duration),
        "container": fmt.get("format_name"),
        "has_video": video is not None,
        "has_audio": audio is not None,
    }
    if video:
        w, h = int(video.get("width", 0)), int(video.get("height", 0))
        rotation = 0
        for sd in video.get("side_data_list", []) or []:
            if "rotation" in sd:
                rotation = int(float(sd["rotation"]))
        rotation = int(float((video.get("tags") or {}).get("rotate", rotation)))
        if rotation % 180:
            w, h = h, w
        fps_raw = video.get("avg_frame_rate", "0/1")
        try:
            num, den = fps_raw.split("/")
            fps = round(int(num) / int(den), 2) if int(den) else 0
        except Exception:
            fps = 0
        meta.update({
            "width": w, "height": h, "rotation": rotation, "fps": fps,
            "orientation": "portrait" if h > w else ("landscape" if w > h else "square"),
            "aspect_ratio": _ratio(w, h) if w and h else "?",
            "video_codec": video.get("codec_name"),
        })
    if audio:
        meta.update({
            "audio_codec": audio.get("codec_name"),
            "audio_sample_rate": audio.get("sample_rate"),
            "audio_channels": audio.get("channels"),
        })
    return meta


FONT_CANDIDATES = [
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
]


def find_font():
    for f in FONT_CANDIDATES:
        if Path(f).exists():
            return f
    return None


DRAWTEXT_OK = True  # set in main() once we know which ffmpeg we have


def ffmpeg_has_drawtext(ffmpeg):
    # Homebrew's ffmpeg 9 formula dropped freetype, so drawtext is missing there.
    # When it is missing we extract plain frames and stamp them with Pillow instead.
    proc = subprocess.run([ffmpeg, "-hide_banner", "-filters"], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return re.search(r"\sdrawtext\s", proc.stdout) is not None


def timestamp_filter(size=28):
    # burn the running time into the top-left corner of every frame.
    # drawtext needs an explicit font file on Windows (fontconfig crashes without one).
    if not DRAWTEXT_OK:
        return "null"
    font = find_font()
    if not font:
        return "null"
    font = font.replace(":", "\\:")
    return (f"drawtext=fontfile='{font}':text='%{{pts\\:hms}}':x=8:y=8:fontsize={size}:fontcolor=white:"
            "box=1:boxcolor=black@0.6:boxborderw=6")


def hms_ms(seconds):
    # same shape as drawtext's %{pts:hms}: HH:MM:SS.mmm
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    return f"{h:02d}:{m:02d}:{seconds % 60:06.3f}"


def stamp_frames(items, size):
    """Burn a label into each JPEG with Pillow. items = [(path, label), ...].
    Used when ffmpeg has no drawtext filter. Returns False if Pillow is missing."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("warning: ffmpeg lacks drawtext and Pillow is not installed; frames carry no burned-in "
              "timestamps. Use frames.json for times, or: python3 -m pip install --user pillow",
              file=sys.stderr)
        return False
    font_path = find_font()
    try:
        font = ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default(size)
    except Exception:
        font = ImageFont.load_default()
    for path, label in items:
        im = Image.open(path).convert("RGB")
        d = ImageDraw.Draw(im, "RGBA")
        x0, y0, x1, y1 = d.textbbox((8, 8), label, font=font)
        d.rectangle((x0 - 6, y0 - 6, x1 + 6, y1 + 6), fill=(0, 0, 0, 153))
        d.text((8, 8), label, font=font, fill=(255, 255, 255, 255))
        im.save(path, quality=90)
    return True


def extract_frames(ffmpeg, src, out, every, frame_width, tile):
    frames_dir = out / "frames"
    sheets_dir = out / "sheets"
    for d in (frames_dir, sheets_dir):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir()
    fps = f"1/{every}"
    cols, rows = tile

    tile_vf = f"tile={cols}x{rows}:padding=4:margin=4:color=black"
    if DRAWTEXT_OK:
        run([ffmpeg, "-y", "-hide_banner", "-i", str(src),
             "-vf", f"fps={fps},scale={frame_width}:-2,{timestamp_filter(26)}",
             "-q:v", "3", str(frames_dir / "f%04d.jpg")])

        run([ffmpeg, "-y", "-hide_banner", "-i", str(src),
             "-vf", f"fps={fps},scale=360:-2,{timestamp_filter(22)},{tile_vf}",
             "-q:v", "3", str(sheets_dir / "sheet%03d.jpg")])
    else:
        # no drawtext: extract plain frames, stamp them with Pillow, then tile the stamped small ones
        run([ffmpeg, "-y", "-hide_banner", "-i", str(src),
             "-vf", f"fps={fps},scale={frame_width}:-2",
             "-q:v", "3", str(frames_dir / "f%04d.jpg")])
        big = sorted(frames_dir.glob("f*.jpg"))
        stamp_frames([(f, hms_ms(i * every)) for i, f in enumerate(big)], 26)

        small_dir = out / "_sheet_src"
        if small_dir.exists():
            shutil.rmtree(small_dir)
        small_dir.mkdir()
        run([ffmpeg, "-y", "-hide_banner", "-i", str(src),
             "-vf", f"fps={fps},scale=360:-2",
             "-q:v", "3", str(small_dir / "f%04d.jpg")])
        small = sorted(small_dir.glob("f*.jpg"))
        stamp_frames([(f, hms_ms(i * every)) for i, f in enumerate(small)], 22)
        if small:
            run([ffmpeg, "-y", "-hide_banner", "-framerate", "1", "-i", str(small_dir / "f%04d.jpg"),
                 "-vf", tile_vf, "-q:v", "3", str(sheets_dir / "sheet%03d.jpg")])
        shutil.rmtree(small_dir)

    frames = sorted(frames_dir.glob("f*.jpg"))
    sheets = sorted(sheets_dir.glob("sheet*.jpg"))
    per_sheet = cols * rows
    index = []
    for i, f in enumerate(frames):
        t = i * every
        index.append({
            "file": f.name, "seconds": round(t, 3), "time": hms(t),
            "sheet": sheets[i // per_sheet].name if sheets and i // per_sheet < len(sheets) else None,
        })
    with open(out / "frames.json", "w", encoding="utf-8") as fh:
        json.dump(index, fh, indent=1)
    return index, sheets, per_sheet


def extract_audio(ffmpeg, src, out):
    wav = out / "audio.wav"
    run([ffmpeg, "-y", "-hide_banner", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000",
         "-c:a", "pcm_s16le", str(wav)])
    return wav


def detect_silence(ffmpeg, wav, out):
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(wav), "-af", "silencedetect=noise=-35dB:d=1.5", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", proc.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", proc.stderr)]
    spans = list(zip(starts, ends))
    lines = [f"{hms(s)} - {hms(e)}  ({e - s:.1f}s)" for s, e in spans] or ["no silences of 1.5s or longer"]
    (out / "silence.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return spans


def transcribe(wav, out, model_name, lang):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("faster-whisper not installed; skipping transcript. "
              "Run: python -m pip install faster-whisper", file=sys.stderr)
        return None
    print(f"transcribing with faster-whisper '{model_name}'")
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(wav), language=lang, vad_filter=True, beam_size=5)
    segs, lines = [], []
    for s in segments:
        text = s.text.strip()
        if not text:
            continue
        segs.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": text})
        lines.append(f"[{hms(s.start)} - {hms(s.end)}] {text}")
    header = f"language: {info.language} (confidence {info.language_probability:.2f})"
    body = "\n".join(lines) if lines else "(no speech detected)"
    (out / "transcript.txt").write_text(header + "\n\n" + body + "\n", encoding="utf-8")
    with open(out / "transcript.json", "w", encoding="utf-8") as fh:
        json.dump({"language": info.language, "language_probability": info.language_probability,
                   "segments": segs}, fh, indent=1)
    return {"language": info.language, "segments": segs}


def write_report(out, meta, frames, sheets, per_sheet, silence, transcript, every):
    lines = ["# Media watch report", "", f"Source: `{meta['file']}`", "", "## Metadata", ""]
    for k in ("duration", "container", "width", "height", "orientation", "aspect_ratio", "rotation",
              "fps", "video_codec", "audio_codec", "audio_channels", "size_bytes"):
        if k in meta:
            lines.append(f"- {k}: {meta[k]}")
    lines.append("")
    if frames:
        lines += ["## Frames", "",
                  f"{len(frames)} frames sampled every {every}s. Read `sheets/` first "
                  f"(each sheet holds {per_sheet} frames in reading order), then open a frame from "
                  f"`frames/` for detail.", ""]
        for i, s in enumerate(sheets):
            lo = i * per_sheet
            hi = min(lo + per_sheet - 1, len(frames) - 1)
            if lo < len(frames):
                lines.append(f"- `sheets/{s.name}`: {frames[lo]['time']} to {frames[hi]['time']}")
        lines.append("")
    if transcript is not None:
        lines += ["## Transcript", "", f"Language: {transcript['language']}", ""]
        if transcript["segments"]:
            lines += [f"- [{hms(s['start'])}] {s['text']}" for s in transcript["segments"]]
        else:
            lines.append("(no speech detected)")
        lines.append("")
    if silence is not None:
        lines += ["## Silence (1.5s or longer, below -35 dB)", ""]
        lines += [f"- {hms(s)} to {hms(e)}" for s, e in silence] or ["- none"]
        lines.append("")
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")


def zoom(ffmpeg, src, out, t, crop):
    out.mkdir(parents=True, exist_ok=True)
    dest = out / f"zoom_{t:.2f}s.jpg"
    vf = []
    if crop:
        x, y, w, h = crop
        vf.append(f"crop=iw*{w}:ih*{h}:iw*{x}:ih*{y}")
    vf += ["scale='min(1600,iw)':-2", timestamp_filter(30)]
    run([ffmpeg, "-y", "-hide_banner", "-ss", str(t), "-i", str(src), "-frames:v", "1",
         "-vf", ",".join(vf), "-q:v", "2", str(dest)])
    if not DRAWTEXT_OK:
        stamp_frames([(dest, hms_ms(t))], 30)
    print(str(dest))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("--every", type=float, default=2.0)
    ap.add_argument("--tile", default="4x4")
    ap.add_argument("--frame-width", type=int, default=720)
    ap.add_argument("--model", default="small")
    ap.add_argument("--lang", default=None)
    ap.add_argument("--no-frames", action="store_true")
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--zoom", type=float, default=None)
    ap.add_argument("--crop", default=None)
    args = ap.parse_args()

    ffmpeg, ffprobe = need("ffmpeg"), need("ffprobe")
    global DRAWTEXT_OK
    DRAWTEXT_OK = ffmpeg_has_drawtext(ffmpeg)
    every = max(0.25, args.every)
    cols, rows = (int(v) for v in args.tile.lower().split("x"))

    if re.match(r"^https?://", args.source):
        dl_dir = Path(args.out) if args.out else Path.cwd() / "watch_downloads"
        dl_dir.mkdir(parents=True, exist_ok=True)
        src = fetch(args.source, dl_dir)
    else:
        src = Path(args.source).expanduser().resolve()
        if not src.exists():
            die(f"file not found: {src}")

    out = Path(args.out).resolve() if args.out else src.with_name(src.stem + "_watch")
    out.mkdir(parents=True, exist_ok=True)

    if args.zoom is not None:
        crop = tuple(float(v) for v in args.crop.split(",")) if args.crop else None
        zoom(ffmpeg, src, out, args.zoom, crop)
        return

    meta = probe(ffprobe, src)
    with open(out / "meta.json", "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    print(f"{meta['duration']}  {meta.get('width', '?')}x{meta.get('height', '?')}  "
          f"video={meta['has_video']} audio={meta['has_audio']}")

    frames, sheets, per_sheet = [], [], cols * rows
    if meta["has_video"] and not args.no_frames:
        frames, sheets, per_sheet = extract_frames(ffmpeg, src, out, every, args.frame_width, (cols, rows))
        print(f"{len(frames)} frames, {len(sheets)} contact sheets")

    silence, transcript = None, None
    if meta["has_audio"] and not args.no_audio:
        wav = extract_audio(ffmpeg, src, out)
        silence = detect_silence(ffmpeg, wav, out)
        transcript = transcribe(wav, out, args.model, args.lang)
        if transcript:
            print(f"transcript: {len(transcript['segments'])} segments, language {transcript['language']}")

    write_report(out, meta, frames, sheets, per_sheet, silence, transcript, every)
    print(f"\nreport: {out / 'report.md'}")


if __name__ == "__main__":
    main()
