TeslaCam Merger - Windows 平台打包指南
==========================================

由于当前是在 macOS 环境下进行开发，我无法直接为您生成 `.exe` 文件。
但是，我已经为您准备好了全套跨平台代码，您只需在 Windows 电脑上执行以下步骤即可快速生成软件：

1. 环境准备:
   - 安装 Python 3 (前往 python.org 下载)。
   - 下载 Windows 版 FFmpeg (需包含 `ffmpeg.exe` 和 `ffprobe.exe`)。
     推荐下载地址: https://www.gyan.dev/ffmpeg/builds/

2. 设置步骤:
   - 将此文件夹及其所有内容拷贝到您的 Windows 电脑。
   - 将下载好的 `ffmpeg.exe` 和 `ffprobe.exe` 直接放入本项目的根目录（即与 `backend.py` 放在同一级文件夹下）。
   - (可选) 如果您需要 Windows 图标，可以找一个在线转换网站将 `icon.png` 转换为 `icon.ico`。

3. 开始打包:
   - 双击运行根目录下的 **`build_app_win.bat`**。
   - 脚本会自动为您安装必要的 Python 依赖（FastAPI, PyWebView 等）并启动打包。

4. 导出结果:
   - 打包完成后，您会在项目目录的 **`dist/TeslaCamMerger`** 文件夹中找到生成的软件。
   - 运行文件夹内的 **`TeslaCamMerger.exe`** 即可启动。

祝您使用愉快！如有问题请随时反馈。
