# TeslaCam Merger (特斯拉行车记录仪视频合并器)

[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc-sa/4.0/)

[![Build Multi-Platform Apps](https://github.com/diciky/TeslaCamMerger/actions/workflows/build.yml/badge.svg)](https://github.com/diciky/TeslaCamMerger/actions/workflows/build.yml)

一个专业、高效且美观的特斯拉行车记录仪（TeslaCam）视频合并工具。它可以将特斯拉产生的多个视角（前、后、左、右）的小段视频合并为一个完整的、分屏显示的 1080p 视频，并按日期进行归类。

## ✨ 功能特性

- **四分屏布局**：完美整合前视、后视、左重复器、右重复器四个视角，提供全方位视野。
- **特斯拉风格 UI**：极致还原特斯拉车载系统的设计美学，支持日历式日期选择。
- **硬件加速支持**：
  - **macOS**: 适配 Apple Silicon (M1/M2/M3) 的 `h264_videotoolbox`。
  - **Windows**: 适配 NVIDIA (NVENC) 和 Intel (QSV) 硬件加速。
- **智能化处理**：
  - 自动识别视频损坏并尝试软件编码兜底（libx264）。
  - 支持多线程并发转码，性能出众。
- **多平台分发**：
  - **macOS**: 提供标准的 `.dmg` 安装包（含“拖拽至 Applications”引导）。
  - **Windows**: 提供独立的 `.exe` 执行文件。
- **云端自动化构建**：通过 GitHub Actions 自动打包所有平台的安装程序。

## 🚀 快速开始 (下载最新版)

**当前版本：v0.1**

如果您不想安装开发环境，可以直接从 GitHub Releases 页面获取成品：

👉 **[前往下载页面](https://github.com/diciky/TeslaCamMerger/releases)**

在下载页面中，您可以找到：
- `TeslaCamMerger_macOS_DMG`: 适合 Mac 用户。
- `TeslaCamMerger_Windows.zip`: 适合 Windows 用户。

## 🛠️ 本地开发与运行

### 环境要求
- Python 3.9+
- FFmpeg (需在环境变量中，或放在项目根目录)

### 安装依赖
```bash
pip install -r requirements.txt
```

### 启动应用
```bash
python backend.py
```
程序启动后会打开一个独立的桌面窗口。

## 📦 手动打包

### macOS
运行项目根目录下的脚本：
```bash
./build_app.sh
```
打包成功后，`.dmg` 安装包将出现在 `dist/` 目录下。

### Windows
1. 确保项目根目录下有 `ffmpeg.exe` 和 `ffprobe.exe`。
2. 双击运行：
```cmd
build_app_win.bat
```
打包成功后，程序将出现在 `dist/TeslaCamMerger` 目录下。

## 🤖 GitHub Actions 自动化

本项目集成了强大的 CI/CD 流程。只需将代码推送到 `main` 分支，GitHub 就会自动启动 macOS 和 Windows 的并发构建，并生成可下载的 Artifacts。

## 📝 许可证 (License)

本项目采用 **[CC BY-NC-SA 4.0 (署名-非商业性使用-相同方式共享 4.0 国际)](https://creativecommons.org/licenses/by-nc-sa/4.0/deed.zh)** 协议开源。

- **非商业性使用**：您不得将本项目及其衍生版本用于任何形式的商业目的（包括但不限于销售软件、封装为付费服务等）。
- **署名**：在分发或修改本项目时，必须保留原作者信息。
- **相同方式共享**：如果您对代码进行了修改或二次开发，则必须以同样的协议开源。

---
*Inspired by Tesla. Built for Tesla Owners.*
