"""设置面板模块。

提供灵敏度滑块、确认帧数/保持时间配置、灯效开关、
面板位置/透明度、AI软件热键配置、校准入口、左右手镜像、隐私声明。

修改配置后调用 ConfigManager.set() 并触发 config_changed 信号。
"""

from typing import Optional

from src.core.config_manager import ConfigManager
from src.core.i18n import t
from src.utils.logger import get_logger

_logger = get_logger("SettingsDialog")

try:
    from PySide6.QtWidgets import (
        QDialog,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QSlider,
        QCheckBox,
        QComboBox,
        QPushButton,
        QGroupBox,
        QFormLayout,
        QSpinBox,
        QDoubleSpinBox,
        QTabWidget,
        QWidget,
        QMessageBox,
    )
    from PySide6.QtCore import Qt, Signal
    _HAS_QT = True
except ImportError:
    _HAS_QT = False
    _logger.warning("PySide6 not installed, settings dialog unavailable")


class SettingsDialog(QDialog if _HAS_QT else object):
    """设置对话框。

    提供多标签页配置界面，修改后通知主窗口热更新。

    Signals:
        config_changed: 配置变更信号，携带新的配置字典。
    """

    config_changed = Signal(dict) if _HAS_QT else None

    def __init__(
        self,
        config_manager: ConfigManager,
        parent=None,
    ) -> None:
        """初始化设置对话框。

        Args:
            config_manager: 配置管理器。
            parent: 父控件。
        """
        if _HAS_QT:
            super().__init__(parent)
            self.setWindowTitle("AirCoding - " + t("Settings"))
            self.setFixedSize(480, 560)

        self._config_manager = config_manager

        if _HAS_QT:
            self._setup_ui()

    def _setup_ui(self) -> None:
        """设置UI布局。"""
        layout = QVBoxLayout(self)

        # 标签页
        tab_widget = QTabWidget()

        # === 快捷键设置标签页 ===
        tab_widget.addTab(self._create_hotkey_tab(), t("Hotkeys"))

        # === 识别设置标签页 ===
        tab_widget.addTab(self._create_recognition_tab(), t("Recognition"))

        # === 防误触设置标签页 ===
        tab_widget.addTab(self._create_validation_tab(), t("Validation"))

        # === UI设置标签页 ===
        tab_widget.addTab(self._create_ui_tab(), t("Interface"))

        # === AI软件设置标签页 ===
        tab_widget.addTab(self._create_ai_tab(), t("AI Software"))

        # === 校准标签页 ===
        tab_widget.addTab(self._create_calibration_tab(), t("Calibration"))

        layout.addWidget(tab_widget)

        # 底部按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        reset_btn = QPushButton(t("Reset Defaults"))
        reset_btn.clicked.connect(self._reset_to_default)
        btn_layout.addWidget(reset_btn)

        save_btn = QPushButton(t("Save"))
        save_btn.clicked.connect(self._save_config)
        btn_layout.addWidget(save_btn)

        cancel_btn = QPushButton(t("Cancel"))
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    def _create_hotkey_tab(self) -> QWidget:
        """创建快捷键自定义标签页。

        每个手势一行，下拉选择绑定的快捷键。
        """
        widget = QWidget()
        layout = QFormLayout(widget)

        # 预设快捷键选项
        self._hotkey_options = [
            (t("(Internal logic)"), []),
            ("Enter", ["enter"]),
            ("Escape", ["escape"]),
            ("Space", ["space"]),
            ("Tab", ["tab"]),
            ("Y", ["y"]),
            ("N", ["n"]),
            ("Ctrl+C", ["ctrl", "c"]),
            ("Ctrl+V", ["ctrl", "v"]),
            ("Ctrl+Z", ["ctrl", "z"]),
            ("Ctrl+S", ["ctrl", "s"]),
            ("Ctrl+A", ["ctrl", "a"]),
            ("Ctrl+X", ["ctrl", "x"]),
            ("Ctrl+D", ["ctrl", "d"]),
            ("Ctrl+W", ["ctrl", "w"]),
            ("Ctrl+F", ["ctrl", "f"]),
            ("Alt+Tab", ["alt", "tab"]),
            ("Alt+F4", ["alt", "f4"]),
            ("Delete", ["delete"]),
            ("Backspace", ["backspace"]),
        ]

        # 从配置加载当前映射
        from src.core.gesture_config import DEFAULT_GESTURE_MAPPINGS
        mappings = DEFAULT_GESTURE_MAPPINGS
        self._hotkey_combos = {}

        # 手势快捷键（不区分左右手）
        gesture_label = QLabel(t("Gesture Hotkeys"))
        gesture_label.setStyleSheet("font-weight: bold; color: #4A90D9;")
        layout.addRow(gesture_label)

        for m in mappings:
            if m.gesture.value == "phone_call":
                label_text = f"{m.emoji} " + t("Voice Input (Dynamic Hotkey)")
                combo = QComboBox()
                combo.setEnabled(False)
                combo.addItem(t("Auto-detected from AI software"))
                layout.addRow(label_text, combo)
                continue
            if m.gesture.value == "pinch":
                label_text = f"{m.emoji} " + t("Mode Switch")
                combo = QComboBox()
                combo.setEnabled(False)
                combo.addItem(t("Internal logic (mode switch)"))
                layout.addRow(label_text, combo)
                continue

            label_text = f"{m.emoji} {m.action_name}"
            combo = QComboBox()
            for display, keys in self._hotkey_options:
                combo.addItem(display)
                if keys == m.key_sequence:
                    combo.setCurrentIndex(combo.count() - 1)
            self._hotkey_combos[m.gesture.value] = combo
            layout.addRow(label_text, combo)

        return widget

    def _create_recognition_tab(self) -> QWidget:
        """创建识别设置标签页。"""
        widget = QWidget()
        layout = QFormLayout(widget)

        # 灵敏度滑块
        sensitivity_label = QLabel(t("Recognition Sensitivity"))
        self._sensitivity_slider = QSlider(Qt.Horizontal)
        self._sensitivity_slider.setRange(50, 100)
        current_conf = self._config_manager.get("recognition.thresholds.confidence", 0.7)
        self._sensitivity_slider.setValue(int(current_conf * 100))
        self._sensitivity_slider.valueChanged.connect(
            lambda v: sensitivity_label.setText(f"{t('Recognition Sensitivity')} ({v}%)")
        )
        layout.addRow(sensitivity_label)
        layout.addRow(self._sensitivity_slider)

        # 单手模式
        self._single_hand_check = QCheckBox(t("Prioritize single hand"))
        self._single_hand_check.setChecked(
            self._config_manager.get("recognition.single_hand_mode", True)
        )
        layout.addRow(self._single_hand_check)

        # 手指伸直阈值
        self._finger_extended_spin = QDoubleSpinBox()
        self._finger_extended_spin.setRange(0.1, 1.0)
        self._finger_extended_spin.setSingleStep(0.05)
        self._finger_extended_spin.setValue(
            self._config_manager.get("recognition.thresholds.finger_extended", 0.5)
        )
        layout.addRow(t("Finger Extended Threshold:"), self._finger_extended_spin)

        # 手指弯曲阈值
        self._finger_curled_spin = QDoubleSpinBox()
        self._finger_curled_spin.setRange(0.1, 1.0)
        self._finger_curled_spin.setSingleStep(0.05)
        self._finger_curled_spin.setValue(
            self._config_manager.get("recognition.thresholds.finger_curled", 0.3)
        )
        layout.addRow(t("Finger Curled Threshold:"), self._finger_curled_spin)

        return widget

    def _create_validation_tab(self) -> QWidget:
        """创建防误触设置标签页。"""
        widget = QWidget()
        layout = QFormLayout(widget)

        # 确认帧数
        self._confirm_frames_spin = QSpinBox()
        self._confirm_frames_spin.setRange(1, 10)
        self._confirm_frames_spin.setValue(
            self._config_manager.get("validation.confirm_frames", 3)
        )
        layout.addRow(t("Confirm Frames:"), self._confirm_frames_spin)

        # 冷却时间
        self._cooldown_spin = QSpinBox()
        self._cooldown_spin.setRange(100, 3000)
        self._cooldown_spin.setSingleStep(100)
        self._cooldown_spin.setSuffix(" ms")
        self._cooldown_spin.setValue(
            self._config_manager.get("validation.cooldown_ms", 500)
        )
        layout.addRow(t("Cooldown:"), self._cooldown_spin)

        # 打电话保持时间
        self._phone_hold_spin = QSpinBox()
        self._phone_hold_spin.setRange(0, 3000)
        self._phone_hold_spin.setSingleStep(100)
        self._phone_hold_spin.setSuffix(" ms")
        self._phone_hold_spin.setValue(
            self._config_manager.get("validation.hold_durations.phone_call", 300)
        )
        layout.addRow(t("Phone Call Hold:"), self._phone_hold_spin)

        # 捏合保持时间
        self._pinch_hold_spin = QSpinBox()
        self._pinch_hold_spin.setRange(0, 5000)
        self._pinch_hold_spin.setSingleStep(100)
        self._pinch_hold_spin.setSuffix(" ms")
        self._pinch_hold_spin.setValue(
            self._config_manager.get("validation.hold_durations.pinch", 1500)
        )
        layout.addRow(t("Pinch Hold:"), self._pinch_hold_spin)

        return widget

    def _create_ui_tab(self) -> QWidget:
        """创建界面设置标签页。"""
        widget = QWidget()
        layout = QFormLayout(widget)

        # 语言切换
        self._language_combo = QComboBox()
        self._language_combo.addItem("English", "en")
        self._language_combo.addItem("简体中文", "zh")
        current_lang = self._config_manager.get("ui.language", "en")
        idx = self._language_combo.findData(current_lang)
        self._language_combo.setCurrentIndex(idx if idx >= 0 else 0)
        layout.addRow(t("Language:"), self._language_combo)

        # 面板位置
        self._position_combo = QComboBox()
        self._position_combo.addItems([
            t("Top Left"), t("Top Right"), t("Bottom Left"),
            t("Bottom Right"), t("Center"),
        ])
        current_pos = self._config_manager.get("ui.panel_position", "bottom_right")
        pos_map = {
            "top_left": 0, "top_right": 1,
            "bottom_left": 2, "bottom_right": 3, "center": 4,
        }
        self._position_combo.setCurrentIndex(pos_map.get(current_pos, 3))
        layout.addRow(t("Panel Position:"), self._position_combo)

        # 透明度
        self._opacity_slider = QSlider(Qt.Horizontal)
        self._opacity_slider.setRange(50, 100)
        self._opacity_slider.setValue(
            int(self._config_manager.get("ui.panel_opacity", 0.85) * 100)
        )
        layout.addRow(t("Panel Opacity:"), self._opacity_slider)

        # 灯效开关
        self._light_effect_check = QCheckBox(t("Enable Light Effect"))
        self._light_effect_check.setChecked(
            self._config_manager.get("ui.light_effect_enabled", True)
        )
        layout.addRow(self._light_effect_check)

        # 声音反馈
        self._sound_check = QCheckBox(t("Enable Sound Feedback"))
        self._sound_check.setChecked(
            self._config_manager.get("ui.sound_feedback_enabled", True)
        )
        layout.addRow(self._sound_check)

        # 镜像预览
        self._mirror_check = QCheckBox(t("Mirror Preview"))
        self._mirror_check.setChecked(
            self._config_manager.get("ui.mirror_preview", False)
        )
        layout.addRow(self._mirror_check)

        # 跟随前台显示器
        self._follow_monitor_check = QCheckBox(t("Follow AI Software Monitor"))
        self._follow_monitor_check.setChecked(
            self._config_manager.get("ui.follow_foreground_monitor", True)
        )
        layout.addRow(self._follow_monitor_check)

        # 隐私声明
        privacy_label = QLabel(
            t("Privacy Notice: camera frames are processed and displayed "
              "locally only. No image or video data is uploaded to the network.")
        )
        privacy_label.setWordWrap(True)
        privacy_label.setStyleSheet("color: #8E8E93; font-size: 11px;")
        layout.addRow(privacy_label)

        return widget

    def _create_ai_tab(self) -> QWidget:
        """创建AI软件设置标签页（可编辑热键+添加自定义软件）。"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 常用热键选项
        self._hotkey_options = [
            ("Ctrl+D", ["ctrl", "d"]),
            ("Alt+D", ["alt", "d"]),
            ("Ctrl+Shift+V", ["ctrl", "shift", "v"]),
            ("Ctrl+Space", ["ctrl", "space"]),
            ("Alt+Space", ["alt", "space"]),
            ("F1", ["f1"]),
            ("F2", ["f2"]),
            ("Ctrl+E", ["ctrl", "e"]),
            ("Ctrl+J", ["ctrl", "j"]),
        ]

        self._ai_hotkey_combos = {}
        self._ai_tab_layout = layout
        registry = self._config_manager.get_ai_software_registry()

        # AI软件分组
        ai_label = QLabel(t("AI Software"))
        ai_label.setStyleSheet("font-weight: bold; color: #4A90D9;")
        layout.addWidget(ai_label)

        for name, info in registry.items():
            if info.get("category", "ai") != "ai":
                continue
            self._add_software_row(layout, name, info)

        # IM软件分组
        im_label = QLabel("\n" + t("IM Software"))
        im_label.setStyleSheet("font-weight: bold; color: #4A90D9;")
        layout.addWidget(im_label)

        for name, info in registry.items():
            if info.get("category", "ai") != "im":
                continue
            self._add_software_row(layout, name, info)

        # 自定义软件分组
        self._custom_label = QLabel("\n" + t("Custom Software"))
        self._custom_label.setStyleSheet("font-weight: bold; color: #4A90D9;")
        layout.addWidget(self._custom_label)

        for name, info in registry.items():
            if info.get("category", "ai") != "custom":
                continue
            self._add_software_row(layout, name, info)

        # 添加按钮
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("+ " + t("Add Custom Software"))
        add_btn.clicked.connect(self._add_custom_software)
        btn_layout.addWidget(add_btn)
        layout.addLayout(btn_layout)

        layout.addStretch()
        return widget

    def _add_software_row(self, layout, name: str, info: dict) -> None:
        """添加一个软件配置行（名称+热键下拉+进程名）。"""
        display_name = info.get("display_name", name)
        hotkey = info.get("voice_input_hotkey", [])
        process_names = info.get("process_names", [])

        group = QGroupBox(display_name)
        group_layout = QFormLayout(group)

        # 热键下拉
        combo = QComboBox()
        combo.addItem(t("Not configured (disabled)"))
        for display, keys in self._hotkey_options:
            combo.addItem(display)
            if keys == hotkey:
                combo.setCurrentIndex(combo.count() - 1)
        group_layout.addRow(t("Voice Input Hotkey:"), combo)
        self._ai_hotkey_combos[name] = combo

        # 进程名显示
        process_label = QLabel(", ".join(process_names) if process_names else t("Not configured"))
        process_label.setStyleSheet("color: rgba(255,255,255,100); font-size: 11px;")
        group_layout.addRow(t("Process Name:"), process_label)

        layout.addWidget(group)

    def _add_custom_software(self) -> None:
        """添加自定义软件对话框（支持捕获前台进程+录制自定义热键）。"""
        from PySide6.QtWidgets import (
            QDialog, QLineEdit, QLabel, QDialogButtonBox, QFormLayout,
            QPushButton, QHBoxLayout, QComboBox, QMessageBox,
        )

        dialog = QDialog(self)
        dialog.setWindowTitle(t("Add Custom Software"))
        dialog.setFixedSize(450, 380)
        dialog_layout = QFormLayout(dialog)

        # 显示名称
        display_edit = QLineEdit()
        display_edit.setPlaceholderText(t("e.g. My App"))
        dialog_layout.addRow(t("Display Name:"), display_edit)

        # 进程名 — 支持手动输入或点击按钮捕获前台窗口进程
        process_edit = QLineEdit()
        process_edit.setPlaceholderText(t("Click the button to capture the foreground window process"))

        capture_btn = QPushButton(t("Capture Foreground"))
        captured_name = [None]  # 存储捕获的进程名

        def _capture_foreground():
            """捕获当前前台窗口的进程名。"""
            try:
                import win32gui
                import win32process
                import psutil

                hwnd = win32gui.GetForegroundWindow()
                if hwnd == 0:
                    # 对话框可能遮住了前台窗口，先最小化对话框
                    dialog.showMinimized()
                    import time
                    time.sleep(0.5)
                    hwnd = win32gui.GetForegroundWindow()

                if hwnd == 0:
                    process_edit.setText(t("Capture failed: cannot get foreground window"))
                    return

                window_title = win32gui.GetWindowText(hwnd)
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid == 0:
                    process_edit.setText(t("Capture failed: cannot get process ID"))
                    return

                try:
                    process = psutil.Process(pid)
                    proc_name = process.name()
                    process_edit.setText(proc_name)
                    captured_name[0] = proc_name
                    if not display_edit.text():
                        display_edit.setText(window_title[:20])
                except Exception as e:
                    process_edit.setText(t("Capture failed: {}").format(str(e)))
            except Exception as e:
                process_edit.setText(t("Capture failed: {}").format(str(e)))

        capture_btn.clicked.connect(_capture_foreground)

        process_layout = QHBoxLayout()
        process_layout.addWidget(process_edit)
        process_layout.addWidget(capture_btn)
        dialog_layout.addRow(t("Process Name:"), process_layout)

        # 自定义热键 — 支持录制
        hotkey_label = QLabel(t("Not configured (click the button below to record)"))
        hotkey_label.setStyleSheet("color: rgba(255,255,255,150); padding: 4px;")
        recorded_hotkey = [[]]

        record_btn = QPushButton("🎙 " + t("Record Hotkey"))
        record_btn.setCheckable(True)

        def _on_record_toggled(checked):
            if checked:
                record_btn.setText("⏹ " + t("Press combination... (click again to cancel)"))
                hotkey_label.setText(t("Press combination..."))
                hotkey_label.setStyleSheet("color: #FFD700; padding: 4px;")
                dialog.grabKeyboard()
            else:
                record_btn.setText("🎙 " + t("Record Hotkey"))
                dialog.releaseKeyboard()

        def _on_key_event(event):
            if not record_btn.isChecked():
                return
            from PySide6.QtCore import QEvent
            if event.type() == QEvent.KeyPress:
                from PySide6.QtGui import QKeySequence
                # 获取按键组合
                key_seq = QKeySequence(int(event.modifiers()) | int(event.key()))
                key_str = key_seq.toString()
                if key_str:
                    # 解析为按键列表
                    parts = []
                    s = key_str.lower()
                    if "ctrl" in s or "ctrl+" in s:
                        parts.append("ctrl")
                    if "alt" in s or "alt+" in s:
                        parts.append("alt")
                    if "shift" in s or "shift+" in s:
                        parts.append("shift")
                    # 提取主键
                    main_key = s.split("+")[-1].strip()
                    if main_key and main_key not in ["ctrl", "alt", "shift"]:
                        parts.append(main_key)
                    if parts:
                        recorded_hotkey[0] = parts
                        hotkey_label.setText(" + ".join(parts) + " ✅")
                        hotkey_label.setStyleSheet("color: #34C759; padding: 4px;")
                        record_btn.setChecked(False)
                        record_btn.setText("🎙 " + t("Re-record"))

        record_btn.toggled.connect(_on_record_toggled)
        dialog.keyPressEvent = _on_key_event

        hotkey_layout = QHBoxLayout()
        hotkey_layout.addWidget(hotkey_label)
        hotkey_layout.addWidget(record_btn)
        dialog_layout.addRow(t("Voice Input Hotkey:"), hotkey_layout)

        # 也提供预设选项
        preset_combo = QComboBox()
        preset_combo.addItem(t("-- Select Preset --"))
        for display, keys in self._hotkey_options:
            preset_combo.addItem(display)
        preset_combo.currentIndexChanged.connect(lambda idx: (
            recorded_hotkey.__setitem__(0, self._hotkey_options[idx-1][1] if idx > 0 else []),
            hotkey_label.setText(" + ".join(self._hotkey_options[idx-1][1]) if idx > 0 else t("Not configured")),
            hotkey_label.setStyleSheet("color: #34C759; padding: 4px;" if idx > 0 else "color: rgba(255,255,255,150); padding: 4px;")
        ) if idx > 0 else None)
        dialog_layout.addRow(t("Or select preset:"), preset_combo)

        # 提示
        info_label = QLabel(
            t("Usage:\n1. Switch to the target app window, then click "
              "'Capture Foreground'\n2. Click 'Record Hotkey' and press the "
              "voice input shortcut in the target app\n3. Or pick a common "
              "shortcut from the preset list")
        )
        info_label.setStyleSheet("color: rgba(255,255,255,100); font-size: 10px;")
        info_label.setWordWrap(True)
        dialog_layout.addRow(info_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        dialog_layout.addRow(buttons)

        if dialog.exec() == QDialog.Accepted:
            display_name = display_edit.text().strip()
            if not display_name:
                QMessageBox.warning(self, t("Error"), t("Display name cannot be empty"))
                return

            name = display_name.lower().replace(" ", "_").replace(".", "_")
            if name in self._ai_hotkey_combos:
                QMessageBox.warning(self, t("Error"), t("Software '{name}' already exists").format(name=display_name))
                return

            proc_text = process_edit.text().strip()
            process_names = [proc_text] if proc_text and not proc_text.startswith("Capture failed") else []

            hotkey = recorded_hotkey[0]

            # 保存到配置
            ai_config = self._config_manager.get("ai_software", {})
            ai_config[name] = {
                "display_name": display_name,
                "process_names": process_names,
                "voice_input_hotkey": hotkey,
                "window_title_keywords": [display_name],
                "category": "custom",
            }
            self._config_manager.set("ai_software", ai_config)
            self._config_manager.save()

            # 添加到UI
            self._add_software_row(self._ai_tab_layout, name, ai_config[name])
            _logger.info("Custom software added: %s (process=%s, hotkey=%s)",
                        name, process_names, hotkey)
            QMessageBox.information(
                self, t("Success"),
                t("Added: {name}\nProcess: {processes}\nHotkey: {hotkey}").format(
                    name=display_name,
                    processes=process_names,
                    hotkey="+".join(hotkey) if hotkey else t("Not configured"),
                ),
            )

    def _create_calibration_tab(self) -> QWidget:
        """创建校准设置标签页。"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 说明
        info_label = QLabel(
            t("Calibration will guide you through each gesture, one by one, "
              "and generate a personalized threshold profile from the collected "
              "data.\n\nWe recommend calibrating in stable lighting conditions.")
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # 开始校准按钮
        calibrate_btn = QPushButton(t("Start Calibration"))
        calibrate_btn.setMinimumHeight(40)
        calibrate_btn.clicked.connect(self._start_calibration)
        layout.addWidget(calibrate_btn)

        # 校准状态
        self._calibration_status = QLabel(t("Not calibrated"))
        layout.addWidget(self._calibration_status)

        layout.addStretch()

        return widget

    def _save_config(self) -> None:
        """保存配置到 ConfigManager 并发射信号。"""
        # 快捷键设置
        from src.core.gesture_config import DEFAULT_GESTURE_MAPPINGS
        from src.core.enums import GestureType, HandSide

        # 获取当前配置中的手势映射
        gesture_mappings = self._config_manager.get("gesture_mappings", [])
        if not gesture_mappings:
            # 从默认映射构建
            gesture_mappings = []
            for m in DEFAULT_GESTURE_MAPPINGS:
                gesture_mappings.append({
                    "gesture": m.gesture.value,
                    "hand_side": m.hand_side.value,
                    "action_name": m.action_name,
                    "key_sequence": list(m.key_sequence),
                    "emoji": m.emoji,
                    "confirm_frames": m.confirm_frames,
                    "hold_duration_ms": m.hold_duration_ms,
                    "cooldown_ms": m.cooldown_ms,
                    "confidence_threshold": m.confidence_threshold,
                    "action_color": m.action_color,
                })

        # 更新快捷键（不区分手侧）
        for mapping in gesture_mappings:
            key = mapping['gesture']
            if key in self._hotkey_combos:
                combo = self._hotkey_combos[key]
                idx = combo.currentIndex()
                if 0 <= idx < len(self._hotkey_options):
                    _, keys = self._hotkey_options[idx]
                    mapping["key_sequence"] = keys

        self._config_manager.set("gesture_mappings", gesture_mappings)

        # 识别设置
        confidence = self._sensitivity_slider.value() / 100.0
        self._config_manager.set("recognition.thresholds.confidence", confidence)
        self._config_manager.set(
            "recognition.single_hand_mode", self._single_hand_check.isChecked()
        )
        self._config_manager.set(
            "recognition.thresholds.finger_extended",
            self._finger_extended_spin.value(),
        )
        self._config_manager.set(
            "recognition.thresholds.finger_curled",
            self._finger_curled_spin.value(),
        )

        # 防误触设置
        self._config_manager.set(
            "validation.confirm_frames", self._confirm_frames_spin.value()
        )
        self._config_manager.set(
            "validation.cooldown_ms", self._cooldown_spin.value()
        )
        self._config_manager.set(
            "validation.hold_durations.phone_call", self._phone_hold_spin.value()
        )
        self._config_manager.set(
            "validation.hold_durations.pinch", self._pinch_hold_spin.value()
        )
        self._config_manager.set(
            "validation.confidence_threshold", confidence
        )

        # UI设置
        self._config_manager.set(
            "ui.language", self._language_combo.currentData()
        )
        pos_reverse_map = {
            0: "top_left", 1: "top_right",
            2: "bottom_left", 3: "bottom_right", 4: "center",
        }
        self._config_manager.set(
            "ui.panel_position", pos_reverse_map[self._position_combo.currentIndex()]
        )
        self._config_manager.set(
            "ui.panel_opacity", self._opacity_slider.value() / 100.0
        )
        self._config_manager.set(
            "ui.light_effect_enabled", self._light_effect_check.isChecked()
        )
        self._config_manager.set(
            "ui.sound_feedback_enabled", self._sound_check.isChecked()
        )
        self._config_manager.set(
            "ui.mirror_preview", self._mirror_check.isChecked()
        )
        self._config_manager.set(
            "ui.follow_foreground_monitor", self._follow_monitor_check.isChecked()
        )

        # 保存AI软件热键修改
        ai_config = self._config_manager.get("ai_software", {})
        for name, combo in self._ai_hotkey_combos.items():
            idx = combo.currentIndex()
            if idx == 0:
                ai_config[name]["voice_input_hotkey"] = []
            else:
                ai_config[name]["voice_input_hotkey"] = self._hotkey_options[idx - 1][1]
        self._config_manager.set("ai_software", ai_config)

        # 发射配置变更信号
        config = self._config_manager.get_all()
        self.config_changed.emit(config)

        _logger.info("Settings saved (with hotkey customization)")
        self.accept()

    def _reset_to_default(self) -> None:
        """恢复默认配置。"""
        reply = QMessageBox.question(
            self,
            t("Confirm"),
            t("Reset all settings to defaults?"),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._config_manager.reset_to_default()
            config = self._config_manager.get_all()
            self.config_changed.emit(config)
            self.accept()

    def _add_custom_software(self) -> None:
        """添加自定义AI软件对话框。"""

    def _start_calibration(self) -> None:
        """启动校准流程。"""
        self._calibration_status.setText(t("Calibration will be fully implemented in the next version"))
        QMessageBox.information(
            self,
            t("Calibration"),
            t("Calibration started. Follow the guide and make the gestures.\n"
              "(The full calibration flow is triggered by the Onboarding module)"),
        )
