@echo off
rem Runs adwatch.py with the private Python the installer set up.
rem Usage: %USERPROFILE%\claude-media-watcher\adwatch.cmd ^<file or link^> [options]
setlocal
set "D=%~dp0"
if not exist "%D%.venv\Scripts\python.exe" goto system
"%D%.venv\Scripts\python.exe" "%D%adwatch.py" %*
exit /b
:system
where python >nul 2>nul || goto missing
python "%D%adwatch.py" %*
exit /b
:missing
echo error: claude-media-watcher is not installed yet. Run install.ps1 in "%D%" 1>&2
exit /b 1
