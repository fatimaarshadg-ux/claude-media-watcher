#!/usr/bin/env python3
"""
adwatch.py: deep watch of an ad. Everything watch.py does, plus the things a
2-second frame pass misses: every cut, the music, and the pacing.

  python3 adwatch.py <video file or url> [--out DIR] [--every 0.5]

Writes into DIR (default <file>_adwatch):
  watch/            watch.py output at --every (frames, sheets, report.md)
  cuts/             one frame just after every cut, stamped with its time
  stems/            vocals.wav and music.wav (demucs split)
  timeline.png      one picture: music energy, beats, cuts, speech rate
  pacing.md         cuts, shot lengths, words per minute, pauses, music
                    tempo and energy changes, whether cuts land on beats
  pacing.json       the same numbers for scripts

Needs ffmpeg, faster-whisper, librosa, demucs, matplotlib, soundfile.
What it cannot do: name the song, or judge taste. It measures.
"""
import argparse, json, os, re, subprocess, sys, warnings
from pathlib import Path

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
PY = sys.executable


def run(cmd, capture=False):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 and not capture:
        sys.exit(f"failed: {' '.join(map(str, cmd))}\n{r.stderr[-2000:]}")
    return r


def mmss(t):
    return f"{int(t // 60)}:{t % 60:04.1f}"


def find_video(watch_dir):
    for ext in ("*.mp4", "*.mov", "*.webm", "*.mkv", "*.m4v"):
        hits = sorted(watch_dir.glob(ext))
        if hits:
            return hits[0]
    return None


def detect_cuts(src, threshold):
    r = run(["ffmpeg", "-hide_banner", "-i", str(src), "-vf",
             f"select='gt(scene,{threshold})',showinfo", "-f", "null", "-"], capture=True)
    return [float(m) for m in re.findall(r"pts_time:([0-9.]+)", r.stderr)]


def cut_frames(src, cuts, out, duration):
    out.mkdir(parents=True, exist_ok=True)
    for i, t in enumerate([0.0] + cuts):
        at = min(t + 0.15, max(duration - 0.05, 0))
        # Container duration can run past the last video frame, so step back until a frame exists.
        for back in (0, 0.3, 0.8, 1.5):
            t_at = max(at - back, 0)
            dest = out / f"cut{i:03d}_{t_at:07.2f}s.jpg"
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t_at:.2f}", "-i", str(src),
                 "-frames:v", "1", "-vf", "scale=360:-2", str(dest)], capture=True)
            if dest.exists() and dest.stat().st_size > 0:
                break


def has_audio(src):
    r = run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(src)], capture=True)
    return bool(r.stdout.strip())


def split_stems(src, out):
    out.mkdir(parents=True, exist_ok=True)
    wav = out / "full.wav"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-vn", "-ac", "2", "-ar", "44100", str(wav)])
    run([PY, "-m", "demucs", "--two-stems", "vocals", "-n", "htdemucs", "-o", str(out / "demucs"), str(wav)])
    base = out / "demucs" / "htdemucs" / "full"
    (base / "vocals.wav").replace(out / "vocals.wav")
    (base / "no_vocals.wav").replace(out / "music.wav")
    return wav, out / "vocals.wav", out / "music.wav"


def transcribe_words(vocals, model):
    from faster_whisper import WhisperModel
    m = WhisperModel(model, device="cpu", compute_type="int8")
    segs, _ = m.transcribe(str(vocals), word_timestamps=True, vad_filter=True)
    return [{"w": w.word.strip(), "s": w.start, "e": w.end} for s in segs for w in (s.words or [])]


def analyse(full, vocals, music, words, cuts, duration):
    import numpy as np, librosa
    hop = 0.5
    y_m, sr = librosa.load(str(music), sr=22050, mono=True)
    y_v, _ = librosa.load(str(vocals), sr=22050, mono=True)
    frame = int(sr * hop)
    rms = lambda y: np.array([float(np.sqrt(np.mean(y[i:i + frame] ** 2))) if len(y[i:i + frame]) else 0 for i in range(0, len(y), frame)])
    m_rms, v_rms = rms(y_m), rms(y_v)
    to_db = lambda a: 20 * np.log10(np.maximum(a, 1e-5))
    m_db, v_db = to_db(m_rms), to_db(v_rms)

    # Music presence: stem energy within 30 dB of the loudest music moment and above a floor.
    # Music level relative to voice tells how the mix is balanced (bed under VO, or music-led).
    peak = float(m_db.max()) if len(m_db) else -100
    present = (m_db > max(peak - 30, -50))
    music_share = float(present.mean()) if len(present) else 0.0
    has_music = music_share > 0.15 and peak > -45

    tempo, beats = 0.0, []
    if has_music:
        t, b = librosa.beat.beat_track(y=y_m, sr=sr)
        tempo = float(np.atleast_1d(t)[0])
        beats = librosa.frames_to_time(b, sr=sr).tolist()
    centroid = librosa.feature.spectral_centroid(y=y_m, sr=sr)[0]
    brightness = float(np.median(centroid)) if len(centroid) else 0

    # Energy changes: big jumps in smoothed music level (drops, builds, music in or out).
    changes = []
    if has_music and len(m_db) > 4:
        sm = np.convolve(m_db, np.ones(3) / 3, mode="same")
        for i in range(2, len(sm)):
            d = sm[i] - sm[i - 2]
            if abs(d) >= 8:
                t = round(i * hop, 1)
                if not changes or t - changes[-1]["t"] > 2:
                    changes.append({"t": t, "change_db": round(float(d), 1), "kind": "music rises" if d > 0 else "music drops"})

    # Speech pacing.
    wpm_overall = 0.0
    windows = []
    pauses = []
    if words:
        speak = words[-1]["e"] - words[0]["s"]
        wpm_overall = len(words) / max(speak, 1) * 60
        for start in np.arange(0, duration, 5):
            n = sum(1 for w in words if start <= w["s"] < start + 5)
            windows.append({"t": float(start), "wpm": n * 12})
        for a, b in zip(words, words[1:]):
            gap = b["s"] - a["e"]
            if gap >= 0.6:
                pauses.append({"t": round(a["e"], 1), "len": round(gap, 1), "after": a["w"]})
    first_word = words[0]["s"] if words else None
    hook_words = [w["w"] for w in words if w["s"] < 3.0]

    # Voice expressiveness: pitch spread of the voice stem (semitones, 10th to 90th percentile).
    pitch_range = None
    try:
        f0, vflag, _ = librosa.pyin(y_v[: sr * 60], fmin=70, fmax=400, sr=sr, frame_length=2048)
        f0 = f0[vflag & ~np.isnan(f0)]
        if len(f0) > 20:
            st = 12 * np.log2(f0 / np.median(f0))
            pitch_range = round(float(np.percentile(st, 90) - np.percentile(st, 10)), 1)
    except Exception:
        pass

    # Cut pacing.
    edges = [0.0] + cuts + [duration]
    shots = [round(b - a, 2) for a, b in zip(edges, edges[1:]) if b - a > 0.05]
    cut_windows = [{"t": float(s), "cuts": sum(1 for c in cuts if s <= c < s + 5)} for s in np.arange(0, duration, 5)]
    on_beat = None
    if beats and cuts:
        on_beat = round(sum(1 for c in cuts if min(abs(c - b) for b in beats) <= 0.12) / len(cuts), 2)
    # What share of cuts would land within 0.12s of a beat by pure chance at this tempo.
    chance = round(min(1.0, 0.24 / (60 / tempo)), 2) if tempo else None

    return {
        "duration_s": round(duration, 2),
        "cuts": [round(c, 2) for c in cuts],
        "shot_count": len(shots),
        "avg_shot_s": round(sum(shots) / len(shots), 2) if shots else None,
        "shortest_shot_s": min(shots) if shots else None,
        "longest_shot_s": max(shots) if shots else None,
        "first_cut_s": round(cuts[0], 2) if cuts else None,
        "cuts_per_5s": cut_windows,
        "speech": {
            "words": len(words), "wpm_overall": round(wpm_overall), "first_word_s": first_word,
            "words_in_first_3s": " ".join(hook_words), "wpm_per_5s": windows, "pauses": pauses,
            "voice_pitch_range_semitones": pitch_range,
        },
        "music": {
            "present": bool(has_music), "share_of_runtime": round(music_share, 2), "tempo_bpm": round(tempo),
            "median_brightness_hz": round(brightness), "music_minus_voice_db": round(float(np.median(m_db) - np.median(v_db)), 1) if words else None, "energy_changes": changes,
            "cuts_on_beat_share": on_beat, "on_beat_by_chance": chance, "beats": [round(b, 2) for b in beats],
        },
        "_curves": {"hop": hop, "music_db": m_db.round(1).tolist(), "voice_db": v_db.round(1).tolist()},
    }


def analyse_silent(cuts, duration):
    """The video file has no audio track at all (text-only or muted ad)."""
    edges = [0.0] + cuts + [duration]
    shots = [round(b - a, 2) for a, b in zip(edges, edges[1:]) if b - a > 0.05]
    n = int(duration * 2) + 1
    return {
        "duration_s": round(duration, 2), "cuts": [round(c, 2) for c in cuts], "shot_count": len(shots),
        "avg_shot_s": round(sum(shots) / len(shots), 2) if shots else None,
        "shortest_shot_s": min(shots) if shots else None, "longest_shot_s": max(shots) if shots else None,
        "first_cut_s": round(cuts[0], 2) if cuts else None,
        "cuts_per_5s": [{"t": float(s), "cuts": sum(1 for c in cuts if s <= c < s + 5)} for s in range(0, int(duration) + 1, 5)],
        "no_audio_track": True,
        "speech": {"words": 0, "wpm_overall": 0, "first_word_s": None, "words_in_first_3s": "", "wpm_per_5s": [],
                   "pauses": [], "voice_pitch_range_semitones": None},
        "music": {"present": False, "share_of_runtime": 0, "tempo_bpm": 0, "median_brightness_hz": 0,
                  "music_minus_voice_db": None, "energy_changes": [], "cuts_on_beat_share": None,
                  "on_beat_by_chance": None, "beats": []},
        "_curves": {"hop": 0.5, "music_db": [-100.0] * n, "voice_db": [-100.0] * n},
    }


def plot(res, dest):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    c = res["_curves"]
    hop = c["hop"]
    fig, ax = plt.subplots(3, 1, figsize=(14, 7), sharex=True)
    t = [i * hop for i in range(len(c["music_db"]))]
    ax[0].plot(t, c["music_db"], color="tab:purple", label="music level (dB)")
    ax[0].plot(t[: len(c["voice_db"])], c["voice_db"], color="tab:orange", alpha=0.6, label="voice level (dB)")
    for b in res["music"]["beats"]:
        ax[0].axvline(b, color="tab:purple", alpha=0.08)
    for ch in res["music"]["energy_changes"]:
        ax[0].annotate(ch["kind"], (ch["t"], max(c["music_db"])), fontsize=7, rotation=90, va="top")
    ax[0].legend(loc="lower right", fontsize=8)
    ax[0].set_title(f"music {res['music']['tempo_bpm']} BPM, present {int(res['music']['share_of_runtime']*100)}% of runtime", fontsize=9)
    w = res["speech"]["wpm_per_5s"]
    ax[1].bar([x["t"] + 2.5 for x in w], [x["wpm"] for x in w], width=4.5, color="tab:orange")
    for p in res["speech"]["pauses"]:
        ax[1].axvline(p["t"], color="black", alpha=0.4, linestyle=":")
    ax[1].set_ylabel("words/min")
    ax[1].set_title(f"speech {res['speech']['wpm_overall']} wpm overall, dotted lines are pauses", fontsize=9)
    for cut in res["cuts"]:
        ax[2].axvline(cut, color="tab:blue")
    ax[2].set_yticks([])
    ax[2].set_title(f"cuts: {len(res['cuts'])} (avg shot {res['avg_shot_s']}s)", fontsize=9)
    ax[2].set_xlabel("seconds")
    step = 5 if res["duration_s"] <= 90 else 10
    ax[2].set_xticks(range(0, int(res["duration_s"]) + 1, step))
    fig.tight_layout()
    fig.savefig(dest, dpi=110)


def write_md(res, dest, src_name):
    s, m = res["speech"], res["music"]
    L = [f"# Pacing and sound: {src_name}", "",
         *(["**This video file has no audio track** (silent or text-only ad as delivered by the library)."] if res.get("no_audio_track") else []),
         f"- Length {res['duration_s']}s, {res['shot_count']} shots, average shot {res['avg_shot_s']}s "
         f"(shortest {res['shortest_shot_s']}s, longest {res['longest_shot_s']}s), first cut at {res['first_cut_s']}s.",
         f"- Speech: {s['words']} words, {s['wpm_overall']} words per minute, first word at {s['first_word_s']}s. "
         f"First 3 seconds: \"{s['words_in_first_3s']}\". Voice pitch range {s['voice_pitch_range_semitones']} semitones "
         f"(under 4 is flat, 4 to 8 conversational, over 8 very animated).",
         f"- Music: {'yes' if m['present'] else 'none detected'}"
         + (f", about {m['tempo_bpm']} BPM, under {int(m['share_of_runtime']*100)}% of runtime, median brightness {m['median_brightness_hz']} Hz "
            f"(low is warm or soft, high is bright or punchy), sitting {m['music_minus_voice_db']} dB relative to the voice (around -10 or lower is a quiet bed under the talking). Cuts on the beat: {m['cuts_on_beat_share']} (chance would give {m['on_beat_by_chance']}, so only a clearly higher share means the edit follows the music)." if m["present"] else "."),
         "", "## Cuts per 5 seconds", "",
         " ".join(f"{int(w['t'])}s:{w['cuts']}" for w in res["cuts_per_5s"]),
         "", "## Words per minute per 5 seconds", "",
         " ".join(f"{int(w['t'])}s:{w['wpm']}" for w in s["wpm_per_5s"]),
         "", "## Pauses (0.6s or longer)", ""]
    L += [f"- {mmss(p['t'])} for {p['len']}s after \"{p['after']}\"" for p in s["pauses"]] or ["- none"]
    L += ["", "## Music energy changes", ""]
    L += [f"- {mmss(c['t'])}: {c['kind']} ({c['change_db']} dB)" for c in m["energy_changes"]] or ["- none"]
    L += ["", "## Cut times", "", ", ".join(mmss(c) for c in res["cuts"]) or "none", "",
          "Limits: tempo and brightness are measurements, not taste. The song is not identified. "
          "Speech-over-music separation is good but not perfect, so faint music under loud speech can be missed."]
    dest.write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--out")
    ap.add_argument("--every", type=float, default=0.5)
    ap.add_argument("--scene", type=float, default=0.3, help="cut sensitivity, lower finds more cuts")
    ap.add_argument("--model", default="small")
    a = ap.parse_args()

    out = Path(a.out or (Path(a.src).stem + "_adwatch")).resolve()
    out.mkdir(parents=True, exist_ok=True)
    wdir = out / "watch"
    if not (wdir / "report.md").exists():
        run([PY, str(HERE / "watch.py"), a.src, "--every", str(a.every), "--model", a.model, "--out", str(wdir)])
    src = Path(a.src) if Path(a.src).exists() else find_video(wdir)
    if not src:
        sys.exit("could not find the downloaded video in " + str(wdir))
    dur = float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(src)], capture=True).stdout.strip() or 0)

    cuts = detect_cuts(src, a.scene)
    # Crossfades and jump cuts between similar shots score low; list them separately for a human check.
    soft = [round(t, 2) for t in detect_cuts(src, 0.12) if all(abs(t - c) > 0.4 for c in cuts)]
    cut_frames(src, cuts, out / "cuts", dur)
    if has_audio(src):
        full, vocals, music = split_stems(src, out / "stems")
        words = transcribe_words(vocals, a.model)
        (out / "words.json").write_text(json.dumps(words), encoding="utf-8")
        res = analyse(full, vocals, music, words, cuts, dur)
    else:
        res = analyse_silent(cuts, dur)
    plot(res, out / "timeline.png")
    write_md(res, out / "pacing.md", src.name)
    res["possible_soft_cuts"] = soft
    with open(out / "pacing.md", "a", encoding="utf-8") as f:
        f.write("\n## Possible soft cuts (crossfades, jump cuts): check these in the 0.5s sheets\n\n"
                + (", ".join(mmss(t) for t in soft) or "none") + "\n")
    res.pop("_curves")
    (out / "pacing.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(f"done: {out}\n  {out/'pacing.md'}\n  {out/'timeline.png'}\n  {out/'watch'/'report.md'}\n  {len(cuts)} cuts in {out/'cuts'}")


if __name__ == "__main__":
    main()
