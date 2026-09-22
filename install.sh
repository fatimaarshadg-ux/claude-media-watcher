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
if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "installing ffmpeg with Homebrew"
    brew install ffmpeg
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

# 2. python + faster-whisper
py="$(command -v python3 || command -v python || true)"
if [ -z "$py" ]; then
  echo "python3 not found. Install Python 3.9 or newer, then rerun." >&2
  exit 1
fi
echo "python: $py ($("$py" --version 2>&1))"
if ! "$py" -c "import faster_whisper" >/dev/null 2>&1; then
  echo "installing faster-whisper"
  "$py" -m pip install --user --quiet faster-whisper 2>/dev/null \
    || "$py" -m pip install --user --quiet --break-system-packages faster-whisper
fi
"$py" -c "import faster_whisper; print('faster-whisper', faster_whisper.__version__)"

# 3. copy the tool into place (unless we are already running from there)
if [ "$here" != "$target" ]; then
  mkdir -p "$target"
  cp "$here/watch.py" "$here/install.sh" "$here/README.md" "$target/"
  cp -R "$here/skill" "$target/"
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
