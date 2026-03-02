# TeslaCam Viewer iOS App

一个用于浏览和播放 TeslaCam 四分屏合并视频的 iOS 原生应用。

## 项目结构

```
TeslaCamViewer/
├── App/
│   └── TeslaCamViewerApp.swift      # 应用入口
├── Views/
│   ├── ContentView.swift            # 主界面
│   ├── DatePickerView.swift         # 日期选择器
│   ├── VideoListView.swift          # 视频列表
│   └── VideoPlayerView.swift        # 视频播放器
├── ViewModels/
│   └── VideoViewModel.swift         # 视图状态管理
├── Models/
│   └── Video.swift                  # 数据模型
└── Services/
    └── APIService.swift             # API 通信服务
```

## 开发环境要求

- macOS 13.0+
- Xcode 15.0+
- iOS 16.0+ 目标设备

## 如何在 Xcode 中创建项目

1. 打开 Xcode
2. 选择 "Create New Project"
3. 选择 "iOS" → "App"
4. 填写项目信息:
   - Product Name: `TeslaCamViewer`
   - Organization Identifier: `com.yourdomain`
   - Interface: `SwiftUI`
   - Language: `Swift`
5. 将本目录下的 `.swift` 文件拖入 Xcode 项目中

## 配置 API 连接

在应用首次启动时，需要配置服务器地址和 API 密钥：

```swift
APIService.shared.configure(
    baseURL: "https://your-cloud-backend.com",
    apiKey: "your-api-key"
)
```

## 生成 IPA (无开发者账号)

### 方法 1: Xcode 直连

1. 用 USB 连接 iPhone
2. 在 Xcode 中选择你的设备
3. 点击 "Run" (⌘R)
4. 首次需要在 iPhone 设置 → 通用 → VPN与设备管理 中信任开发者

> ⚠️ 此方法需要每 7 天重新部署

### 方法 2: AltStore

1. 在 Mac 上安装 AltServer
2. 在 iPhone 上安装 AltStore
3. 使用 Xcode 导出 `.ipa` (Product → Archive → Distribute App → Ad Hoc)
4. 通过 AltStore 安装 IPA

## 功能特性

- 📅 日历式日期选择
- 📹 视频列表展示
- ▶️ 全屏视频播放
- 🌙 深色模式
- 🚗 特斯拉风格 UI
