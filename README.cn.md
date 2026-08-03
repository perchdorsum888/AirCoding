# AirCoding

通过摄像头识别手势，用空气手势驱动键盘操作和语音输入。无需穿戴设备，纯视觉识别，适用于 vibecoding 场景下的快捷操作。

> 🌍 English version: [README.md](README.md)
>
> **语言支持**：界面内置中英文切换（默认英文），设置 → 界面 → 语言 中切换后重启生效。

## 支持的手势

| 手势 | 动作 | 说明 |
|------|------|------|
| 👌 OK手势 | Enter | 确认操作 |
| ✋ 张开手掌 | Escape | 取消操作 |
| ✌️ 剪刀手 | Ctrl+Z | 撤销 |
| 🤏 捏合 | 模式切换 | 切换自动批准/手动确认 |
| 🤙 打电话 | 语音输入 | 检测前台AI软件并注入语音快捷键 |

## 技术栈

- **Python 3.10~3.12**
- **MediaPipe** — 手部21点 + 面部468点实时landmark检测
- **PySide6 (Qt6)** — GUI框架，无边框透明置顶窗口
- **OpenCV** — 摄像头采集与图像预处理
- **pynput** — 键盘事件注入
- **pywin32 / psutil** — Windows前台窗口检测与进程识别
- **PyYAML** — 配置文件管理

## 目录结构

```
aircoding/
├── main.py                      # 应用入口，启动流程与信号连接
├── test_runner.py               # 测试程序（真实摄像头+日志分析）
├── start.bat                      # Windows启动脚本（pythonw静默启动）
├── requirements.txt             # Python依赖
├── config/
│   └── default_config.yaml      # 默认配置（手势映射、阈值、AI软件注册表）
├── resources/
│   ├── aircoding.ico            # 应用图标（多尺寸）
│   └── aircoding.png            # 应用图标PNG
├── src/
│   ├── core/                    # 核心模块
│   │   ├── enums.py             # 枚举定义（手势类型、灯效状态、系统模式）
│   │   ├── config_manager.py    # 配置管理器（默认配置+用户配置合并）
│   │   ├── gesture_config.py    # 手势映射默认配置
│   │   └── state_machine.py     # 状态机（灯效状态转换）
│   ├── camera/                  # 摄像头模块
│   │   ├── camera_manager.py    # 摄像头采集管理（独立线程、自动重连、占用检测）
│   │   └── image_processor.py   # 图像预处理（亮度检测、降噪）
│   ├── recognition/             # 识别模块
│   │   ├── recognition_engine.py # 识别引擎（多线程推理、手势确认、有效区域）
│   │   ├── hand_classifier.py   # 手势分类器（per-finger阈值、5种手势）
│   │   ├── phone_call_detector.py # 打电话手势检测（拇指+小指伸直）
│   │   ├── gesture_validator.py # 手势验证器（多帧确认、冷却时间、保持计时）
│   │   ├── calibrator.py        # 校准器（注册采集、特征提取、阈值计算、持续适配）
│   │   └── face_expression.py   # 面部表情识别（挑眉检测）
│   ├── action/                  # 动作模块
│   │   ├── gesture_mapper.py    # 手势→键盘映射
│   │   ├── keyboard_injector.py # 键盘注入（pynput优先，SendInput备选）
│   │   ├── ai_software_detector.py # AI软件检测（前台窗口进程匹配）
│   │   └── auto_approval.py     # 自动批准控制器
│   ├── ui/                      # UI模块
│   │   ├── main_window.py       # 主窗口（无边框置顶、托盘、手势校准）
│   │   ├── privacy_preview.py   # 隐私预览（骨架绘制、有效区域、加载引导）
│   │   ├── settings_dialog.py   # 设置对话框（手势快捷键、AI软件管理、校准）
│   │   ├── onboarding.py        # 新手引导
│   │   ├── light_effect_widget.py # 灯效动画
│   │   └── toast.py             # Toast提示
│   └── utils/
│       ├── logger.py            # 日志系统（文件+控制台）
│       └── audio.py             # 音频反馈
└── tests/                       # 单元测试
    ├── test_hand_classifier.py
    ├── test_gesture_validator.py
    └── test_state_machine.py
```

## 核心功能

### 手势识别

- 基于 MediaPipe 手部21点landmark，通过手指伸直/弯曲比例判定手势
- 支持 per-finger 独立阈值（校准后每根手指有独立的伸直/弯曲判定标准）
- 双阈值滞回方案（伸直阈值/弯曲阈值/灰区），减少边界抖动
- 防误触黑名单（检查手指间距、方向等辅助条件）

### 手势校准

- 引导用户逐一做出手势，每个手势采集30帧×2角度
- 提取8个特征（5指ratio、拇指方向、拇指食指距离、食指中指夹角）
- 计算per-finger阈值并持久化到 `%APPDATA%/AirCoding/calibration_profile.json`
- 运行时持续适配（每100次成功识别后自动更新阈值）

### 打电话手势与语音输入

- 上升沿（手势出现）→ 检测前台AI软件 → 注入语音输入热键 → 开始录音
- 下降沿（手势消失）→ 再次注入热键 → 停止录音
- 支持的AI软件：WorkBuddy、豆包、飞书、微信、企业微信 + 自定义添加

### 摄像头管理

- 独立线程10fps采集，帧队列缓冲
- 摄像头被其他程序占用时自动释放，释放后自动恢复
- 多人检测：画面中出现第二人时暂停手势识别

### 有效区域

- 以人脸为中心的圆形区域（人脸宽度×1.625为半径）
- 手部在圆形内才会被识别，圆形外被忽略
- 预览窗口绘制虚线圆形引导框

### 启动优化

- UI窗口优先显示（~0.6s）
- MediaPipe导入与摄像头打开在后台并行（~4s完成）
- QTimer轮询检查后台初始化完成

## 安装与运行

### 环境要求

- Windows 10/11
- Python 3.10~3.12（MediaPipe 暂不支持 3.13+）
- 摄像头

### 推荐：AI 辅助配置（适合 AI 工具用户）

AirCoding 专为 AI 编程助手（Claude Code、WorkBuddy、Cursor、Windsurf 等）环境配置而设计。仓库内置 [AI-SETUP.md](AI-SETUP.cn.md) —— 一份写给 AI 执行者的分步环境配置说明书。

1. **下载项目到本地** —— `git clone https://github.com/mushi888/AirCoding.git`（或下载 ZIP 解压）
2. **用 AI 软件导入该文件夹，新建为本地任务** —— 将项目根目录（包含 `main.py` 的文件夹）作为任务目录
3. **让 AI 读取 `AI-SETUP.md` 并自动配置环境** —— AI 将按说明书执行：检查 Python 3.10~3.12 → 创建 `.venv_run` 虚拟环境 → 安装全部依赖（约 400MB）→ 验证安装（含单元测试）
4. **配置完成后，双击 `start.bat` 启动应用** —— 允许摄像头权限即可使用

> 💡 **写给 AI 执行者**：[AI-SETUP.md](AI-SETUP.cn.md) 包含全部所需信息——前提检查（Gate 0）、安装步骤、验证关卡、故障诊断表、验收清单。请严格按顺序执行。

### 手动安装（无 AI 助手时）

```bash
# 克隆仓库
git clone https://github.com/mushi888/AirCoding.git
cd AirCoding

# 创建虚拟环境（目录名必须是 .venv_run）
python -m venv .venv_run

# 安装依赖
.venv_run\Scripts\pip install -r requirements.txt
# 海外用户直接用默认源；国内用户追加 -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 运行

```bash
# 方式1：启动脚本（静默，无命令行窗口）—— 推荐
start.bat

# 方式2：直接运行
.venv_run\Scripts\pythonw.exe main.py

# 方式3：开发模式（显示命令行窗口和日志）
.venv_run\Scripts\python.exe main.py
```

### 测试

```bash
# 单元测试
.venv_run\Scripts\python.exe -m pytest tests/ -q

# 手势测试程序（真实摄像头）
.venv_run\Scripts\python.exe test_runner.py --frames 30

# 分析测试日志
.venv_run\Scripts\python.exe test_runner.py --analyze <日志文件路径>
```

## 配置

### 配置文件位置

| 文件 | 路径 | 说明 |
|------|------|------|
| 默认配置 | `config/default_config.yaml` | 出厂配置，勿修改 |
| 用户配置 | `%APPDATA%/AirCoding/user_config.yaml` | 用户自定义配置 |
| 校准档案 | `%APPDATA%/AirCoding/calibration_profile.json` | 手势校准数据 |
| 日志 | `%APPDATA%/AirCoding/logs/aircoding.log` | 运行日志 |

### 全局热键

- **Ctrl+Alt+K** — 显示/隐藏面板

## 许可证

MIT License

Copyright (c) 2026 AirCoding

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
