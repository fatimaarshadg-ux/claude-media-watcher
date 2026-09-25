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
  --every N       seconds between sampled frames (default: 2, or wider on videos over
                  10 minutes so there are about 300 frames; min 0.25)
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
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")  # Windows without developer mode

# faster-whisper's feature extractor trips harmless numpy divide/overflow warnings on some inputs.
warnings.filterwarnings("ignore", category=RuntimeWarning, module=r"faster_whisper\..*")
from pathlib import Path


def die(msg, code=1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


LOCAL_BIN = Path(__file__).resolve().parent / "bin"
INSTALL_HINT = ("run the installer again: bash ~/claude-media-watcher/install.sh on Mac/Linux, or "
                "install.ps1 in %USERPROFILE%\\claude-media-watcher on Windows")


def which(binary):
    # The installer puts its own ffmpeg, ffprobe and yt-dlp in <install folder>/bin; prefer those.
    return shutil.which(binary, path=str(LOCAL_BIN)) or shutil.which(binary)


def need(binary):
    path = which(binary)
    if not path:
        die(f"{binary} not found. To fix, {INSTALL_HINT}.")
    return path


def run(cmd, capture=False):
    if capture:
        return subprocess.run(cmd, check=True, capture_output=True, text=True,
                              encoding="utf-8", errors="replace").stdout
    proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode:
        die(f"{Path(cmd[0]).name} failed ({proc.returncode}):\n" + proc.stderr.strip()[-1500:])


def sample_frames(ffmpeg, src, every, vf_after, dest_pattern):
    """Write one frame per `every` seconds and return each written frame's real time in seconds.
    select keeps the first frame at or after each multiple of `every`, and showinfo reports its true
    timestamp, so labels match the picture (the fps filter would shift them by up to half a gap)."""
    vf = f"select='gte(t\\,{every}*selected_n)',showinfo" + (f",{vf_after}" if vf_after else "")
    stderr = ""
    for sync in (["-fps_mode", "vfr"], ["-vsync", "vfr"]):  # -fps_mode on ffmpeg 5.1+, -vsync before
        proc = subprocess.run([ffmpeg, "-y", "-hide_banner", "-i", str(src), "-vf", vf, *sync,
                               "-q:v", "3", str(dest_pattern)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                              encoding="utf-8", errors="replace")
        stderr = proc.stderr
        if proc.returncode == 0:
            return [float(t) for t in re.findall(r"\bpts_time:\s*(-?[\d.]+)", stderr)]
    die(f"ffmpeg failed while sampling frames:\n{stderr.strip()[-1500:]}")


def hms(seconds):
    seconds = max(0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:05.2f}" if h else f"{m:02d}:{s:05.2f}"


MEDIA_EXT = re.compile(r"\.(mp4|mov|m4v|webm|mkv|avi|mp3|m4a|wav|ogg|aac|flac)$", re.I)


class _Quiet:
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


def fetch_page(url, dest_dir):
    """Share pages (Loom, YouTube, TikTok, Instagram, Vimeo...) are not files; yt-dlp resolves them."""
    # The standalone yt-dlp in <install folder>/bin is kept current by the installer; sites change often
    # enough that old releases stop working. The Python module is the fallback.
    fmt = "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b"
    ffmpeg_dir = str(Path(need("ffmpeg")).parent)  # so yt-dlp can join separate video and audio streams
    problem = ""
    cli = which("yt-dlp")
    if cli:
        print(f"resolving {url} with yt-dlp")
        proc = subprocess.run([cli, "-q", "--no-warnings", "--no-playlist", "--print", "after_move:filepath",
                               "-f", fmt, "--merge-output-format", "mp4", "--ffmpeg-location", ffmpeg_dir,
                               "-o", str(dest_dir / "%(id)s.%(ext)s"), url],
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        lines = [l for l in proc.stdout.splitlines() if l.strip()]
        if proc.returncode == 0 and lines and Path(lines[-1]).exists():
            return Path(lines[-1])
        problem = (proc.stderr or proc.stdout).strip()[-800:]
    try:
        import yt_dlp
    except ImportError:
        die(f"could not download {url}.\n{problem}\nIf the link is private, download the video yourself and "
            f"pass the file instead. Otherwise {INSTALL_HINT}.")
    opts = {"outtmpl": str(dest_dir / "%(id)s.%(ext)s"), "quiet": True, "no_warnings": True,
            "noplaylist": True, "format": fmt, "merge_output_format": "mp4", "ffmpeg_location": ffmpeg_dir,
            "logger": _Quiet()}  # errors are reported once, below
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            path = Path(ydl.prepare_filename(info))
    except Exception as e:
        die(f"could not download {url}: {problem or e}\n"
            "If the link is private or needs a login, download the video yourself and pass the file instead.")
    if not path.exists():
        path = path.with_suffix(".mp4")
    return path


def ssl_context():
    # A private Python may not see the system certificates; certifi (installed with faster-whisper) has them.
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def fetch(url, dest_dir):
    if not MEDIA_EXT.search(re.sub(r"[?#].*$", "", url)):
        return fetch_page(url, dest_dir)
    name = re.sub(r"[?#].*$", "", url.rsplit("/", 1)[-1]) or "download"
    if "." not in name:
        name += ".mp4"
    dest = dest_dir / name
    print(f"downloading {url} -> {dest}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (claude-media-watcher)"})
    try:
        with urllib.request.urlopen(req, context=ssl_context(), timeout=60) as r, open(dest, "wb") as f:
            shutil.copyfileobj(r, f)
    except Exception as e:
        if dest.exists():
            dest.unlink()
        print(f"direct download failed ({e}); trying yt-dlp")
        return fetch_page(url, dest_dir)
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


def pillow():
    try:
        from PIL import Image, ImageDraw, ImageFont
        return Image, ImageDraw, ImageFont
    except ImportError:
        return None


def load_font(size):
    _, _, ImageFont = pillow()
    font_path = find_font()
    try:
        return ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default(size)
    except Exception:
        return ImageFont.load_default()


def stamp(im, label, font):
    """Burn a label into the top-left corner of a Pillow image, in place."""
    _, ImageDraw, _ = pillow()
    d = ImageDraw.Draw(im, "RGBA")
    x0, y0, x1, y1 = d.textbbox((8, 8), label, font=font)
    d.rectangle((x0 - 6, y0 - 6, x1 + 6, y1 + 6), fill=(0, 0, 0, 153))
    d.text((8, 8), label, font=font, fill=(255, 255, 255, 255))


def stamp_frames(items, size):
    """Burn a label into each JPEG with Pillow. items = [(path, label), ...]. False if Pillow is missing."""
    if not pillow():
        print("warning: frames carry no burned-in timestamps (Pillow missing). Use frames.json for times.",
              file=sys.stderr)
        return False
    Image = pillow()[0]
    font = load_font(size)
    for path, label in items:
        im = Image.open(path).convert("RGB")
        stamp(im, label, font)
        im.save(path, quality=90)
    return True


def extract_frames(ffmpeg, src, out, every, frame_width, tile):
    frames_dir = out / "frames"
    sheets_dir = out / "sheets"
    for d in (frames_dir, sheets_dir):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir()
    cols, rows = tile
    per_sheet = cols * rows

    if pillow():
        # One decode pass: plain frames from ffmpeg, then Pillow stamps the time on each and builds
        # contact sheets that are only as big as the frames they hold.
        times = sample_frames(ffmpeg, src, every, f"scale={frame_width}:-2", frames_dir / "f%04d.jpg")
        Image = pillow()[0]
        big_font, small_font = load_font(26), load_font(22)
        big = sorted(frames_dir.glob("f*.jpg"))
        pad = 4
        for n, lo in enumerate(range(0, len(big), per_sheet), start=1):
            thumbs = []
            for i in range(lo, min(lo + per_sheet, len(big))):
                label = hms_ms(times[i] if i < len(times) else i * every)
                im = Image.open(big[i]).convert("RGB")
                small = im.resize((360, max(2, round(im.height * 360 / im.width))))
                stamp(im, label, big_font)
                im.save(big[i], quality=90)
                stamp(small, label, small_font)
                thumbs.append(small)
            w = max(t.width for t in thumbs)
            h = max(t.height for t in thumbs)
            c = min(cols, len(thumbs))
            r = -(-len(thumbs) // cols)
            sheet = Image.new("RGB", (c * w + (c + 1) * pad, r * h + (r + 1) * pad), "black")
            for k, t in enumerate(thumbs):
                sheet.paste(t, (pad + (k % cols) * (w + pad), pad + (k // cols) * (h + pad)))
            sheet.save(sheets_dir / f"sheet{n:03d}.jpg", quality=85)
    else:
        # No Pillow: let ffmpeg burn the time in (if it has drawtext) and tile the sheets.
        tile_vf = f"tile={cols}x{rows}:padding=4:margin=4:color=black"
        times = sample_frames(ffmpeg, src, every, f"scale={frame_width}:-2,{timestamp_filter(26)}",
                              frames_dir / "f%04d.jpg")
        sample_frames(ffmpeg, src, every, f"scale=360:-2,{timestamp_filter(22)},{tile_vf}",
                      sheets_dir / "sheet%03d.jpg")

    frames = sorted(frames_dir.glob("f*.jpg"))
    sheets = sorted(sheets_dir.glob("sheet*.jpg"))
    index = []
    for i, f in enumerate(frames):
        t = times[i] if i < len(times) else i * every
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
        print(f"faster-whisper is not available, so there is no transcript. To fix, {INSTALL_HINT}.",
              file=sys.stderr)
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
    vf += ["scale='min(1600,iw)':-2", "null" if pillow() else timestamp_filter(30)]
    run([ffmpeg, "-y", "-hide_banner", "-ss", str(t), "-i", str(src), "-frames:v", "1",
         "-vf", ",".join(vf), "-q:v", "2", str(dest)])
    if pillow() or not DRAWTEXT_OK:
        stamp_frames([(dest, hms_ms(t))], 30)
    print(str(dest))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("--every", type=float, default=None)
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

    if args.every is not None:
        every = max(0.25, args.every)
    else:
        # 2s by default; on long videos widen the gap so there are about 300 frames to read.
        every = 2.0 if meta["duration_seconds"] <= 600 else float(math.ceil(meta["duration_seconds"] / 300))
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
