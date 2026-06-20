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

echo [1/5] Creating virtual environment...
if exist ".venv" (
    echo        .venv already exists.
) else (
    %PYTHON% -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
)

echo [2/5] Installing dependencies...
call .venv\Scripts\activate.bat
pip install --upgrade pip --quiet
pip install Pillow>=10.0 msgpack>=1.0 pyinstaller>=6.0 --quiet
if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

echo [3/5] Building executable with PyInstaller...
pyinstaller --clean --noconfirm Steel2D.spec
if errorlevel 1 (
    echo ERROR: PyInstaller build failed. Check output above for details.
    pause
    exit /b 1
)

echo [4/5] Creating portable zip (dist\Steel2D.zip)...
if exist "dist\Steel2D.zip" del /f /q "dist\Steel2D.zip"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Compress-Archive -Path 'dist\Steel2D' -DestinationPath 'dist\Steel2D.zip' -Force"
if errorlevel 1 (
    echo WARNING: Could not create zip -- dist\Steel2D folder is still usable.
) else (
    echo        Created: dist\Steel2D.zip
)

echo [5/5] Done!
echo.
echo ============================================================
echo  Executable : dist\Steel2D\Steel2D.exe
echo  Portable   : dist\Steel2D.zip
echo.
echo  To distribute, share dist\Steel2D.zip
echo  Recipient extracts the zip and double-clicks Steel2D.exe
echo  No installation or Python required.
echo  Game data goes to: %%APPDATA%%\Steel2D\
echo ============================================================
echo.
pause
