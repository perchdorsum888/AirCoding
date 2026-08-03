"""新手引导模块。

欢迎页 → 逐一学习手势 → 完成总结。
订阅 RecognitionEngine.gesture_detected 信号实现实时反馈。
连续3次正确识别标记通过。

引导流程：
    1. 欢迎页（介绍AirCoding概念）
    2. 遍历每个手势：
       - 显示手势emoji + 动作说明
       - 实时显示手部骨架（辅助调整位置）
       - 用户做出手势 → 识别正确则 correct_count += 1
       - 连续3次正确 → 标记通过，进入下一个手势
    3. 完成总结（已学会手势列表 + 速查卡）
"""

from typing import Optional

from src.core.enums import GestureType
from src.core.config_manager import ConfigManager
from src.core.i18n import t
from src.utils.logger import get_logger

_logger = get_logger("Onboarding")

try:
    from PySide6.QtWidgets import (
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QStackedWidget,
        QProgressBar,
        QFrame,
    )
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtGui import QFont, QColor, QPainter, QBrush
    _HAS_QT = True
except ImportError:
    _HAS_QT = False
    _logger.warning("PySide6 not installed, onboarding widget unavailable")


# 引导手势列表（按学习顺序）
ONBOARDING_GESTURES = [
    {
        "gesture": GestureType.OK,
        "emoji": "👌",
        "name": "OK Gesture",
        "action": "OK Gesture = Press Enter",
        "instruction": "Form a circle with thumb and index finger, keep other fingers straight",
    },
    {
        "gesture": GestureType.OPEN_PALM,
        "emoji": "✋",
        "name": "Open Palm",
        "action": "Open Palm = Press Escape",
        "instruction": "Open your palm and spread all five fingers",
    },
    {
        "gesture": GestureType.SCISSOR,
        "emoji": "✌️",
        "name": "Scissor",
        "action": "Scissor = Ctrl+Z Undo",
        "instruction": "Extend index and middle fingers, curl the rest",
    },
    {
        "gesture": GestureType.PHONE_CALL,
        "emoji": "🤙",
        "name": "Phone Call Gesture",
        "action": "Thumb to ear + pinky to mouth = activate voice input\n"
                 "This is AirCoding's core gesture!",
        "instruction": "Make a phone call gesture: thumb to ear, pinky to mouth",
    },
    {
        "gesture": GestureType.PINCH,
        "emoji": "🤏",
        "name": "Pinch",
        "action": "Pinch = Toggle Mode",
        "instruction": "Touch the tip of your thumb to the tip of your index finger",
    },
]

REQUIRED_CORRECT_COUNT = 3  # 连续正确次数


class OnboardingWidget(QWidget if _HAS_QT else object):
    """新手引导组件。

    多页面引导流程，订阅识别引擎信号实现实时反馈。

    Attributes:
        _recognition_engine: 识别引擎。
        _config_manager: 配置管理器。
        _stack: 页面堆栈。
        _current_step: 当前步骤（0=欢迎页，1~N=手势学习，N+1=完成页）。
        _correct_counts: 各手势正确计数。
    """

    finished = Signal() if _HAS_QT else None

    def __init__(
        self,
        recognition_engine,
        config_manager: ConfigManager,
        parent=None,
    ) -> None:
        """初始化新手引导。

        Args:
            recognition_engine: 识别引擎实例。
            config_manager: 配置管理器。
            parent: 父控件。
        """
        if _HAS_QT:
            super().__init__(parent)
            self.setWindowFlags(
                Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
            )
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setFixedSize(500, 420)

        self._recognition_engine = recognition_engine
        self._config_manager = config_manager
        self._current_step = 0
        self._correct_counts: dict = {}
        self._stack: Optional[QStackedWidget] = None
        self._progress_bar: Optional[QProgressBar] = None
        self._status_label: Optional[QLabel] = None
        self._skip_btn: Optional[QPushButton] = None

        # 初始化正确计数
        for item in ONBOARDING_GESTURES:
            self._correct_counts[item["gesture"]] = 0

        if _HAS_QT:
            self._setup_ui()
            self._connect_signals()

    def _setup_ui(self) -> None:
        """设置UI布局。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # 进度条
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, len(ONBOARDING_GESTURES) + 1)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setStyleSheet(
            "QProgressBar { background: rgba(60, 60, 80, 150); border-radius: 4px; }"
            "QProgressBar::chunk { background: #007AFF; border-radius: 4px; }"
        )
        layout.addWidget(self._progress_bar)

        # 页面堆栈
        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        # 创建欢迎页
        self._stack.addWidget(self._create_welcome_page())

        # 创建各手势学习页
        for item in ONBOARDING_GESTURES:
            self._stack.addWidget(self._create_gesture_page(item))

        # 创建完成页
        self._stack.addWidget(self._create_complete_page())

        # 状态标签
        self._status_label = QLabel("")
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setStyleSheet(
            "color: #34C759; font-size: 14px; font-weight: bold;"
        )
        layout.addWidget(self._status_label)

        # 底部按钮
        btn_layout = QHBoxLayout()

        self._skip_btn = QPushButton(t("Skip Tutorial"))
        self._skip_btn.setStyleSheet(
            "QPushButton { background: rgba(60, 60, 80, 150); border-radius: 8px; "
            "color: white; padding: 8px 20px; }"
            "QPushButton:hover { background: rgba(80, 80, 100, 200); }"
        )
        self._skip_btn.clicked.connect(self._skip)
        btn_layout.addWidget(self._skip_btn)

        btn_layout.addStretch()

        self._next_btn = QPushButton(t("Next →"))
        self._next_btn.setStyleSheet(
            "QPushButton { background: #007AFF; border-radius: 8px; "
            "color: white; padding: 8px 24px; font-weight: bold; }"
            "QPushButton:hover { background: #0056b3; }"
            "QPushButton:disabled { background: #555; }"
        )
        self._next_btn.clicked.connect(self._next_step)
        btn_layout.addWidget(self._next_btn)

        layout.addLayout(btn_layout)

    def _create_welcome_page(self) -> QWidget:
        """创建欢迎页。"""
        page = QFrame()
        page.setStyleSheet(
            "QFrame { background: rgba(30, 30, 40, 220); border-radius: 16px; }"
        )
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel(t("👋 Welcome to AirCoding"))
        title.setFont(QFont("Microsoft YaHei UI", 20, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: white;")
        layout.addWidget(title)

        desc = QLabel(
            t("\nAirCoding recognizes gestures and expressions through your "
              "camera,\nletting you control AI interactions hands-free.\n\n"
              "Next, we will learn the core gestures one by one.\n"
              "Each gesture requires 3 consecutive correct recognitions.")
        )
        desc.setFont(QFont("Microsoft YaHei UI", 12))
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet("color: rgba(200, 200, 220, 220);")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        return page

    def _create_gesture_page(self, item: dict) -> QWidget:
        """创建手势学习页。

        Args:
            item: 手势信息字典。

        Returns:
            页面控件。
        """
        page = QFrame()
        page.setStyleSheet(
            "QFrame { background: rgba(30, 30, 40, 220); border-radius: 16px; }"
        )
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignCenter)

        # 手势emoji
        emoji_label = QLabel(item["emoji"])
        emoji_label.setFont(QFont("Segoe UI Emoji", 64))
        emoji_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(emoji_label)

        # 手势名称
        name_label = QLabel(t(item["name"]))
        name_label.setFont(QFont("Microsoft YaHei UI", 18, QFont.Bold))
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setStyleSheet("color: white;")
        layout.addWidget(name_label)

        # 动作说明
        action_label = QLabel(t(item["action"]))
        action_label.setFont(QFont("Microsoft YaHei UI", 11))
        action_label.setAlignment(Qt.AlignCenter)
        action_label.setStyleSheet("color: #00E5FF;")
        action_label.setWordWrap(True)
        layout.addWidget(action_label)

        # 指导
        instruction_label = QLabel(f"\n💡 {t(item['instruction'])}")
        instruction_label.setFont(QFont("Microsoft YaHei UI", 10))
        instruction_label.setAlignment(Qt.AlignCenter)
        instruction_label.setStyleSheet("color: rgba(200, 200, 220, 180);")
        layout.addWidget(instruction_label)

        # 正确次数显示
        count_label = QLabel(t("Correct: {}/{}").format(0, REQUIRED_CORRECT_COUNT))
        count_label.setObjectName(f"count_{item['gesture'].value}")
        count_label.setFont(QFont("Microsoft YaHei UI", 12))
        count_label.setAlignment(Qt.AlignCenter)
        count_label.setStyleSheet("color: #34C759; font-weight: bold;")
        layout.addWidget(count_label)

        return page

    def _create_complete_page(self) -> QWidget:
        """创建完成总结页。"""
        page = QFrame()
        page.setStyleSheet(
            "QFrame { background: rgba(30, 30, 40, 220); border-radius: 16px; }"
        )
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel(t("🎉 Congratulations!"))
        title.setFont(QFont("Microsoft YaHei UI", 24, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #34C759;")
        layout.addWidget(title)

        summary = QLabel(
            t("\nYou have learned all the core gestures!\n\n"
              "🤙 Phone Call → Voice Input\n"
              "👌 OK → Enter\n"
              "✋ Open Palm → Escape\n"
              "✌️ Scissor → Ctrl+Z\n\n"
              "You can start using AirCoding now!")
        )
        summary.setFont(QFont("Microsoft YaHei UI", 12))
        summary.setAlignment(Qt.AlignCenter)
        summary.setStyleSheet("color: white;")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        return page

    def _connect_signals(self) -> None:
        """连接识别引擎信号。"""
        if self._recognition_engine is not None:
            self._recognition_engine.gesture_detected.connect(
                self._on_gesture_detected
            )

    def _on_gesture_detected(self, result) -> None:
        """手势检测回调。

        Args:
            result: RecognitionResult 对象。
        """
        # 仅在手势学习阶段处理
        if self._current_step < 1 or self._current_step > len(ONBOARDING_GESTURES):
            return

        current_item = ONBOARDING_GESTURES[self._current_step - 1]
        expected_gesture = current_item["gesture"]

        if result.gesture == expected_gesture:
            self._correct_counts[expected_gesture] += 1
            count = self._correct_counts[expected_gesture]

            # 更新计数显示
            count_label = self._stack.currentWidget().findChild(
                QLabel, f"count_{expected_gesture.value}"
            )
            if count_label:
                count_label.setText(t("Correct: {}/{}").format(count, REQUIRED_CORRECT_COUNT))

            if count >= REQUIRED_CORRECT_COUNT:
                self._status_label.setText(t("✓ Gesture learned!"))
                self._status_label.setStyleSheet(
                    "color: #34C759; font-size: 14px; font-weight: bold;"
                )
                # 自动进入下一步
                from PySide6.QtCore import QTimer
                QTimer.singleShot(1000, self._next_step)
            else:
                self._status_label.setText(t("Correct! {}/{}").format(count, REQUIRED_CORRECT_COUNT))
                self._status_label.setStyleSheet(
                    "color: #34C759; font-size: 14px; font-weight: bold;"
                )
        elif result.gesture != GestureType.NONE:
            self._status_label.setText(t("✗ Try again"))
            self._status_label.setStyleSheet(
                "color: #FF3B30; font-size: 14px; font-weight: bold;"
            )

    def _next_step(self) -> None:
        """进入下一步。"""
        self._current_step += 1
        self._progress_bar.setValue(self._current_step)
        self._status_label.setText("")

        if self._current_step >= len(ONBOARDING_GESTURES) + 2:
            # 完成
            self._complete()
            return

        self._stack.setCurrentIndex(self._current_step)

        # 最后一步隐藏下一步按钮
        if self._current_step == len(ONBOARDING_GESTURES) + 1:
            self._next_btn.setText(t("Done ✓"))
            self._next_btn.setStyleSheet(
                "QPushButton { background: #34C759; border-radius: 8px; "
                "color: white; padding: 8px 24px; font-weight: bold; }"
                "QPushButton:hover { background: #2d9a47; }"
            )

    def _skip(self) -> None:
        """跳过引导。"""
        _logger.info("User skipped onboarding")
        self._complete()

    def _complete(self) -> None:
        """完成引导。"""
        self._config_manager.set_onboarding_completed(True)
        _logger.info("Onboarding completed")
        self.finished.emit()
        self.close()

    def paintEvent(self, event) -> None:
        """绘制背景。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(QColor(20, 20, 30, 200)))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 20, 20)
        painter.end()
