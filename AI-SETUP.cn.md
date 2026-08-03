# AirCoding 环境配置说明书（AI 执行者专用）

> **本文档的用途**：供 Claude 类 AI 编程助手（Claude Code、WorkBuddy、Cursor、Windsurf 等）读取并执行，完成 AirCoding 项目从零到可运行的全部环境配置。
> **执行原则**：严格按步骤顺序执行；每个步骤都包含「命令 → 预期输出 → 失败恢复」三段式；不要跳过验证环节。
> 🌍 English version: [AI-SETUP.md](AI-SETUP.md)

---

## 0. 项目是什么

AirCoding 是一个 **Windows 桌面应用**：通过摄像头实时识别手部/面部动作，将手势映射为键盘按键和语音输入热键，用于 vibecoding 场景的快捷操作。

| 维度 | 说明 |
|------|------|
| 技术栈 | Python + MediaPipe（手势识别）+ PySide6/Qt6（GUI）+ OpenCV（摄像头）+ pynput（键盘注入） |
| 运行形态 | 常驻后台的悬浮面板 + 系统托盘图标，非 CLI 工具 |
| 硬件依赖 | **必须有可用摄像头**（笔记本内置或 USB 外接均可） |
| 平台限制 | **仅支持 Windows 10/11**（依赖 pywin32、uiautomation 等 Windows 专有 API，无法移植到 macOS/Linux） |

---

## 1. 执行前提检查（Gate 0，不满足则停止）

### 1.1 操作系统

- **必须**：Windows 10 或 Windows 11（64 位）
- 验证命令：`cmd /c ver`，预期输出包含 `Windows` 且版本号 ≥ 10.0

### 1.2 Python 版本（关键约束）

- **必须**：Python **3.10 / 3.11 / 3.12** 三者之一
- **禁止**：Python 3.13+ —— MediaPipe 尚未发布 3.13 的兼容包，安装必然失败
- **禁止**：Python 3.9 及以下 —— PySide6 ≥6.5 要求 3.9+，且项目代码使用了新版语法

验证命令（在项目根目录执行）：

```powershell
python -c "import sys; v=sys.version_info[:2]; print(v); exit(0 if (3,10)<=v<(3,13) else 1)"
```

预期输出：`(3, 10)`、`(3, 11)` 或 `(3, 12)`，退出码 0。

**失败恢复**：若版本不符，引导用户从 https://www.python.org/downloads/ 安装 3.12.x（推荐），安装时勾选 **Add Python to PATH**。若系统装有 py launcher，后续命令可用 `py -3.12` 替代 `python`。

### 1.3 硬件

- 摄像头设备存在且未被其他程序独占（验证方式见第 5 节运行后检查）。

---

## 2. 关键约束与已知陷阱（执行前必读）

以下三条是本项目的"血泪教训"，违反任意一条都会导致运行失败或难以排查的隐性故障：

### 2.1 MediaPipe 版本上限（最重要的陷阱）

- `requirements.txt` 中已锁定 `mediapipe>=0.10.0,<0.10.15`，**不要放宽此约束**。
- **原因**：MediaPipe 0.10.15 起移除了 `mediapipe.python.solutions` 旧 API，而本项目代码依赖该 API。
- **症状**（如果装了 0.10.15+）：应用能启动、UI 正常、摄像头指示灯亮，但**预览画面空白无视频**；日志（`%APPDATA%\AirCoding\logs\aircoding.log`）中出现 `No module named 'mediapipe.python'`。
- **修复**：`.venv_run\Scripts\python.exe -m pip install "mediapipe>=0.10.0,<0.10.15" --force-reinstall`

### 2.2 虚拟环境目录名固定为 `.venv_run`

- 启动脚本 `start.bat` 硬编码了路径 `.venv_run\Scripts\pythonw.exe`。
- 创建虚拟环境时**必须使用此目录名**，否则启动脚本找不到解释器。

### 2.3 `start.bat` 的规范（仓库中唯一的 bat 启动器）

- `start.bat` 是仓库中唯一的批处理文件（启动器，非安装器；`安装.bat` 已移除）。
- 它是纯 ASCII 脚本（无中文输出），因此**没有编码约束**；但修改时仍需保持：
  - 行尾：**CRLF**（Windows 风格）
  - 硬编码路径 `.venv_run\Scripts\pythonw.exe` 不可改动
- 若未来在其中加入中文输出，则必须满足 GBK（CP936）编码，转换命令：
  ```powershell
  $p="start.bat的完整路径"; $t=[IO.File]::ReadAllText($p,[Text.Encoding]::UTF8); $t=($t -replace "`r`n","`n") -replace "`n","`r`n"; [IO.File]::WriteAllText($p,$t,[Text.Encoding]::GetEncoding(936))
  ```

### 2.4 海外用户的 pip 源（开源后新增）

- 安装依赖时：海外用户直接用 PyPI 官方默认源，无需加 `-i` 参数；国内用户追加 `-i https://pypi.tuna.tsinghua.edu.cn/simple`。
- 不要在任何文档或脚本中把清华镜像写死为唯一来源。

### 2.5 UI 语言切换（开源后新增）

- 程序内置中英文切换，**默认英文**（`ui.language: "en"`）。
- 切换入口：设置 → 界面 → 语言；修改后**重启应用生效**。
- 国际化实现：`src/core/i18n.py` 的 `t()` 函数，英文原文即 key，中文在翻译表中；未收录字符串回退英文。

---

## 3. 获取代码

```bash
git clone https://github.com/mushi888/AirCoding.git
cd AirCoding
```

若用户已提供本地项目目录，跳过克隆，直接进入项目根目录（目录下应能看到 `main.py`、`requirements.txt`、`start.bat`）。

---

## 4. 环境安装（唯一路径）

> `安装.bat` 已移除，由本说明书取代——**AI 执行者本身就是安装器**。严格按以下步骤执行，它们覆盖了原脚本的全部动作（建 venv、选 pip 源、装依赖、验证）。

### 步骤 1：创建虚拟环境（目录名必须是 `.venv_run`）

```powershell
python -m venv .venv_run
```

### 步骤 2：升级 pip

```powershell
.venv_run\Scripts\python.exe -m pip install --upgrade pip
```

### 步骤 3：安装全部依赖（约 400MB，耗时 3~15 分钟取决于网络）

```powershell
.venv_run\Scripts\python.exe -m pip install -r requirements.txt --retries 5 --timeout 120
# 海外用户直接用默认源；国内用户追加 -i https://pypi.tuna.tsinghua.edu.cn/simple
```

**步骤 3 失败恢复**：pip 中断后可直接重跑同一命令，pip 会跳过已完成的包（幂等）。

---

## 5. 安装验证（Gate 1，全部通过才算装好）

### 5.1 依赖导入验证

```powershell
.venv_run\Scripts\python.exe -c "import mediapipe, cv2, numpy, PySide6, pynput, win32gui, psutil, uiautomation, yaml; print('deps OK, mediapipe =', mediapipe.__version__)"
```

- 预期输出：`deps OK, mediapipe = 0.10.14`（版本号必须在 `0.10.x` 且 `x < 15`）
- 若 mediapipe 版本 ≥ 0.10.15 → 回到 2.1 节执行降级修复

### 5.2 MediaPipe API 兼容性验证（本项目特有，必须执行）

```powershell
.venv_run\Scripts\python.exe -c "from mediapipe.python.solutions import hands, face_mesh; h=hands.Hands(); f=face_mesh.FaceMesh(); h.close(); f.close(); print('MediaPipe legacy API OK')"
```

- 预期输出：`MediaPipe legacy API OK`
- 预期副作用：首次执行时 MediaPipe 会自动下载内置模型（hands/face_mesh），属正常现象
- 若报 `ModuleNotFoundError: No module named 'mediapipe.python'` → mediapipe 版本过高，执行 2.1 节修复

### 5.3 单元测试

```powershell
.venv_run\Scripts\python.exe -m pytest tests/ -q
```

- 预期输出：`46 passed`（允许出现警告，不允许出现 failed/error）

---

## 6. 启动应用

| 方式 | 命令 | 适用场景 |
|------|------|----------|
| 静默启动（推荐） | 双击 `start.bat` | 日常使用，无命令行窗口 |
| 开发模式 | `.venv_run\Scripts\python.exe main.py` | 调试排错，控制台可见实时日志 |
| pythonw 直启 | `.venv_run\Scripts\pythonw.exe -B main.py` | 等价于start.bat |

**必须在项目根目录执行**（代码使用相对导入 `from src.xxx`，工作目录错误会报 `ModuleNotFoundError: No module named 'src'`）。

---

## 7. 运行后验收（Gate 2，确认程序真的在正常工作）

启动后按以下清单逐项确认：

1. **UI 出现**：屏幕右下角（默认位置）出现半透明悬浮面板。
2. **摄像头激活**：摄像头指示灯亮起。
3. **视频预览正常**：面板预览区显示摄像头画面（骨架叠加）。**若画面空白但指示灯亮 → 90% 是 mediapipe 版本问题（见 2.1）**。
4. **首次启动引导**：首次运行会弹出新手引导（Onboarding），完成后写入配置。
5. **手势可用**：对照下表做手势，观察面板灯效变化与按键注入效果。

| 手势 | 触发动作 |
|------|----------|
| 👌 OK 手势 | Enter |
| ✋ 张开手掌 | Escape |
| ✌️ 剪刀手 | Ctrl+Z |
| 🤏 捏合（保持 1.5s） | 切换 自动批准/手动确认 模式 |
| 🤙 打电话手势 | 检测前台 AI 软件并注入其语音输入热键 |

6. **全局热键**：`Ctrl+Alt+K` 可显示/隐藏面板。

### 识别不准时

打开设置（面板 ⚙️ 按钮）执行**手势校准**（指纹式注册：6 种手势各采集 30 帧）。校准数据保存于 `%APPDATA%\AirCoding\calibration_profile.json`，并会在使用中持续自适应。

---

## 8. 故障诊断表（症状 → 原因 → 处置）

| 症状 | 最可能原因 | 处置 |
|------|-----------|------|
| UI 正常 + 摄像头灯亮 + 画面空白 | mediapipe ≥ 0.10.15（API 被移除） | 按 2.1 节降级 |
| 日志出现 `No module named 'mediapipe.python'` | 同上 | 按 2.1 节降级 |
| 双击start.bat 报 `Python venv not found` | 虚拟环境目录名不是 `.venv_run` 或未创建 | 按第 4 节重建，目录名必须是 `.venv_run` |
| start.bat 乱码/报错 | 文件损坏或行尾错误 | 按 2.3 节重新保存为 CRLF 行尾 |
| 启动报 `No module named 'src'` | 未在项目根目录执行 | `cd` 到项目根目录再运行 |
| pip 安装 mediapipe 找不到匹配版本 | Python 是 3.13+ | 换装 Python 3.10~3.12（见 1.2） |
| 摄像头打不开/灯不亮 | 被其他程序（腾讯会议/微信等）独占 | 关闭占用程序后重启应用；应用本身也支持占用释放后自动恢复 |
| 手势无反应 | 未校准或手在有效区域外 | 手保持在预览虚线圆圈内；执行手势校准 |
| 单元测试失败 | 环境污染（曾反复装卸包） | 删除 `.venv_run` 后按第 4 节全新安装 |

**日志位置**：`%APPDATA%\AirCoding\logs\aircoding.log`（无 APPDATA 环境变量时回退到项目目录 `logs/`）。排错第一步永远是读日志末尾 50 行。

---

## 9. 运行时数据位置（排错与备份用）

| 数据 | 路径 | 说明 |
|------|------|------|
| 用户配置 | `%APPDATA%\AirCoding\user_config.yaml` | 覆盖 `config/default_config.yaml` 的同名键 |
| 校准档案 | `%APPDATA%\AirCoding\calibration_profile.json` | 手势校准特征与阈值 |
| 运行日志 | `%APPDATA%\AirCoding\logs\aircoding.log` | 主要排错依据 |
| 出厂配置 | 项目内 `config/default_config.yaml` | 不要修改，改用户配置 |

**恢复出厂状态**：删除 `%APPDATA%\AirCoding\` 整个目录即可（配置、校准、日志全部重置），不影响项目代码。

---

## 10. 辅助工具

```powershell
# 真实摄像头手势测试（采集 30 帧并输出识别质量报告）
.venv_run\Scripts\python.exe test_runner.py --frames 30

# 全自动模式（无需按 Enter）
.venv_run\Scripts\python.exe test_runner.py --frames 30 --auto

# 分析历史测试日志
.venv_run\Scripts\python.exe test_runner.py --analyze <日志文件路径>
```

---

## 11. 项目结构速查

```
AirCoding/
├── main.py                  # 入口：模块初始化 + 信号连接 + Qt 事件循环
├── test_runner.py           # 真实摄像头测试工具
├── start.bat                  # 静默启动（硬编码 .venv_run 路径）
├── AI-SETUP.md              # 本说明书（AI 执行者的环境配置指南）
├── requirements.txt         # 依赖清单（mediapipe 上限 <0.10.15，勿动）
├── config/default_config.yaml  # 出厂配置（手势映射/阈值/AI软件注册表/灯效）
├── resources/               # 应用图标
├── src/
│   ├── core/                # 枚举、配置管理、状态机
│   ├── camera/              # 摄像头采集（独立线程 10fps）、图像预处理
│   ├── recognition/         # MediaPipe 推理、手势分类、校准、表情识别
│   ├── action/              # 键盘注入、AI软件检测、自动批准
│   ├── ui/                  # 主窗口、隐私预览、设置、引导、灯效
│   └── utils/               # 日志、音频反馈
└── tests/                   # pytest 单元测试（46 个用例）
```

---

## 12. 执行完成判定（Definition of Done）

AI 执行者完成本说明书后，应能回答以下全部为"是"：

- [ ] Python 版本在 3.10~3.12 区间内
- [ ] `.venv_run` 存在且 `requirements.txt` 全部依赖安装成功
- [ ] mediapipe 版本 < 0.10.15，且 `mediapipe.python.solutions` 可导入
- [ ] `pytest tests/ -q` 全部通过（46 passed）
- [ ] 应用启动后 UI 显示、摄像头灯亮、**预览画面有视频**
- [ ] 至少一种手势（建议 ✋）能触发对应键盘动作

全部满足 → 环境配置完成，程序可正常使用。任意一项不满足 → 按第 8 节故障诊断表定位处置。
