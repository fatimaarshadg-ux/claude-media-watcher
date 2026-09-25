#!/usr/bin/env bash
# claude-media-watcher installer for macOS and Linux. Safe to rerun (it also updates).
#
# Everything goes into ~/claude-media-watcher: ffmpeg, yt-dlp, a private Python with the
# speech-to-text packages, and the tool itself. Outside that folder it only writes the skill file
# (~/.claude/skills/media-watcher/SKILL.md) and the speech model cache (~/.cache/huggingface).
# No admin password, no Homebrew, no Xcode tools, and it never touches your system Python.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
target="$HOME/claude-media-watcher"
bin="$target/bin"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

step() { printf '\n[%s/7] %s\n' "$1" "$2"; }
say() { printf '      %s\n' "$1"; }
fail() {
  printf '\nINSTALL STOPPED: %s\n' "$1" >&2
  printf 'Nothing is half-broken: fix the above and run the installer again, it picks up where it left off.\n' >&2
  exit 1
}
download() {
  curl -fsSL --retry 3 --retry-delay 3 --connect-timeout 30 "$1" -o "$2" \
    || fail "could not download $1 (check the internet connection, or a firewall or VPN blocking GitHub)."
}

echo "== claude-media-watcher: install =="
echo "This takes about 3 to 15 minutes depending on the internet speed (about 700 MB to download, once)."

# Keep a Mac awake while this runs; caffeinate exits by itself when the script ends.
if command -v caffeinate >/dev/null 2>&1; then caffeinate -dimsu -w $$ & fi

os="$(uname -s)"
case "$(uname -m)" in
  arm64|aarch64) arch=arm64 ;;
  x86_64|amd64) arch=x64 ;;
  *) fail "this processor ($(uname -m)) is not supported. Supported: Apple Silicon, Intel/AMD 64-bit, ARM64." ;;
esac
case "$os" in
  Darwin|Linux) ;;
  *) fail "this looks like $os. On Windows, run install.ps1 instead (see README)." ;;
esac
for tool in curl tar; do
  command -v "$tool" >/dev/null 2>&1 || fail "'$tool' is missing. Install it with your package manager and rerun."
done
if [ "$os" = "Darwin" ]; then
  command -v unzip >/dev/null 2>&1 || fail "'unzip' is missing."
fi

# 1. The tool itself
step 1 "Copying the tool into $target"
mkdir -p "$target" "$bin"
if [ "$here" != "$target" ]; then
  for f in watch.py watch watch.cmd install.sh install.ps1 README.md; do
    [ -f "$here/$f" ] && cp "$here/$f" "$target/"
  done
  rm -rf "$target/skill"
  cp -R "$here/skill" "$target/"
fi
chmod +x "$target/watch" "$target/install.sh"
say "done"

# 2. ffmpeg and ffprobe (reads video and audio)
step 2 "Getting ffmpeg (the video engine)"
if "$bin/ffmpeg" -version >/dev/null 2>&1 && "$bin/ffprobe" -version >/dev/null 2>&1; then
  say "already installed"
elif command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1 && ffmpeg -version >/dev/null 2>&1; then
  say "using the one already on this computer: $(command -v ffmpeg)"
else
  if [ "$os" = "Darwin" ]; then
    # Native static builds, both linked from ffmpeg.org: Apple Silicon (martin-riedl.de) or Intel (evermeet.cx).
    for tool in ffmpeg ffprobe; do
      if [ "$arch" = "arm64" ]; then
        url="https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/$tool.zip"
      else
        url="https://evermeet.cx/ffmpeg/getrelease/$tool/zip"
      fi
      download "$url" "$tmp/$tool.zip"
      unzip -o -q "$tmp/$tool.zip" -d "$bin"
    done
  else
    # Static Linux builds from BtbN/FFmpeg-Builds (linked from ffmpeg.org). No sudo needed.
    if [ "$arch" = "arm64" ]; then pkg=linuxarm64; else pkg=linux64; fi
    download "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-$pkg-gpl.tar.xz" "$tmp/ffmpeg.tar.xz"
    tar -xJf "$tmp/ffmpeg.tar.xz" -C "$tmp" || fail "could not unpack ffmpeg (is 'xz' installed?)."
    cp "$tmp"/ffmpeg-*/bin/ffmpeg "$tmp"/ffmpeg-*/bin/ffprobe "$bin/"
  fi
  chmod +x "$bin/ffmpeg" "$bin/ffprobe"
  "$bin/ffmpeg" -version >/dev/null 2>&1 || fail "the downloaded ffmpeg does not run on this computer."
  say "installed into $bin"
fi

# 3. yt-dlp (turns share links like YouTube, TikTok, Instagram, Loom, Vimeo into a video file)
step 3 "Getting yt-dlp (for video links)"
if [ "$os" = "Darwin" ]; then ytname=yt-dlp_macos
elif [ "$arch" = "arm64" ]; then ytname=yt-dlp_linux_aarch64
else ytname=yt-dlp_linux; fi
if [ -x "$bin/yt-dlp" ]; then
  # Sites change often, so a rerun also updates it.
  "$bin/yt-dlp" -U >/dev/null 2>&1 || true
  say "already installed (checked for updates)"
else
  download "https://github.com/yt-dlp/yt-dlp/releases/latest/download/$ytname" "$bin/yt-dlp"
  chmod +x "$bin/yt-dlp"
  say "installed"
fi

# 4. A private Python with faster-whisper (speech to text) and Pillow (images)
step 4 "Setting up a private Python with the speech-to-text engine"
export UV_PYTHON_INSTALL_DIR="$target/python" UV_CACHE_DIR="$target/.cache/uv" UV_NO_PROGRESS=1
venv="$target/.venv"
py="$venv/bin/python"
packages=(faster-whisper pillow yt-dlp)
if [ ! -x "$bin/uv" ]; then
  if [ "$os" = "Darwin" ]; then triple=apple-darwin; else triple=unknown-linux-musl; fi
  if [ "$arch" = "arm64" ]; then triple="aarch64-$triple"; else triple="x86_64-$triple"; fi
  if curl -fsSL --retry 3 --connect-timeout 30 "https://github.com/astral-sh/uv/releases/latest/download/uv-$triple.tar.gz" -o "$tmp/uv.tar.gz" \
     && tar -xzf "$tmp/uv.tar.gz" -C "$tmp"; then
    cp "$tmp/uv-$triple/uv" "$bin/uv" && chmod +x "$bin/uv"
  fi
fi
ready=no
if [ -x "$bin/uv" ]; then
  if ! "$py" -c "import sys" >/dev/null 2>&1; then
    "$bin/uv" venv -q --clear --managed-python --python 3.12 "$venv" || true
  fi
  if "$py" -c "import sys" >/dev/null 2>&1 \
     && "$bin/uv" pip install -q --python "$py" "${packages[@]}" \
     && "$bin/uv" pip install -q --python "$py" --upgrade yt-dlp; then
    ready=yes
  fi
fi
if [ "$ready" = no ]; then
  # Fallback: a venv from a system Python 3.9+. On a Mac without Xcode tools /usr/bin/python3 is only a
  # stub that opens a popup, so skip it there.
  say "the private Python could not be set up, trying the system Python instead"
  sys_py=""
  for cand in python3.13 python3.12 python3.11 python3.10 python3 python; do
    p="$(command -v "$cand" 2>/dev/null || true)"
    [ -n "$p" ] || continue
    if [ "$os" = "Darwin" ] && [ "$p" = "/usr/bin/python3" ] && ! xcode-select -p >/dev/null 2>&1; then continue; fi
    if "$p" -c "import sys, venv; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >/dev/null 2>&1; then sys_py="$p"; break; fi
  done
  [ -n "$sys_py" ] || fail "no usable Python found and the private one could not be downloaded. Check the internet connection and rerun."
  rm -rf "$venv"
  "$sys_py" -m venv "$venv" || fail "could not create a Python environment (on Debian/Ubuntu: sudo apt install python3-venv)."
  "$py" -m pip install -q --disable-pip-version-check --upgrade pip >/dev/null 2>&1 || true
  "$py" -m pip install -q --disable-pip-version-check "${packages[@]}" || fail "could not install the Python packages."
fi
"$py" -c "import faster_whisper, PIL, yt_dlp" >/dev/null 2>&1 || fail "the Python packages did not install correctly."
say "ready ($("$py" --version 2>&1), faster-whisper $("$py" -c 'import faster_whisper; print(faster_whisper.__version__)'))"

# 5. The skill, which tells Claude Code when and how to use the tool
step 5 "Installing the Claude Code skill"
mkdir -p "$HOME/.claude/skills/media-watcher"
cp "$target/skill/SKILL.md" "$HOME/.claude/skills/media-watcher/SKILL.md"
say "~/.claude/skills/media-watcher/SKILL.md"

# 6. Speech model, so the first real run is fast
step 6 "Downloading the speech model (one time, about 480 MB)"
HF_HUB_VERBOSITY=error HF_HUB_DISABLE_PROGRESS_BARS=1 "$py" - <<'EOF' || fail "could not download the speech model from huggingface.co."
import warnings; warnings.filterwarnings("ignore")
from faster_whisper import WhisperModel
WhisperModel("small", device="cpu", compute_type="int8")
EOF
say "ready"

# 7. Self-test on a generated 3-second clip
step 7 "Testing"
ff="$bin/ffmpeg"; [ -x "$ff" ] || ff="$(command -v ffmpeg)"
"$ff" -loglevel error -y -f lavfi -i testsrc2=size=320x240:rate=10 -f lavfi -i sine=frequency=440 \
  -t 3 -pix_fmt yuv420p -c:v mpeg4 -c:a aac "$tmp/selftest.mp4" || fail "ffmpeg could not make a test clip."
"$target/watch" "$tmp/selftest.mp4" --out "$tmp/selftest_watch" >/dev/null 2>"$tmp/selftest.err" \
  || { cat "$tmp/selftest.err" >&2; fail "the self-test failed (details above)."; }
[ -f "$tmp/selftest_watch/report.md" ] && ls "$tmp/selftest_watch/sheets/"*.jpg >/dev/null 2>&1 \
  || fail "the self-test ran but produced no report."
say "passed"

echo
echo "== DONE: claude-media-watcher is installed =="
echo "Next: start a NEW Claude Code session (the skill loads at session start), then drop in a video,"
echo "an audio file or a link and ask what happens in it."
echo "Run it by hand: $target/watch <video file or link>"
