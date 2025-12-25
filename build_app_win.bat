@echo off
set APP_NAME=TeslaCamMerger
set MAIN_SCRIPT=backend.py

echo Cleaning old builds...
if exist build rd /s /q build
if exist dist rd /s /q dist

echo.
echo Please ensure ffmpeg.exe and ffprobe.exe are in this directory.
if not exist ffmpeg.exe (
    echo Error: ffmpeg.exe not found!
    exit /b 1
)
if not exist ffprobe.exe (
    echo Error: ffprobe.exe not found!
    exit /b 1
)

echo.
echo Installing dependencies...
python -m pip install fastapi uvicorn sse-starlette pywebview pyinstaller

echo.
echo Building %APP_NAME% for Windows...
python -m PyInstaller --noconfirm --windowed --name "%APP_NAME%" ^
    --icon "icon.ico" ^
    --add-data "index.html;." ^
    --add-data "index.css;." ^
    --add-binary "ffmpeg.exe;." ^
    --add-binary "ffprobe.exe;." ^
    --hidden-import "uvicorn" ^
    --hidden-import "webview" ^
    --hidden-import "uvicorn.logging" ^
    --hidden-import "uvicorn.loops" ^
    --hidden-import "uvicorn.loops.auto" ^
    --hidden-import "uvicorn.protocols" ^
    --hidden-import "uvicorn.protocols.http" ^
    --hidden-import "uvicorn.protocols.http.auto" ^
    --hidden-import "uvicorn.protocols.websockets" ^
    --hidden-import "uvicorn.protocols.websockets.auto" ^
    --hidden-import "uvicorn.lifespan" ^
    --hidden-import "uvicorn.lifespan.on" ^
    "%MAIN_SCRIPT%"

echo.
echo Build Complete! Check the dist folder.
pause
