@echo off
setlocal enabledelayedexpansion

:: ============================================================================
:: Fig Binary Installation Script
:: Copies fig.exe from this release package to %USERPROFILE%\.local\bin
:: ============================================================================

set "SCRIPT_DIR=%~dp0"
set "SOURCE=%SCRIPT_DIR%fig.exe"

if not exist "%SOURCE%" (
    echo [ERROR] Could not find "%SOURCE%".
    exit /b 1
)

:: Primary target: %USERPROFILE%\.local\bin
set "LOCAL_BIN=%USERPROFILE%\.local\bin"
if not exist "%LOCAL_BIN%" (
    echo [*] Creating directory %LOCAL_BIN%...
    mkdir "%LOCAL_BIN%"
)

echo [*] Installing fig.exe to %LOCAL_BIN%...
copy /Y "%SOURCE%" "%LOCAL_BIN%\fig.exe" >nul
if errorlevel 1 (
    echo [ERROR] Failed to copy fig.exe to %LOCAL_BIN%.
    echo Please make sure fig.exe is not currently running.
    exit /b 1
)
echo [OK] Successfully copied to %LOCAL_BIN%\fig.exe

:: Ensure %LOCAL_BIN% is on user PATH
powershell -NoProfile -Command "$bin = [System.IO.Path]::Combine($env:USERPROFILE, '.local', 'bin'); $userPath = [Environment]::GetEnvironmentVariable('Path', 'User'); if ($userPath -notlike ('*' + $bin + '*')) { $newPath = if ([string]::IsNullOrEmpty($userPath)) { $bin } else { $userPath.TrimEnd(';') + ';' + $bin }; [Environment]::SetEnvironmentVariable('Path', $newPath, 'User'); Write-Host '[*] Added ' $bin ' to user PATH.' }"

:: Check for Scoop shim collision
set "SCOOP_SHIM=%USERPROFILE%\scoop\shims\fig.exe"
if exist "%SCOOP_SHIM%" (
    echo [*] Syncing copy to %SCOOP_SHIM% (scoop\shims is ahead of .local\bin in PATH)...
    copy /Y "%SOURCE%" "%SCOOP_SHIM%" >nul
    echo [OK] Synced %SCOOP_SHIM%.
)

echo.
echo ============================================================================
echo  Fig installation complete!
echo ============================================================================
echo Test with: fig --version
echo ============================================================================
