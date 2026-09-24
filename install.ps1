# Installs claude-media-watcher on Windows.
#   - ffmpeg (winget, Gyan.FFmpeg)
#   - faster-whisper and pillow (pip, user install)
#   - the media-watcher skill into %USERPROFILE%\.claude\skills
# Safe to rerun. From the cloned repo folder:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
$ErrorActionPreference = "Stop"

$here = $PSScriptRoot
$target = Join-Path $env:USERPROFILE "claude-media-watcher"

Write-Host "== claude-media-watcher install =="

# 1. ffmpeg
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "installing ffmpeg with winget"
        winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
        # winget adds the bin folder to the user PATH; pick it up for this process too
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    } else {
        throw "ffmpeg is missing and winget is not available. Install ffmpeg from https://www.gyan.dev/ffmpeg/builds/ and rerun."
    }
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    throw "ffmpeg installed but not on PATH yet. Open a new terminal and rerun this script."
}
Write-Host "ffmpeg: $((Get-Command ffmpeg).Source)"

# 1b. yt-dlp (for share links: Loom, YouTube, TikTok, Instagram)
if (-not (Get-Command yt-dlp -ErrorAction SilentlyContinue) -and (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Host "installing yt-dlp with winget"
    winget install --id yt-dlp.yt-dlp -e --accept-source-agreements --accept-package-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}

# 2. python + faster-whisper
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
# The "python" on a brand-new Windows PC is often the Microsoft Store stub, which only opens the Store.
if ($py -and $py.Source -like "*WindowsApps*") { $py = $null }
if (-not $py -and (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Host "installing Python 3.12 with winget (per-user, no admin needed)"
    winget install --id Python.Python.3.12 -e --scope user --accept-source-agreements --accept-package-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py -and $py.Source -like "*WindowsApps*") { $py = Get-Command py -ErrorAction SilentlyContinue }
}
if (-not $py) { throw "Python not found. Install Python 3.9 or newer from python.org (tick 'Add to PATH') and rerun." }
$py = $py.Source
Write-Host "python: $py ($(& $py --version))"
& $py -c "import faster_whisper, PIL, yt_dlp" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "installing faster-whisper and pillow"
    & $py -m pip install --user --quiet faster-whisper pillow yt-dlp
    if ($LASTEXITCODE -ne 0) { throw "pip install faster-whisper failed" }
}
& $py -c "import faster_whisper, PIL, yt_dlp; print('faster-whisper', faster_whisper.__version__, '/ pillow', PIL.__version__, '/ yt-dlp', yt_dlp.version.__version__)"

# 3. copy the tool into place (unless we are already running from there)
if ($here -ne $target) {
    New-Item -ItemType Directory -Force $target | Out-Null
    Copy-Item (Join-Path $here "watch.py"), (Join-Path $here "install.ps1"), (Join-Path $here "README.md") $target -Force
    if (Test-Path (Join-Path $target "skill")) { Remove-Item (Join-Path $target "skill") -Recurse -Force -Confirm:$false }
    Copy-Item (Join-Path $here "skill") $target -Recurse -Force
}

# 4. skill
$skillDir = Join-Path $env:USERPROFILE ".claude\skills\media-watcher"
New-Item -ItemType Directory -Force $skillDir | Out-Null
Copy-Item (Join-Path $target "skill\SKILL.md") (Join-Path $skillDir "SKILL.md") -Force
Write-Host "skill installed: $skillDir\SKILL.md"

# 5. warm the default Whisper model so the first real run is fast
Write-Host "downloading the Whisper 'small' model (one time, about 480 MB)"
& $py -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8'); print('model ready')"

Write-Host ""
Write-Host "Done. Test with:"
Write-Host "  python $target\watch.py some-video.mp4"
