"""浮动提示模块。

居中偏下方浮动卡片，QPropertyAnimation 淡出。
500ms显示后渐隐，支持图标+文字。
"""

from typing import Optional

from src.utils.logger import get_logger

_logger = get_logger("Toast")

try:
    from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QGraphicsOpacityEffect
    from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect
    from PySide6.QtGui import QFont, QColor, QPainter, QBrush, QPen
    _HAS_QT = True
except ImportError:
    _HAS_QT = False
    _logger.warning("PySide6 not installed, Toast widget unavailable")

# Toast 配置
DISPLAY_DURATION_MS = 1500    # 显示持续时间
FADE_DURATION_MS = 500        # 淡出动画时间
TOAST_WIDTH = 280
TOAST_HEIGHT = 60


class Toast(QWidget if _HAS_QT else object):
    """浮动提示通知组件。

    显示操作确认/错误/模式切换提示，500ms后淡出。

    Attributes:
        _label: 文字标签。
        _opacity_effect: 透明度效果。
        _fade_animation: 淡出动画。
        _display_timer: 显示定时器。
    """

    def __init__(self, parent=None) -> None:
        """初始化Toast组件。"""
        if _HAS_QT:
            super().__init__(parent)
            self.setWindowFlags(
                Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
            )
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setFixedSize(TOAST_WIDTH, TOAST_HEIGHT)

        self._label: Optional[QLabel] = None
        self._icon_label: Optional[QLabel] = None
        self._opacity_effect: Optional[QGraphicsOpacityEffect] = None
        self._fade_animation: Optional[QPropertyAnimation] = None
        self._display_timer: Optional[QTimer] = None

        if _HAS_QT:
            self._setup_ui()

    def _setup_ui(self) -> None:
        """设置UI布局。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setAlignment(Qt.AlignCenter)

        self._label = QLabel()
        font = QFont("Microsoft YaHei UI", 11)
        font.setBold(True)
        self._label.setFont(font)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setStyleSheet("color: white; background: transparent;")
        layout.addWidget(self._label)

        # 透明度效果
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_effect)

        # 淡出动画
        self._fade_animation = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_animation.setDuration(FADE_DURATION_MS)
        self._fade_animation.setStartValue(1.0)
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_animation.finished.connect(self.hide)

        # 显示定时器
        self._display_timer = QTimer(self)
        self._display_timer.setSingleShot(True)
        self._display_timer.timeout.connect(self._start_fade)

    def show_message(
        self,
        message: str,
        icon: str = "",
        color: str = "#007AFF",
        duration: int = DISPLAY_DURATION_MS,
    ) -> None:
        """显示提示消息。

        Args:
            message: 提示文字。
            icon: 图标emoji（可选）。
            color: 背景色（十六进制）。
            duration: 显示持续时间（毫秒）。
        """
        if not _HAS_QT:
            _logger.info("Toast: %s %s", icon, message)
            return

        # 设置文本
        text = f"{icon}  {message}" if icon else message
        self._label.setText(text)

        # 存储颜色用于绘制
        self._bg_color = QColor(color)

        # 定位到屏幕中下方
        self._position_toast()

        # 显示并设置不透明
        self._opacity_effect.setOpacity(1.0)
        self.show()
        self.raise_()

        # 启动显示定时器
        self._display_timer.start(duration)

    def _start_fade(self) -> None:
        """开始淡出动画。"""
        if _HAS_QT and self._fade_animation is not None:
            self._fade_animation.start()

    def _position_toast(self) -> None:
        """将Toast定位到屏幕中下方居中。"""
        if not _HAS_QT:
            return

        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen is None:
            return

        geometry = screen.availableGeometry()
        x = geometry.x() + (geometry.width() - TOAST_WIDTH) // 2
        y = geometry.y() + geometry.height() - TOAST_HEIGHT - 100
        self.move(x, y)

    def paintEvent(self, event) -> None:
        """绘制圆角背景。"""
        if not _HAS_QT:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        bg_color = getattr(self, "_bg_color", QColor("#007AFF"))
        painter.setBrush(QBrush(QColor(
            bg_color.red(), bg_color.green(), bg_color.blue(), 220
        )))
        painter.setPen(Qt.NoPen)

        rect = QRect(0, 0, TOAST_WIDTH, TOAST_HEIGHT)
        painter.drawRoundedRect(rect, 15, 15)

        painter.end()
