"""灯效组件模块。

使用 QPainter 自定义绘制7种灯效状态动画：
- 呼吸（breathe）：正弦波亮度变化
- 脉动（pulse）：线性亮度变化
- 闪光（flash）：阶跃亮→暗
- 闪烁（flicker）：快速亮灭交替
- 波形（wave）：正弦波环形扩散
- 常亮微脉动（steady_pulse）：轻微亮度变化

QTimer 以30fps驱动动画，颜色用 QColor 插值实现渐变。
"""

import math
from typing import Optional

from src.core.enums import LightState
from src.utils.logger import get_logger

_logger = get_logger("LightEffectWidget")

try:
    from PySide6.QtWidgets import QWidget
    from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
    from PySide6.QtGui import (
        QPainter,
        QColor,
        QPen,
        QBrush,
        QRadialGradient,
        QPainterPath,
    )
    _HAS_QT = True
except ImportError:
    _HAS_QT = False
    _logger.warning("PySide6 not installed, light effect widget unavailable")

# 灯效动画配置
LIGHT_EFFECT_CONFIG = {
    LightState.STANDBY: {
        "color": "#4A90D9",
        "animation": "breathe",
        "period_ms": 3000,
    },
    LightState.RECOGNIZING: {
        "color": "#00E5FF",
        "animation": "pulse",
        "period_ms": 800,
    },
    LightState.RECORDING: {
        "color": "#FF2D55",
        "animation": "wave",
        "period_ms": 600,
    },
    LightState.TRIGGERED: {
        "color": "#FFFFFF",
        "animation": "flash",
        "period_ms": 600,
    },
    LightState.ERROR: {
        "color": "#FF3B30",
        "animation": "flicker",
        "period_ms": 1200,
    },
    LightState.AUTO_APPROVE: {
        "color": "#34C759",
        "animation": "steady_pulse",
        "period_ms": 4000,
    },
    LightState.MANUAL_CONFIRM: {
        "color": "#FF9500",
        "animation": "steady_pulse",
        "period_ms": 4000,
    },
}

# 动画帧率
ANIMATION_FPS = 30


class LightEffectWidget(QWidget if _HAS_QT else object):
    """虚拟灯效组件。

    根据灯效状态绘制对应的动画效果。
    支持状态切换时的渐变过渡。

    Attributes:
        _current_state: 当前灯效状态。
        _action_color: 动作触发色。
        _animation_timer: 动画定时器。
        _animation_phase: 动画相位（0.0~1.0）。
        _transition_progress: 状态过渡进度（0.0~1.0）。
        _from_color: 过渡起始色。
        _to_color: 过渡目标色。
    """

    def __init__(self, parent=None, size: int = 80) -> None:
        """初始化灯效组件。

        Args:
            parent: 父控件。
            size: 组件尺寸（像素）。
        """
        if _HAS_QT:
            super().__init__(parent)
            self.setFixedSize(size, size)

        self._current_state: LightState = LightState.STANDBY
        self._action_color: str = "#FFFFFF"
        self._animation_phase: float = 0.0
        self._transition_progress: float = 1.0  # 1.0=过渡完成
        self._from_color: QColor = QColor("#4A90D9") if _HAS_QT else None
        self._to_color: QColor = QColor("#4A90D9") if _HAS_QT else None
        self._size = size

        # 动画定时器
        if _HAS_QT:
            self._animation_timer = QTimer(self)
            self._animation_timer.timeout.connect(self._update_animation)
            self._animation_timer.start(int(1000 / ANIMATION_FPS))

    def set_state(self, state: LightState) -> None:
        """设置灯效状态，触发渐变过渡。

        Args:
            state: 目标灯效状态。
        """
        if state == self._current_state:
            return

        config = LIGHT_EFFECT_CONFIG.get(state, LIGHT_EFFECT_CONFIG[LightState.STANDBY])

        if _HAS_QT:
            self._from_color = self._get_current_draw_color()
            self._to_color = QColor(config["color"])
            self._transition_progress = 0.0

        old_state = self._current_state
        self._current_state = state
        self._animation_phase = 0.0

        _logger.debug("Light effect state change: %s → %s", old_state.value, state.value)

    def set_action_color(self, color: str) -> None:
        """设置动作触发色（用于 TRIGGERED 状态）。

        Args:
            color: 十六进制色值。
        """
        self._action_color = color

    def start_transition(
        self, from_state: LightState, to_state: LightState
    ) -> None:
        """启动状态过渡动画。

        Args:
            from_state: 起始状态。
            to_state: 目标状态。
        """
        from_config = LIGHT_EFFECT_CONFIG.get(
            from_state, LIGHT_EFFECT_CONFIG[LightState.STANDBY]
        )
        to_config = LIGHT_EFFECT_CONFIG.get(
            to_state, LIGHT_EFFECT_CONFIG[LightState.STANDBY]
        )

        if _HAS_QT:
            self._from_color = QColor(from_config["color"])
            self._to_color = QColor(to_config["color"])
            self._transition_progress = 0.0

        self._current_state = to_state
        self._animation_phase = 0.0

    def _update_animation(self) -> None:
        """更新动画帧（由 QTimer 驱动）。"""
        if not _HAS_QT:
            return

        config = LIGHT_EFFECT_CONFIG.get(
            self._current_state, LIGHT_EFFECT_CONFIG[LightState.STANDBY]
        )
        period_ms = config.get("period_ms", 2000)

        if period_ms > 0:
            self._animation_phase += (1000 / ANIMATION_FPS) / period_ms
            if self._animation_phase >= 1.0:
                self._animation_phase -= 1.0

        # 更新过渡进度
        if self._transition_progress < 1.0:
            self._transition_progress = min(
                1.0, self._transition_progress + (1000 / ANIMATION_FPS) / 400.0
            )

        self.update()

    def _get_current_draw_color(self) -> "QColor":
        """获取当前应该绘制的颜色（考虑过渡）。

        Returns:
            QColor 对象。
        """
        if not _HAS_QT:
            return None

        if self._transition_progress < 1.0:
            return self._lerp_color(
                self._from_color, self._to_color, self._transition_progress
            )
        return self._to_color

    @staticmethod
    def _lerp_color(c1: "QColor", c2: "QColor", t: float) -> "QColor":
        """线性插值两个颜色。

        Args:
            c1: 起始颜色。
            c2: 目标颜色。
            t: 插值因子（0.0~1.0）。

        Returns:
            插值后的 QColor。
        """
        r = int(c1.red() + (c2.red() - c1.red()) * t)
        g = int(c1.green() + (c2.green() - c1.green()) * t)
        b = int(c1.blue() + (c2.blue() - c1.blue()) * t)
        return QColor(r, g, b)

    def _get_brightness(self) -> float:
        """根据动画类型计算当前亮度因子。

        Returns:
            亮度因子 0.0~1.0。
        """
        config = LIGHT_EFFECT_CONFIG.get(
            self._current_state, LIGHT_EFFECT_CONFIG[LightState.STANDBY]
        )
        animation = config.get("animation", "breathe")
        phase = self._animation_phase

        if animation == "breathe":
            # 正弦波呼吸：0.3~1.0
            return 0.3 + 0.7 * (0.5 + 0.5 * math.sin(2 * math.pi * phase))
        elif animation == "pulse":
            # 线性脉动：0.2~1.0
            return 0.2 + 0.8 * (0.5 + 0.5 * math.sin(2 * math.pi * phase))
        elif animation == "flash":
            # 闪光：前20%亮，后80%暗
            return 1.0 if phase < 0.2 else 0.1
        elif animation == "flicker":
            # 闪烁：快速亮灭
            return 1.0 if phase < 0.5 else 0.2
        elif animation == "wave":
            # 波形：正弦波
            return 0.3 + 0.7 * (0.5 + 0.5 * math.sin(4 * math.pi * phase))
        elif animation == "steady_pulse":
            # 常亮微脉动：0.7~1.0
            return 0.7 + 0.3 * (0.5 + 0.5 * math.sin(2 * math.pi * phase))
        else:
            return 1.0

    def paintEvent(self, event) -> None:
        """绘制灯效（QPainter 自定义绘制）。"""
        if not _HAS_QT:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 获取当前颜色和亮度
        base_color = self._get_current_draw_color()
        brightness = self._get_brightness()

        # TRIGGERED 状态使用动作色
        if self._current_state == LightState.TRIGGERED:
            base_color = QColor(self._action_color)

        # 调整亮度
        draw_color = QColor(
            int(base_color.red() * brightness),
            int(base_color.green() * brightness),
            int(base_color.blue() * brightness),
        )

        # 绘制径向渐变光晕
        center = QPointF(self._size / 2, self._size / 2)
        radius = self._size / 2

        gradient = QRadialGradient(center, radius)
        gradient.setColorAt(0.0, QColor(
            draw_color.red(), draw_color.green(), draw_color.blue(), 255
        ))
        gradient.setColorAt(0.5, QColor(
            draw_color.red(), draw_color.green(), draw_color.blue(), 180
        ))
        gradient.setColorAt(1.0, QColor(
            draw_color.red(), draw_color.green(), draw_color.blue(), 0
        ))

        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(0, 0, self._size, self._size))

        # 绘制中心实心圆
        inner_radius = self._size * 0.25
        painter.setBrush(QBrush(draw_color))
        painter.drawEllipse(
            QRectF(
                center.x() - inner_radius,
                center.y() - inner_radius,
                inner_radius * 2,
                inner_radius * 2,
            )
        )

        # 波形动画额外绘制
        if LIGHT_EFFECT_CONFIG.get(self._current_state, {}).get("animation") == "wave":
            wave_radius = self._size * 0.3 + self._size * 0.2 * self._animation_phase
            wave_alpha = int(255 * (1.0 - self._animation_phase))
            wave_pen = QPen(QColor(
                draw_color.red(), draw_color.green(), draw_color.blue(), wave_alpha
            ))
            wave_pen.setWidth(2)
            painter.setPen(wave_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(center, wave_radius, wave_radius)

        painter.end()
