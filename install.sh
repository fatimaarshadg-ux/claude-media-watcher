#!/usr/bin/env bash
# Installs claude-media-watcher on macOS or Linux.
#   - ffmpeg (Homebrew on Mac, apt/dnf on Linux)
#   - faster-whisper (pip, user install)
#   - the media-watcher skill into ~/.claude/skills
# Safe to rerun. Run from the cloned repo folder: bash install.sh
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
target="$HOME/claude-media-watcher"

echo "== claude-media-watcher install =="

# 1. ffmpeg
# On a brand-new Mac there is often no Homebrew. Rather than stop, drop a static ffmpeg and ffprobe
# into ~/claude-media-watcher/bin (watch.py looks there too). No admin password needed.
mkdir -p "$target/bin"
export PATH="$PATH:$target/bin"
if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "installing ffmpeg with Homebrew"
    brew install ffmpeg
  elif [ "$(uname)" = "Darwin" ]; then
    echo "no Homebrew; downloading static ffmpeg and ffprobe (evermeet.cx builds, linked from ffmpeg.org)"
    for tool in ffmpeg ffprobe; do
      tmpzip="$(mktemp -t "$tool").zip"
      curl -fsSL "https://evermeet.cx/ffmpeg/getrelease/$tool/zip" -o "$tmpzip"
      unzip -o -q "$tmpzip" -d "$target/bin"
      rm -f "$tmpzip"
      chmod +x "$target/bin/$tool"
      xattr -d com.apple.quarantine "$target/bin/$tool" 2>/dev/null || true
    done
    # These builds are Intel. Apple Silicon runs them through Rosetta, which may need a one-time install.
    if [ "$(uname -m)" = "arm64" ] && ! "$target/bin/ffmpeg" -version >/dev/null 2>&1; then
      echo "Apple Silicon Mac without Rosetta. Run this once, then rerun the installer:" >&2
      echo "  softwareupdate --install-rosetta --agree-to-license" >&2
      echo "(or install Homebrew from https://brew.sh and rerun; the installer will use it)" >&2
      exit 1
    fi
  elif command -v apt-get >/dev/null 2>&1; then
    echo "installing ffmpeg with apt"
    sudo apt-get update -qq && sudo apt-get install -y -qq ffmpeg
  elif command -v dnf >/dev/null 2>&1; then
    echo "installing ffmpeg with dnf"
    sudo dnf install -y ffmpeg
  else
    echo "ffmpeg is missing and no package manager was found. Install ffmpeg, then rerun." >&2
    exit 1
  fi
fi
echo "ffmpeg: $(command -v ffmpeg)"

# 1b. yt-dlp (for share links: Loom, YouTube, TikTok, Instagram). A standalone copy stays current;
# the pip copy is frozen at an old release on Apple's Python 3.9.
if ! command -v yt-dlp >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    brew install yt-dlp
  elif [ "$(uname)" = "Darwin" ]; then
    curl -fsSL "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos" -o "$target/bin/yt-dlp"
    chmod +x "$target/bin/yt-dlp"
    xattr -d com.apple.quarantine "$target/bin/yt-dlp" 2>/dev/null || true
  else
    curl -fsSL "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp" -o "$target/bin/yt-dlp"
    chmod +x "$target/bin/yt-dlp"
  fi
fi
echo "yt-dlp: $(command -v yt-dlp)"

# 2. python + faster-whisper
# On a brand-new Mac, /usr/bin/python3 is only a stub until the Command Line Tools are installed.
if [ "$(uname)" = "Darwin" ] && ! command -v brew >/dev/null 2>&1 && ! xcode-select -p >/dev/null 2>&1; then
  echo "Python needs Apple's Command Line Tools. A window will open: click Install, wait for it to finish," >&2
  echo "then run this installer again." >&2
  xcode-select --install 2>/dev/null || true
  exit 1
fi
py="$(command -v python3 || command -v python || true)"
if [ -z "$py" ] || ! "$py" -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >/dev/null 2>&1; then
  echo "Python 3.9 or newer not found. Install it from https://www.python.org/downloads/ and rerun." >&2
  exit 1
fi
echo "python: $py ($("$py" --version 2>&1))"
if ! "$py" -c "import faster_whisper, PIL, yt_dlp" >/dev/null 2>&1; then
  echo "installing faster-whisper and pillow"
  "$py" -m pip install --user --quiet faster-whisper pillow yt-dlp 2>/dev/null \
    || "$py" -m pip install --user --quiet --break-system-packages faster-whisper pillow yt-dlp
fi
"$py" -c "import faster_whisper, PIL, yt_dlp; print('faster-whisper', faster_whisper.__version__, '/ pillow', PIL.__version__, '/ yt-dlp', yt_dlp.version.__version__)"

# 3. copy the tool into place (unless we are already running from there)
if [ "$here" != "$target" ]; then
  mkdir -p "$target"
  cp "$here/watch.py" "$here/install.sh" "$here/README.md" "$target/"
  cp -R "$here/skill" "$target/"
  [ -f "$here/install.ps1" ] && cp "$here/install.ps1" "$target/"
fi

# 4. skill
mkdir -p "$HOME/.claude/skills/media-watcher"
cp "$target/skill/SKILL.md" "$HOME/.claude/skills/media-watcher/SKILL.md"
echo "skill installed: ~/.claude/skills/media-watcher/SKILL.md"

# 5. warm the default Whisper model so the first real run is fast
echo "downloading the Whisper 'small' model (one time, about 480 MB)"
"$py" - <<'EOF'
from faster_whisper import WhisperModel
WhisperModel("small", device="cpu", compute_type="int8")
print("model ready")
EOF

echo
echo "Done. Test with:"
echo "  $py $target/watch.py some-video.mp4"
