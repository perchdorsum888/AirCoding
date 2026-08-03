"""浮动控制面板主窗口模块。

无边框置顶透明窗口，布局灯效环+手势显示+模式指示+功能按钮+隐私预览。
接收 RecognitionEngine 的 Qt Signal 并路由到各子组件。
跟随前台AI软件所在显示器。
"""

from typing import Optional

from src.core.enums import GestureType, LightState, SystemMode, HandSide
from src.core.state_machine import StateMachine
from src.core.config_manager import ConfigManager
from src.core.i18n import t
from src.action.gesture_mapper import GestureMapper
from src.utils.audio import AudioFeedback
from src.utils.logger import get_logger

_logger = get_logger("MainWindow")

try:
    from PySide6.QtWidgets import (
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QFrame,
        QApplication,
        QSystemTrayIcon,
        QMenu,
    )
    from PySide6.QtCore import Qt, QPoint, QPropertyAnimation, QRect, QObject, Signal
    from PySide6.QtGui import QFont, QColor, QPainter, QBrush, QPen, QMouseEvent, QIcon, QAction, QPixmap
    _HAS_QT = True
except ImportError:
    _HAS_QT = False
    _logger.warning("PySide6 not installed, main window unavailable")


class MainWindow(QWidget if _HAS_QT else object):
    """浮动控制面板主窗口。

    无边框置顶透明窗口，编排灯效、隐私预览、模式指示、功能按钮。
    接收识别引擎信号和状态机信号，更新UI。

    Attributes:
        _state_machine: 状态机。
        _gesture_mapper: 手势映射器。
        _config_manager: 配置管理器。
        _audio_feedback: 声音反馈。
        _light_widget: 灯效组件。
        _preview_widget: 隐私预览组件。
        _toast: 浮动提示。
        _drag_offset: 拖拽偏移量。
    """

    def __init__(
        self,
        state_machine: StateMachine,
        gesture_mapper: GestureMapper,
        config_manager: ConfigManager,
        audio_feedback: AudioFeedback,
    ) -> None:
        """初始化主窗口。

        Args:
            state_machine: 状态机实例。
            gesture_mapper: 手势映射器实例。
            config_manager: 配置管理器实例。
            audio_feedback: 声音反馈实例。
        """
        if _HAS_QT:
            super().__init__()
            self._setup_window(config_manager)

        self._state_machine = state_machine
        self._gesture_mapper = gesture_mapper
        self._config_manager = config_manager
        self._audio_feedback = audio_feedback

        self._light_widget = None
        self._preview_widget = None
        self._toast = None
        self._gesture_label = None
        self._mode_label = None
        self._confidence_label = None
        self._drag_offset: Optional[QPoint] = None
        self._tray_icon = None
        self._quit_requested = False
        self._recognition_engine = None
        self._preview_timer = None

        if _HAS_QT:
            self._setup_ui(config_manager)
            self._position_window(config_manager)
            self._setup_tray_icon()
            self._start_preview_timer()

    def _setup_window(self, config_manager: ConfigManager) -> None:
        """设置窗口属性（无边框、置顶、透明）。"""
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )

        # 设置窗口图标
        import os
        icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "resources", "aircoding.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 窗口尺寸
        opacity = config_manager.get("ui.panel_opacity", 0.85)
        self.setWindowOpacity(opacity)
        self.setFixedSize(260, 360)

    def _setup_tray_icon(self) -> None:
        """设置系统托盘图标（使用自定义ico文件）。"""
        if not _HAS_QT:
            return

        # 加载自定义图标文件
        import os
        icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "resources", "aircoding.ico")
        if os.path.exists(icon_path):
            icon = QIcon(icon_path)
            _logger.info("Tray icon loaded: %s", icon_path)
        else:
            # 回退：绘制简单图标
            pixmap = QPixmap(32, 32)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QBrush(QColor("#4A90D9")))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(4, 4, 24, 24)
            painter.setPen(QPen(QColor("#FFFFFF"), 2))
            painter.setFont(QFont("Arial", 10, QFont.Bold))
            painter.drawText(pixmap.rect(), Qt.AlignCenter, "AK")
            painter.end()
            icon = QIcon(pixmap)

        self._tray_icon = QSystemTrayIcon(icon, self)
        self._tray_icon.setToolTip("AirCoding AirCoding")

        # 托盘菜单
        menu = QMenu()

        show_action = QAction(t("Show/Hide Panel"), self)
        show_action.triggered.connect(self.toggle_visibility)
        menu.addAction(show_action)

        menu.addSeparator()

        settings_action = QAction(t("Settings..."), self)
        settings_action.triggered.connect(self._open_settings)
        menu.addAction(settings_action)

        menu.addSeparator()

        quit_action = QAction(t("Quit"), self)
        quit_action.triggered.connect(self._request_quit)
        menu.addAction(quit_action)

        self._tray_icon.setContextMenu(menu)
        self._tray_icon.activated.connect(self._on_tray_activated)
        self._tray_icon.show()

        _logger.info("System tray icon created")

    def _on_tray_activated(self, reason) -> None:
        """托盘图标点击事件。"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.toggle_visibility()

    def toggle_visibility(self) -> None:
        """切换面板可见性（类似输入法切换）。"""
        if self.isVisible():
            self.hide()
            if self._tray_icon:
                self._tray_icon.showMessage(
                    "AirCoding",
                    t("Panel hidden. Double-click tray icon or press Ctrl+Alt+K to show"),
                    QSystemTrayIcon.Information,
                    2000,
                )
            _logger.info("Panel hidden")
        else:
            self.show()
            self.raise_()
            self.activateWindow()
            _logger.info("Panel shown")

    def _request_quit(self) -> None:
        """请求退出应用。"""
        self._quit_requested = True
        if self._tray_icon:
            self._tray_icon.hide()
        QApplication.quit()

    def _open_settings(self) -> None:
        """打开设置面板。"""
        if hasattr(self, '_settings_btn') and self._settings_btn:
            self._settings_btn.click()
        else:
            self.show()
            self.raise_()

    def closeEvent(self, event) -> None:
        """窗口关闭事件：最小化到托盘而非退出。"""
        if not self._quit_requested:
            event.ignore()
            self.hide()
            if self._tray_icon:
                self._tray_icon.showMessage(
                    "AirCoding",
                    t("Panel minimized to tray. Right-click tray icon to quit"),
                    QSystemTrayIcon.Information,
                    2000,
                )
            _logger.info("Window minimized to tray")
        else:
            event.accept()

    def _setup_ui(self, config_manager: ConfigManager) -> None:
        """设置UI布局。"""
        from src.ui.light_effect_widget import LightEffectWidget
        from src.ui.privacy_preview import PrivacyPreviewWidget
        from src.ui.toast import Toast

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)

        # 灯效组件
        self._light_widget = LightEffectWidget(parent=self, size=70)
        light_container = QHBoxLayout()
        light_container.addStretch()
        light_container.addWidget(self._light_widget)
        light_container.addStretch()
        main_layout.addLayout(light_container)

        # 手势显示
        self._gesture_label = QLabel(t("Waiting for gesture..."))
        font = QFont("Microsoft YaHei UI", 12)
        font.setBold(True)
        self._gesture_label.setFont(font)
        self._gesture_label.setAlignment(Qt.AlignCenter)
        self._gesture_label.setStyleSheet(
            "color: white; background: transparent;"
        )
        main_layout.addWidget(self._gesture_label)

        # 置信度
        self._confidence_label = QLabel("")
        conf_font = QFont("Microsoft YaHei UI", 8)
        self._confidence_label.setFont(conf_font)
        self._confidence_label.setAlignment(Qt.AlignCenter)
        self._confidence_label.setStyleSheet(
            "color: rgba(180, 180, 200, 200); background: transparent;"
        )
        main_layout.addWidget(self._confidence_label)

        # 分割线
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("color: rgba(100, 100, 120, 100);")
        main_layout.addWidget(separator)

        # 模式指示
        self._mode_label = QLabel("🟠 " + t("Manual Confirm Mode"))
        mode_font = QFont("Microsoft YaHei UI", 10)
        self._mode_label.setFont(mode_font)
        self._mode_label.setAlignment(Qt.AlignCenter)
        self._mode_label.setStyleSheet(
            "color: #FF9500; background: transparent;"
        )
        main_layout.addWidget(self._mode_label)

        # 隐私预览
        self._preview_widget = PrivacyPreviewWidget(parent=self, width=240, height=180)
        main_layout.addWidget(self._preview_widget)

        # 功能按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)

        self._settings_btn = QPushButton("⚙️")
        self._settings_btn.setFixedSize(40, 30)
        self._settings_btn.setStyleSheet(
            "QPushButton { background: rgba(60, 60, 80, 150); border-radius: 8px; "
            "color: white; font-size: 16px; }"
            "QPushButton:hover { background: rgba(80, 80, 100, 200); }"
        )
        self._settings_btn.clicked.connect(self._open_settings)
        btn_layout.addWidget(self._settings_btn)

        self._onboarding_btn = QPushButton("📖")
        self._onboarding_btn.setFixedSize(40, 30)
        self._onboarding_btn.setStyleSheet(
            "QPushButton { background: rgba(60, 60, 80, 150); border-radius: 8px; "
            "color: white; font-size: 16px; }"
            "QPushButton:hover { background: rgba(80, 80, 100, 200); }"
        )
        self._onboarding_btn.clicked.connect(self._open_onboarding)
        btn_layout.addWidget(self._onboarding_btn)

        self._calibrate_btn = QPushButton("🎯")
        self._calibrate_btn.setFixedSize(40, 30)
        self._calibrate_btn.setStyleSheet(
            "QPushButton { background: rgba(60, 60, 80, 150); border-radius: 8px; "
            "color: white; font-size: 16px; }"
            "QPushButton:hover { background: rgba(80, 80, 100, 200); }"
        )
        self._calibrate_btn.clicked.connect(self._open_calibration)
        btn_layout.addWidget(self._calibrate_btn)

        self._close_btn = QPushButton("✕")
        self._close_btn.setFixedSize(40, 30)
        self._close_btn.setStyleSheet(
            "QPushButton { background: rgba(60, 60, 80, 150); border-radius: 8px; "
            "color: white; font-size: 14px; }"
            "QPushButton:hover { background: rgba(200, 50, 50, 200); }"
        )
        self._close_btn.clicked.connect(self._on_close)
        btn_layout.addWidget(self._close_btn)

        main_layout.addLayout(btn_layout)

        # Toast
        self._toast = Toast()

    def _position_window(self, config_manager: ConfigManager) -> None:
        """根据配置定位窗口。"""
        position = config_manager.get("ui.panel_position", "bottom_right")
        screen = QApplication.primaryScreen()
        if screen is None:
            return

        geometry = screen.availableGeometry()
        w, h = self.width(), self.height()

        if position == "top_left":
            x, y = geometry.x() + 20, geometry.y() + 20
        elif position == "top_right":
            x, y = geometry.x() + geometry.width() - w - 20, geometry.y() + 20
        elif position == "bottom_left":
            x, y = geometry.x() + 20, geometry.y() + geometry.height() - h - 20
        elif position == "center":
            x = geometry.x() + (geometry.width() - w) // 2
            y = geometry.y() + (geometry.height() - h) // 2
        else:  # bottom_right
            x = geometry.x() + geometry.width() - w - 20
            y = geometry.y() + geometry.height() - h - 20

        self.move(x, y)

    def paintEvent(self, event) -> None:
        """绘制圆角半透明背景。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(QColor(30, 30, 40, 200)))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 16, 16)
        painter.end()

    # === Qt Slots ===

    def on_gesture_detected(self, result) -> None:
        """手势检测确认槽函数。

        Args:
            result: RecognitionResult 对象。
        """
        gesture = result.gesture
        emoji = self._gesture_mapper.get_emoji(gesture)
        action = self._gesture_mapper.get_action(gesture, result.hand_side)

        action_name = action.action_name if action else gesture.value

        # 更新手势显示
        self._gesture_label.setText(f"{emoji} {action_name}")
        self._confidence_label.setText(
            t("Confidence: {:.0f}%").format(result.confidence * 100)
        )

        # 设置灯效动作色
        action_color = self._gesture_mapper.get_action_color(gesture)
        if self._light_widget:
            self._light_widget.set_action_color(action_color)

        # 显示Toast
        if self._toast:
            self._toast.show_message(action_name, emoji, action_color)

        # 播放触发音
        self._audio_feedback.play_trigger()

        _logger.info("Gesture triggered: %s → %s", gesture.value, action_name)

    def on_landmarks_updated(self, hand_lm, face_lm, gesture, frame=None) -> None:
        """landmark更新槽函数（每帧调用，用于预览更新）。

        Args:
            hand_lm: 手部landmark列表。
            face_lm: 面部landmark列表。
            gesture: 当前手势类型。
            frame: 原始摄像头帧（用于预览显示）。
        """
        if self._preview_widget:
            self._preview_widget.update_hand_landmarks(hand_lm, gesture)
            self._preview_widget.update_face_landmarks(face_lm)
            if frame is not None:
                self._preview_widget.update_camera_frame(frame)

    def on_state_changed(self, state: LightState) -> None:
        """灯效状态变更槽函数。

        Args:
            state: 新的灯效状态。
        """
        if self._light_widget:
            self._light_widget.set_state(state)

    def on_mode_changed(self, mode: SystemMode) -> None:
        """系统模式变更槽函数。

        Args:
            mode: 新的系统模式。
        """
        if mode == SystemMode.AUTO_APPROVE:
            self._mode_label.setText("🟢 " + t("Auto Approve Mode"))
            self._mode_label.setStyleSheet("color: #34C759; background: transparent;")
            self._audio_feedback.play_mode_up()
        else:
            self._mode_label.setText("🟠 " + t("Manual Confirm Mode"))
            self._mode_label.setStyleSheet("color: #FF9500; background: transparent;")
            self._audio_feedback.play_mode_down()

    def on_recording_state_changed(self, is_recording: bool) -> None:
        """录音状态变更槽函数。

        Args:
            is_recording: 是否正在录音。
        """
        if is_recording:
            self._audio_feedback.play_recording_start()
            if self._toast:
                self._toast.show_message(t("Voice input activated"), "🎙️", "#FF2D55")
        else:
            self._audio_feedback.play_recording_stop()
            if self._toast:
                self._toast.show_message(t("Voice input stopped"), "🛑", "#8E8E93")

    # === 公共方法 ===

    def update_gesture_display(self, gesture: GestureType, confidence: float) -> None:
        """更新手势显示。

        Args:
            gesture: 手势类型。
            confidence: 置信度。
        """
        emoji = self._gesture_mapper.get_emoji(gesture)
        self._gesture_label.setText(f"{emoji} {gesture.value}")
        self._confidence_label.setText(t("Confidence: {:.0f}%").format(confidence * 100))

    def update_light_effect(self, state: LightState) -> None:
        """更新灯效状态。

        Args:
            state: 灯效状态。
        """
        if self._light_widget:
            self._light_widget.set_state(state)

    def update_mode_indicator(self, mode: SystemMode) -> None:
        """更新模式指示器。

        Args:
            mode: 系统模式。
        """
        self.on_mode_changed(mode)

    def show_toast(self, message: str, icon: str = "") -> None:
        """显示Toast提示。

        Args:
            message: 提示文字。
            icon: 图标emoji。
        """
        if self._toast:
            self._toast.show_message(message, icon)

    def update_recording_status(self, is_recording: bool) -> None:
        """更新录音状态显示。

        Args:
            is_recording: 是否正在录音。
        """
        self.on_recording_state_changed(is_recording)

    def move_to_monitor(self, monitor_index: int) -> None:
        """将窗口移动到指定显示器。

        Args:
            monitor_index: 显示器索引。
        """
        screens = QApplication.screens()
        if monitor_index < 0 or monitor_index >= len(screens):
            return

        geometry = screens[monitor_index].availableGeometry()
        w, h = self.width(), self.height()
        x = geometry.x() + geometry.width() - w - 20
        y = geometry.y() + geometry.height() - h - 20
        self.move(x, y)

    # === 事件处理 ===

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """鼠标按下事件（开始拖拽）。"""
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """鼠标移动事件（拖拽窗口）。"""
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """鼠标释放事件（结束拖拽）。"""
        self._drag_offset = None
        event.accept()

    def _open_settings(self) -> None:
        """打开设置面板。"""
        from src.ui.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self._config_manager, self)
        dialog.config_changed.connect(self._on_config_changed)
        dialog.exec()

    def _open_onboarding(self) -> None:
        """打开新手引导。"""
        from src.ui.onboarding import OnboardingWidget
        # 需要识别引擎引用，由外部设置
        if hasattr(self, "_recognition_engine"):
            onboarding = OnboardingWidget(
                self._recognition_engine, self._config_manager
            )
            onboarding.show()

    def _open_calibration(self) -> None:
        """打开手势校准（像录入指纹一样的逐一注册流程）。

        特性：
        - 校准时屏蔽识别输入（不会触发任何手势动作）
        - 每种手势多角度多手录入（右手正面/右手侧面/左手正面/左手侧面）
        - 打电话手势需要手+脸联合录入
        """
        if not hasattr(self, "_recognition_engine") or self._recognition_engine is None:
            self.show_toast("识别引擎未就绪", "⚠️")
            return

        from src.recognition.calibrator import Calibrator, SAMPLES_PER_GESTURE
        from src.core.enums import GestureType
        from PySide6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar,
            QPushButton,
        )
        from PySide6.QtCore import QTimer, Qt

        # 多角度注册步骤（5种手势，不区分左右手）
        def make_steps():
            steps = []
            base_gestures = [
                (GestureType.OK, "👌", "OK手势"),
                (GestureType.OPEN_PALM, "✋", "张开手掌"),
                (GestureType.SCISSOR, "✌️", "剪刀手"),
                (GestureType.PINCH, "🤏", "捏合"),
            ]
            angles = [
                ("正面", "掌心朝向摄像头"),
                ("侧面", "掌心朝向自己"),
            ]
            for g, emoji, name in base_gestures:
                for angle_name, angle_desc in angles:
                    steps.append((g, emoji, f"{name} - {angle_name}", angle_desc))
            # 打电话手势（需要手+脸联合）
            steps.append((GestureType.PHONE_CALL, "🤙", "打电话手势", "拇指贴耳、小指贴嘴，做出打电话手势"))
            return steps

        enrollment_steps = make_steps()
        calibrator = Calibrator()
        current_step = [0]
        collected = [0]

        # 屏蔽识别输入
        self._recognition_engine.set_calibration_mode(True)

        dialog = QDialog(self)
        dialog.setWindowTitle("手势校准 — 指纹式录入")
        dialog.setFixedSize(400, 340)
        layout = QVBoxLayout(dialog)
        layout.setSpacing(10)

        # 总进度
        total_label = QLabel(f"共 {len(enrollment_steps)} 步")
        total_label.setAlignment(Qt.AlignCenter)
        total_label.setStyleSheet("color: rgba(255,255,255,150); font-size: 11px;")
        layout.addWidget(total_label)

        # 当前手势
        gesture_emoji = QLabel("✊")
        gesture_emoji.setAlignment(Qt.AlignCenter)
        gesture_emoji.setStyleSheet("font-size: 42px;")
        layout.addWidget(gesture_emoji)

        gesture_name_label = QLabel("OK手势 - 正面")
        gesture_name_label.setAlignment(Qt.AlignCenter)
        gesture_name_label.setStyleSheet("font-size: 16px; font-weight: bold; color: white;")
        layout.addWidget(gesture_name_label)

        instruction_label = QLabel("掌心朝向摄像头")
        instruction_label.setAlignment(Qt.AlignCenter)
        instruction_label.setStyleSheet("color: rgba(255,255,255,180); font-size: 12px;")
        layout.addWidget(instruction_label)

        # 进度条
        progress = QProgressBar()
        progress.setRange(0, SAMPLES_PER_GESTURE)
        progress.setStyleSheet(
            "QProgressBar { background: rgba(60,60,80,150); border-radius: 6px; "
            "color: white; text-align: center; }"
            "QProgressBar::chunk { background: #4A90D9; border-radius: 6px; }"
        )
        layout.addWidget(progress)

        # 状态
        status_label = QLabel("准备开始...")
        status_label.setAlignment(Qt.AlignCenter)
        status_label.setStyleSheet("color: #00E5FF; font-size: 12px;")
        layout.addWidget(status_label)

        # 按钮
        btn_layout = QHBoxLayout()
        skip_btn = QPushButton("跳过此步")
        skip_btn.setStyleSheet(
            "QPushButton { background: rgba(60,60,80,150); border-radius: 8px; "
            "color: white; padding: 6px 16px; }"
            "QPushButton:hover { background: rgba(80,80,100,200); }"
        )
        btn_layout.addWidget(skip_btn)

        close_btn = QPushButton("完成校准")
        close_btn.setStyleSheet(
            "QPushButton { background: rgba(74,144,217,200); border-radius: 8px; "
            "color: white; padding: 6px 16px; }"
            "QPushButton:hover { background: rgba(74,144,217,255); }"
        )
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        timer = QTimer(dialog)

        def update_step_ui():
            if current_step[0] >= len(enrollment_steps):
                timer.stop()
                gesture_emoji.setText("✅")
                gesture_name_label.setText("校准完成！")
                instruction_label.setText("所有手势已录入，系统将持续学习适配")
                status_label.setText("点击「完成校准」关闭")
                progress.setValue(SAMPLES_PER_GESTURE)
                calibrator.save_profile()
                if hasattr(self._recognition_engine, '_hand_classifier'):
                    thresholds = calibrator.get_thresholds()
                    if thresholds:
                        self._recognition_engine._hand_classifier.update_thresholds(thresholds)
                return

            gesture, emoji, name, instruction = enrollment_steps[current_step[0]]
            step_num = current_step[0] + 1
            total_label.setText(f"第 {step_num}/{len(enrollment_steps)} 步")
            gesture_emoji.setText(emoji)
            gesture_name_label.setText(name)
            instruction_label.setText(instruction)
            progress.setValue(0)
            collected[0] = 0
            status_label.setText("请做出手势并保持...")

            calibrator.start_enrollment(gesture)

        def collect_frame():
            if current_step[0] >= len(enrollment_steps):
                return
            if collected[0] >= SAMPLES_PER_GESTURE:
                return  # 防止溢出：已采集满，等待update_step_ui重置

            result = self._recognition_engine.get_latest_result()
            gesture = enrollment_steps[current_step[0]][0]

            def _finish_current_step():
                """完成当前手势采集：保存数据→更新分类器→跳转下一步。"""
                try:
                    profile = calibrator.finish_enrollment()
                    if profile:
                        _logger.info("Gesture %s calibration data saved", enrollment_steps[current_step[0]][2])
                    # 每个手势完成后立即更新分类器阈值
                    thresholds = calibrator.get_thresholds()
                    if thresholds and hasattr(self._recognition_engine, '_hand_classifier'):
                        self._recognition_engine._hand_classifier.update_thresholds(thresholds)
                        _logger.info("Classifier thresholds updated: %s", thresholds)
                except Exception as e:
                    _logger.error("Calibration data processing error: %s", e)
                    import traceback
                    _logger.error(traceback.format_exc())
                current_step[0] += 1
                QTimer.singleShot(800, update_step_ui)

            # 打电话手势需要手+脸
            if gesture == GestureType.PHONE_CALL:
                if result and result.hand_landmarks and result.face_landmarks:
                    success = calibrator.collect_enrollment_sample(result.hand_landmarks)
                    if success:
                        collected[0] += 1
                        progress.setValue(collected[0])
                        status_label.setText(f"采集中... {collected[0]}/{SAMPLES_PER_GESTURE}")
                        if collected[0] >= SAMPLES_PER_GESTURE:
                            status_label.setText("✅ 打电话手势录入完成！数据处理中...")
                            _finish_current_step()
                else:
                    status_label.setText("⚠️ 请同时将手和脸放入摄像头范围（拇指贴耳+小指贴嘴）")
            else:
                # 普通手势只需手
                if result and result.hand_landmarks is not None:
                    success = calibrator.collect_enrollment_sample(result.hand_landmarks)
                    if success:
                        collected[0] += 1
                        progress.setValue(collected[0])
                        status_label.setText(f"采集中... {collected[0]}/{SAMPLES_PER_GESTURE}")
                        if collected[0] >= SAMPLES_PER_GESTURE:
                            status_label.setText(f"✅ {enrollment_steps[current_step[0]][2]} 录入完成！数据处理中...")
                            _finish_current_step()
                else:
                    status_label.setText("⚠️ 未检测到手，请将手放入摄像头范围")

        def skip_step():
            calibrator._current_enrollment = None
            calibrator._enrollment_samples = []
            current_step[0] += 1
            update_step_ui()

        def finish():
            timer.stop()
            self._recognition_engine.set_calibration_mode(False)
            calibrator._current_enrollment = None
            calibrator._enrollment_samples = []
            calibrator.save_profile()
            if hasattr(self._recognition_engine, '_hand_classifier'):
                thresholds = calibrator.get_thresholds()
                if thresholds:
                    self._recognition_engine._hand_classifier.update_thresholds(thresholds)
            _logger.info("Gesture calibration completed, %d/%d steps registered", current_step[0], len(enrollment_steps))
            dialog.accept()

        skip_btn.clicked.connect(skip_step)
        close_btn.clicked.connect(finish)
        timer.timeout.connect(collect_frame)
        timer.start(150)

        update_step_ui()
        dialog.exec()

    def set_recognition_engine(self, engine) -> None:
        """设置识别引擎引用（供预览轮询和校准使用）。

        Args:
            engine: RecognitionEngine 实例。
        """
        self._recognition_engine = engine

    def _start_preview_timer(self) -> None:
        """启动预览轮询定时器。

        直接从识别引擎获取最新结果并更新预览，
        绕过信号/槽机制，确保预览可靠更新。
        """
        from PySide6.QtCore import QTimer
        self._preview_timer = QTimer(self)
        self._preview_timer.timeout.connect(self._update_preview)
        self._preview_timer.start(100)  # 每100ms更新一次（10fps）
        _logger.info("Preview polling timer started (100ms)")

    def _update_preview(self) -> None:
        """定时更新预览画面（直接轮询识别引擎）。"""
        if self._recognition_engine is None or self._preview_widget is None:
            return

        result = self._recognition_engine.get_latest_result()
        if result is None:
            return

        # 更新手部landmark
        self._preview_widget.update_hand_landmarks(
            result.hand_landmarks, result.gesture
        )

        # 更新面部landmark
        self._preview_widget.update_face_landmarks(result.face_landmarks)

        # 更新摄像头帧
        if hasattr(result, '_raw_frame') and result._raw_frame is not None:
            self._preview_widget.update_camera_frame(result._raw_frame)
        else:
            # 直接从识别引擎获取最新帧
            frame = getattr(self._recognition_engine, '_latest_frame', None)
            if frame is not None:
                self._preview_widget.update_camera_frame(frame)

        # 更新手势显示
        if result.gesture != GestureType.NONE:
            self.update_gesture_display(result.gesture, result.confidence)

    def _on_close(self) -> None:
        """关闭按钮点击 → 最小化到托盘（不退出）。"""
        self.hide()
        if self._tray_icon:
            self._tray_icon.showMessage(
                "AirCoding",
                "面板已最小化到托盘\n双击托盘图标或按 Ctrl+Alt+K 恢复",
                QSystemTrayIcon.Information,
                3000,
            )
        _logger.info("Panel minimized to tray")

    def _on_config_changed(self, config: dict) -> None:
        """配置变更回调。

        Args:
            config: 新的配置字典。
        """
        # 更新透明度
        opacity = config.get("ui", {}).get("panel_opacity", 0.85)
        self.setWindowOpacity(opacity)

        # 更新声音反馈
        sound_enabled = config.get("ui", {}).get("sound_feedback_enabled", True)
        self._audio_feedback.set_enabled(sound_enabled)

        # 更新预览镜像
        mirror = config.get("ui", {}).get("mirror_preview", False)
        if self._preview_widget:
            self._preview_widget.set_mirror(mirror)

        _logger.info("Main window config updated")
