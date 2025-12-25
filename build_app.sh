#!/bin/bash

APP_NAME="TeslaCamMerger"
MAIN_SCRIPT="backend.py"

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found."
    exit 1
fi

# 检查依赖
echo "Checking dependencies..."
python3 -m pip install -r requirements.txt

# 确定 FFmpeg 路径
FFMPEG_BIN="ffmpeg"
FFPROBE_BIN="ffprobe"

# 优先检查当前目录是否有二进制文件 (用于 Actions)
if [ -f "./ffmpeg" ]; then
    FFMPEG_BIN="./ffmpeg"
fi
if [ -f "./ffprobe" ]; then
    FFPROBE_BIN="./ffprobe"
fi

# 如果还是没找到且是 Mac 且在本地运行，尝试 Homebrew 路径作为兜底
if [[ "$OSTYPE" == "darwin"* ]] && [ "$FFMPEG_BIN" == "ffmpeg" ]; then
    if [ -f "/opt/homebrew/bin/ffmpeg" ]; then
        FFMPEG_BIN="/opt/homebrew/bin/ffmpeg"
        FFPROBE_BIN="/opt/homebrew/bin/ffprobe"
    elif [ -f "/usr/local/bin/ffmpeg" ]; then
        FFMPEG_BIN="/usr/local/bin/ffmpeg"
        FFPROBE_BIN="/usr/local/bin/ffprobe"
    fi
fi

# 清理旧构建
echo "Cleaning up..."
rm -rf build dist $APP_NAME.spec

# 执行打包
echo "Building $APP_NAME..."

# 使用 onedir 模式以确保 .app 结构完整
python3 -m PyInstaller --noconfirm --windowed --name "$APP_NAME" \
    --icon "icon.icns" \
    --add-data "index.html:." \
    --add-data "index.css:." \
    --add-binary "$FFMPEG_BIN:." \
    --add-binary "$FFPROBE_BIN:." \
    --hidden-import "uvicorn" \
    --hidden-import "webview" \
    --hidden-import "uvicorn.logging" \
    --hidden-import "uvicorn.loops" \
    --hidden-import "uvicorn.loops.auto" \
    --hidden-import "uvicorn.protocols" \
    --hidden-import "uvicorn.protocols.http" \
    --hidden-import "uvicorn.protocols.http.auto" \
    --hidden-import "uvicorn.protocols.websockets" \
    --hidden-import "uvicorn.protocols.websockets.auto" \
    --hidden-import "uvicorn.lifespan" \
    --hidden-import "uvicorn.lifespan.on" \
    "$MAIN_SCRIPT"

echo "Build complete."
if [ -d "dist/$APP_NAME.app" ]; then
    echo "Executable created at: $(pwd)/dist/$APP_NAME.app"
    # 清除检疫标记以防止“损坏”报错
    echo "Clearing quarantine attributes..."
    xattr -cr "dist/$APP_NAME.app"

    # --- DMG 生成步骤 (加强版) ---
    echo "Creating professional DMG installer..."
    DMG_NAME="${APP_NAME}.dmg"
    STAGING_DIR="dist/dmg_staging"
    rm -f "dist/$DMG_NAME"
    rm -rf "$STAGING_DIR"
    mkdir -p "$STAGING_DIR"
    
    # 拷贝 App 到暂存区
    cp -R "dist/$APP_NAME.app" "$STAGING_DIR/"
    
    # 创建指向 /Applications 的软链接
    ln -s /Applications "$STAGING_DIR/Applications"
    
    # 使用 hdiutil 从暂存区创建 DMG
    hdiutil create -volname "$APP_NAME" -srcfolder "$STAGING_DIR" -ov -format UDZO "dist/$DMG_NAME"
    
    if [ -f "dist/$DMG_NAME" ]; then
        echo "DMG created at: $(pwd)/dist/$DMG_NAME"
        # 清理冗余的中间件
        echo "Cleaning up intermediate build folders..."
        rm -rf "dist/$APP_NAME"
        rm -rf "$STAGING_DIR"
    else
        echo "DMG creation failed."
    fi
else
    echo "Build failed."
fi
