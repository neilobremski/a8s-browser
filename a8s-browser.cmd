@echo off
setlocal
set "REPO_DIR=%~dp0"
set "ENTRY=%REPO_DIR%src\__main__.py"

where python >nul 2>&1
if %ERRORLEVEL%==0 (
    python "%ENTRY%" %*
    exit /b %ERRORLEVEL%
)

where py >nul 2>&1
if %ERRORLEVEL%==0 (
    py -3 "%ENTRY%" %*
    exit /b %ERRORLEVEL%
)

echo a8s-browser: python not found on PATH >&2
exit /b 127
