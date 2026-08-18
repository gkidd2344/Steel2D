@echo off
setlocal EnableDelayedExpansion

echo ============================================================
echo  Steel2D -- Build Script
echo ============================================================
echo.

:: Find Python -- try common locations
set PYTHON=
for %%P in (python.exe py.exe) do (
    where %%P >nul 2>&1
    if !errorlevel!==0 (
        set PYTHON=%%P
        goto :found_python
    )
)
:: Check common install paths
for %%D in (
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python39\python.exe"
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
    "C:\Python310\python.exe"
    "C:\Python39\python.exe"
) do (
    if exist %%D (
        set PYTHON=%%D
        goto :found_python
    )
)

echo ERROR: Python 3.9+ not found.
echo Please install Python from https://www.python.org/downloads/
echo Make sure to check "Add python.exe to PATH" during installation.
pause
exit /b 1

:found_python
echo Found Python: %PYTHON%
%PYTHON% --version
echo.

:: The venv is used ONLY via its explicit python.exe (never activate.bat or
:: bare pip/pyinstaller). Venvs are not relocatable: if the project folder is
:: renamed or Python is upgraded, activate.bat and the Scripts\*.exe launchers
:: keep stale absolute paths -- but "<venv>\python.exe -m <module>" keeps
:: working, and the health check below recreates truly broken venvs.
set VENV_PY=.venv\Scripts\python.exe

echo [0/5] Pulling any changes from GitHub before build...
git stash
git pull
echo.

echo [1/5] Creating virtual environment...
if exist "%VENV_PY%" (
    "%VENV_PY%" -c "import sys" >nul 2>&1
    if !errorlevel!==0 (
        echo        .venv already exists and is healthy.
    ) else (
        echo        .venv is broken or stale -- recreating...
        rmdir /s /q ".venv"
    )
)
if not exist "%VENV_PY%" (
    %PYTHON% -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
)

echo [2/5] Installing dependencies...
"%VENV_PY%" -m pip install --upgrade pip --quiet
"%VENV_PY%" -m pip install "Pillow>=10.0" "msgpack>=1.0" "pyinstaller>=6.0" --quiet
if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

echo [3/5] Building executable with PyInstaller...
"%VENV_PY%" -m PyInstaller --clean --noconfirm Steel2D.spec
if errorlevel 1 (
    echo ERROR: PyInstaller build failed. Check output above for details.
    pause
    exit /b 1
)

echo [4/5] Creating portable zip (Steel2D.zip)...
if exist "Steel2D.zip" del /f /q "Steel2D.zip"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Compress-Archive -Path 'dist\Steel2D' -DestinationPath 'Steel2D.zip' -Force"
if errorlevel 1 (
    echo WARNING: Could not create zip -- dist\Steel2D folder is still usable.
) else (
    echo        Created: Steel2D.zip
)

echo [5/5] Done!
echo.
echo ============================================================
echo  Executable : dist\Steel2D\Steel2D.exe
echo  Portable   : Steel2D.zip  (project root)
echo.
echo  To distribute, share Steel2D.zip
echo  Recipient extracts the zip and double-clicks Steel2D.exe
echo  No installation or Python required.
echo  Game data goes to: %%APPDATA%%\Steel2D\
echo ============================================================
echo.
pause
