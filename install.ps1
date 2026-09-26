# claude-media-watcher installer for Windows. Safe to rerun (it also updates).
#
# Everything goes into %USERPROFILE%\claude-media-watcher: ffmpeg, yt-dlp, a private Python with the
# speech-to-text packages, and the tool itself. Outside that folder it only writes the skill file
# (%USERPROFILE%\.claude\skills\media-watcher\SKILL.md) and the speech model cache (%USERPROFILE%\.cache\huggingface).
# No admin rights, no winget, no Microsoft Store, and it never touches an existing Python.
#
# Run it from PowerShell:
#   powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\claude-media-watcher\install.ps1"
# or from Git Bash (what Claude Code uses on Windows):
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$USERPROFILE/claude-media-watcher/install.ps1"
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # the progress bar makes Invoke-WebRequest many times slower
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$here = $PSScriptRoot
$target = Join-Path $env:USERPROFILE "claude-media-watcher"
$bin = Join-Path $target "bin"
$tmp = Join-Path ([IO.Path]::GetTempPath()) ("cmw-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force $tmp | Out-Null

function Step($n, $text) { Write-Host ""; Write-Host "[$n/7] $text" }
function Say($text) { Write-Host "      $text" }
function Fail($text) {
    Write-Host ""
    Write-Host "INSTALL STOPPED: $text" -ForegroundColor Red
    Write-Host "Nothing is half-broken: fix the above and run the installer again, it picks up where it left off."
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
    exit 1
}
function Download($url, $dest) {
    for ($i = 1; $i -le 3; $i++) {
        try { Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing; return }
        catch { if ($i -eq 3) { Fail "could not download $url (check the internet connection, or a firewall or VPN blocking GitHub)." }; Start-Sleep 3 }
    }
}
# Windows PowerShell 5.1 turns anything a program writes to stderr into an error when
# ErrorActionPreference is Stop, so run programs with Continue and check the exit code instead.
# A plain function (no param block) so flags like -version reach the program instead of binding here.
function Run {
    $exe = $args[0]
    $rest = @($args | Select-Object -Skip 1)
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    try { & $exe @rest 2>&1 | Out-Null; return $LASTEXITCODE } catch { return 1 } finally { $ErrorActionPreference = $old }
}

Write-Host "== claude-media-watcher: install =="
Write-Host "This takes about 3 to 15 minutes depending on the internet speed (about 900 MB to download, once)."

# Keep the PC awake while this runs (released automatically when the script ends).
try {
    Add-Type -Namespace CMW -Name Power -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint f);'
    [CMW.Power]::SetThreadExecutionState([uint32]"0x80000001") | Out-Null
} catch { }

$arch = $env:PROCESSOR_ARCHITEW6432
if (-not $arch) { $arch = $env:PROCESSOR_ARCHITECTURE }
$arm = ($arch -eq "ARM64")

# 1. The tool itself
Step 1 "Copying the tool into $target"
New-Item -ItemType Directory -Force $target, $bin | Out-Null
if ((Resolve-Path $here).Path.TrimEnd('\') -ne (Resolve-Path $target).Path.TrimEnd('\')) {
    foreach ($f in "watch.py", "watch", "watch.cmd", "install.sh", "install.ps1", "README.md") {
        $p = Join-Path $here $f
        if (Test-Path $p) { Copy-Item $p $target -Force }
    }
    $skillSrc = Join-Path $here "skill"
    if (Test-Path (Join-Path $target "skill")) { Remove-Item (Join-Path $target "skill") -Recurse -Force }
    Copy-Item $skillSrc $target -Recurse -Force
}
Say "done"

# 2. ffmpeg and ffprobe
Step 2 "Getting ffmpeg (the video engine)"
$ffmpeg = Join-Path $bin "ffmpeg.exe"
$ffprobe = Join-Path $bin "ffprobe.exe"
if ((Test-Path $ffmpeg) -and (Test-Path $ffprobe) -and ((Run $ffmpeg -version) -eq 0)) {
    Say "already installed"
} else {
    # Static builds from BtbN/FFmpeg-Builds (linked from ffmpeg.org).
    if ($arm) { $pkg = "winarm64" } else { $pkg = "win64" }
    $zip = Join-Path $tmp "ffmpeg.zip"
    Download "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-$pkg-gpl.zip" $zip
    Expand-Archive $zip -DestinationPath $tmp -Force
    $src = Get-ChildItem $tmp -Directory -Filter "ffmpeg-*" | Select-Object -First 1
    if (-not $src) { Fail "the ffmpeg download was not in the expected shape." }
    Copy-Item (Join-Path $src.FullName "bin\ffmpeg.exe"), (Join-Path $src.FullName "bin\ffprobe.exe") $bin -Force
    if ((Run $ffmpeg -version) -ne 0) { Fail "the downloaded ffmpeg does not run on this PC." }
    Say "installed into $bin"
}

# 3. yt-dlp
Step 3 "Getting yt-dlp (for video links)"
$ytdlp = Join-Path $bin "yt-dlp.exe"
if (Test-Path $ytdlp) {
    Run $ytdlp -U | Out-Null   # sites change often, so a rerun also updates it
    Say "already installed (checked for updates)"
} else {
    if ($arm) { $ytname = "yt-dlp_arm64.exe" } else { $ytname = "yt-dlp.exe" }
    Download "https://github.com/yt-dlp/yt-dlp/releases/latest/download/$ytname" $ytdlp
    Say "installed"
}

# 4. A private Python with faster-whisper and Pillow
Step 4 "Setting up a private Python with the speech-to-text engine"
$env:UV_PYTHON_INSTALL_DIR = Join-Path $target "python"
$env:UV_CACHE_DIR = Join-Path $target ".cache\uv"
$env:UV_NO_PROGRESS = "1"
$venv = Join-Path $target ".venv"
$py = Join-Path $venv "Scripts\python.exe"
$uv = Join-Path $bin "uv.exe"
if (-not (Test-Path $uv)) {
    if ($arm) { $triple = "aarch64-pc-windows-msvc" } else { $triple = "x86_64-pc-windows-msvc" }
    try {
        Invoke-WebRequest -Uri "https://github.com/astral-sh/uv/releases/latest/download/uv-$triple.zip" -OutFile (Join-Path $tmp "uv.zip") -UseBasicParsing
        Expand-Archive (Join-Path $tmp "uv.zip") -DestinationPath (Join-Path $tmp "uv") -Force
        $found = Get-ChildItem (Join-Path $tmp "uv") -Recurse -Filter "uv.exe" | Select-Object -First 1
        if ($found) { Copy-Item $found.FullName $uv -Force }
    } catch { }
}
$ready = $false
if (Test-Path $uv) {
    if (-not ((Test-Path $py) -and ((Run $py -c "import sys") -eq 0))) {
        Run $uv venv -q --clear --managed-python --python 3.12 $venv | Out-Null
    }
    if ((Test-Path $py) -and
        ((Run $uv pip install -q --python $py faster-whisper pillow yt-dlp librosa demucs soundfile matplotlib) -eq 0) -and
        ((Run $uv pip install -q --python $py --upgrade yt-dlp) -eq 0)) { $ready = $true }
}
if (-not $ready) {
    # Fallback: a venv from an installed Python 3.9+. The "python" on a new PC is often only the
    # Microsoft Store stub (under WindowsApps), which opens the Store instead of running.
    Say "the private Python could not be set up, trying an installed Python instead"
    $sysPy = $null
    foreach ($name in "python", "py") {
        $c = Get-Command $name -ErrorAction SilentlyContinue
        if ($c -and $c.Source -notlike "*WindowsApps*" -and ((Run $c.Source -c "import sys, venv; sys.exit(0 if sys.version_info >= (3, 9) else 1)") -eq 0)) { $sysPy = $c.Source; break }
    }
    if (-not $sysPy) { Fail "no usable Python found and the private one could not be downloaded. Check the internet connection and rerun." }
    if (Test-Path $venv) { Remove-Item $venv -Recurse -Force }
    if ((Run $sysPy -m venv $venv) -ne 0) { Fail "could not create a Python environment." }
    Run $py -m pip install -q --disable-pip-version-check --upgrade pip | Out-Null
    if ((Run $py -m pip install -q --disable-pip-version-check faster-whisper pillow yt-dlp librosa demucs soundfile matplotlib) -ne 0) { Fail "could not install the Python packages." }
}
if ((Run $py -c "import faster_whisper, PIL, yt_dlp") -ne 0) { Fail "the Python packages did not install correctly." }
Say "ready ($(& $py --version 2>&1))"

# 5. The skill
Step 5 "Installing the Claude Code skill"
$skillDir = Join-Path $env:USERPROFILE ".claude\skills\media-watcher"
New-Item -ItemType Directory -Force $skillDir | Out-Null
Copy-Item (Join-Path $target "skill\SKILL.md") (Join-Path $skillDir "SKILL.md") -Force
Say "$skillDir\SKILL.md"

# 6. Speech model
Step 6 "Downloading the speech model (one time, about 480 MB)"
$env:HF_HUB_VERBOSITY = "error"
$env:HF_HUB_DISABLE_PROGRESS_BARS = "1"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
if ((Run $py -c "import warnings; warnings.filterwarnings('ignore'); from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')") -ne 0) {
    Fail "could not download the speech model from huggingface.co."
}
Say "ready"

# 7. Self-test on a generated 3-second clip
Step 7 "Testing"
$clip = Join-Path $tmp "selftest.mp4"
$out = Join-Path $tmp "selftest_watch"
if ((Run $ffmpeg -loglevel error -y -f lavfi -i "testsrc2=size=320x240:rate=10" -f lavfi -i "sine=frequency=440" -t 3 -pix_fmt yuv420p "-c:v" mpeg4 "-c:a" aac $clip) -ne 0) {
    Fail "ffmpeg could not make a test clip."
}
$old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
$log = & $py (Join-Path $target "watch.py") $clip --out $out 2>&1
$code = $LASTEXITCODE
$ErrorActionPreference = $old
if ($code -ne 0 -or -not (Test-Path (Join-Path $out "report.md"))) {
    $log | ForEach-Object { Write-Host $_ }
    Fail "the self-test failed (details above)."
}
Say "passed"
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "== DONE: claude-media-watcher is installed =="
Write-Host "Next: start a NEW Claude Code session (the skill loads at session start), then drop in a video,"
Write-Host "an audio file or a link and ask what happens in it."
Write-Host "Run it by hand: $target\watch.cmd <video file or link>"
