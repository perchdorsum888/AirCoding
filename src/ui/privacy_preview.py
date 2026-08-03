"""隐私预览组件模块。

使用 QPainter 绘制 schematic avatar（圆点眼睛+弧线眉毛+线条嘴巴）
和手部21点骨架连线，完全基于 landmark 坐标渲染，不显示真实视频。

手部骨架使用 MediaPipe HAND_CONNECTIONS 定义的连接关系。
面部伪像用5个关键点（双眼/双眉/嘴）绘制简化 avatar。
"""

from typing import Optional

from src.core.enums import GestureType
from src.core.i18n import t
from src.utils.logger import get_logger

_logger = get_logger("PrivacyPreview")

try:
    from PySide6.QtWidgets import QWidget
    from PySide6.QtCore import Qt, QRectF, QPointF
    from PySide6.QtGui import (
        QPainter,
        QColor,
        QPen,
        QBrush,
        QFont,
        QPainterPath,
        QImage,
        QPixmap,
    )
    _HAS_QT = True
except ImportError:
    _HAS_QT = False
    _logger.warning("PySide6 not installed, privacy preview widget unavailable")

# MediaPipe 手部骨架连接关系（21点）
HAND_CONNECTIONS = [
    # 拇指
    (0, 1), (1, 2), (2, 3), (3, 4),
    # 食指
    (0, 5), (5, 6), (6, 7), (7, 8),
    # 中指
    (9, 10), (10, 11), (11, 12),
    # 无名指
    (13, 14), (14, 15), (15, 16),
    # 小指
    (0, 17), (17, 18), (18, 19), (19, 20),
    # 掌心连接
    (5, 9), (9, 13), (13, 17),
]

# 面部关键landmark索引
FACE_LEFT_EYE = 33
FACE_RIGHT_EYE = 263
FACE_LEFT_EYE_TOP = 159
FACE_RIGHT_EYE_TOP = 386
FACE_LEFT_EYEBROW = 70
FACE_RIGHT_EYEBROW = 300
FACE_LEFT_EYEBROW_INNER = 55
FACE_RIGHT_EYEBROW_INNER = 285
FACE_MOUTH_LEFT = 61
FACE_MOUTH_RIGHT = 291
FACE_MOUTH_TOP = 13
FACE_MOUTH_BOTTOM = 14
FACE_NOSE = 1
FACE_NOSE_TIP = 4
FACE_CHIN = 152
FACE_LEFT_EAR = 234
FACE_RIGHT_EAR = 454
FACE_LEFT_CHEEK = 234
FACE_RIGHT_CHEEK = 454

# 面部轮廓连接（用于绘制简化五官）
FACE_CONTOUR = [
    # 左眉
    (70, 105), (105, 107),
    # 右眉
    (300, 334), (334, 336),
    # 左眼轮廓
    (33, 246), (246, 161), (161, 160), (160, 159), (159, 158), (158, 157), (157, 173), (173, 133),
    # 右眼轮廓
    (263, 466), (466, 388), (388, 387), (387, 386), (386, 385), (385, 384), (384, 398), (398, 362),
    # 嘴部轮廓
    (61, 185), (185, 40), (40, 39), (39, 37), (37, 0), (0, 267), (267, 269), (269, 270), (270, 409), (409, 291),
]

# 手势emoji
GESTURE_EMOJI_MAP = {
    GestureType.NONE: "",
    GestureType.PHONE_CALL: "🤙",
    GestureType.OK: "👌",
    GestureType.THUMBS_UP: "👍",  # 已删除，保留兼容
    GestureType.THUMBS_DOWN: "👎",
    GestureType.PINCH: "🤏",
    GestureType.FIST: "✊",
    GestureType.OPEN_PALM: "✋",
    GestureType.SCISSOR: "✌️",
    GestureType.RAISE_EYEBROW: "🤨",
}


class PrivacyPreviewWidget(QWidget if _HAS_QT else object):
    """隐私预览组件。

    绘制 schematic avatar 和手部骨架，不显示真实视频。
    所有渲染基于 landmark 归一化坐标。

    Attributes:
        _hand_landmarks: 手部landmark坐标（None=未检测到手）。
        _face_landmarks: 面部landmark坐标（None=未检测到面部）。
        _current_gesture: 当前手势类型。
        _mirror: 是否镜像（左右手镜像）。
    """

    def __init__(self, parent=None, width: int = 200, height: int = 150) -> None:
        """初始化隐私预览组件。

        Args:
            parent: 父控件。
            width: 组件宽度。
            height: 组件高度。
        """
        if _HAS_QT:
            super().__init__(parent)
            self.setFixedSize(width, height)
            self.setAttribute(Qt.WA_TransparentForMouseEvents)

        self._hand_landmarks: Optional[list] = None
        self._face_landmarks: Optional[list] = None
        self._current_gesture: GestureType = GestureType.NONE
        self._mirror: bool = False
        self._width = width
        self._height = height
        self._camera_frame = None  # 原始摄像头帧

    def update_camera_frame(self, frame) -> None:
        """更新摄像头帧（用于显示真实画面背景）。

        Args:
            frame: numpy.ndarray BGR格式的摄像头帧。
        """
        if frame is not None:
            self._camera_frame = frame
            if _HAS_QT:
                self.update()  # 触发重绘

    def update_hand_landmarks(
        self, landmarks: Optional[list], gesture: GestureType = GestureType.NONE
    ) -> None:
        """更新手部landmark数据。

        Args:
            landmarks: 21点landmark坐标列表，或 None。
            gesture: 当前手势类型。
        """
        self._hand_landmarks = landmarks
        self._current_gesture = gesture
        if _HAS_QT:
            self.update()

    def update_face_landmarks(self, landmarks: Optional[list]) -> None:
        """更新面部landmark数据。

        Args:
            landmarks: 468点landmark坐标列表，或 None。
        """
        self._face_landmarks = landmarks
        if _HAS_QT:
            self.update()

    def set_mirror(self, mirror: bool) -> None:
        """设置镜像模式。

        Args:
            mirror: True 启用镜像。
        """
        self._mirror = mirror

    def clear(self) -> None:
        """清空预览。"""
        self._hand_landmarks = None
        self._face_landmarks = None
        self._current_gesture = GestureType.NONE
        if _HAS_QT:
            self.update()

    def paintEvent(self, event) -> None:
        """绘制预览（QPainter 自定义绘制）。"""
        if not _HAS_QT:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 调试日志：每30帧记录一次预览状态
        self._paint_count = getattr(self, '_paint_count', 0) + 1
        if self._paint_count % 30 == 0:
            frame_shape = self._camera_frame.shape if self._camera_frame is not None else None
            _logger.debug(
                "预览绘制 #%d: camera_frame=%s, hand=%s, face=%s, gesture=%s",
                self._paint_count,
                f"{frame_shape}" if frame_shape else "None",
                f"{len(self._hand_landmarks)}pts" if self._hand_landmarks else "None",
                f"{len(self._face_landmarks)}pts" if self._face_landmarks else "None",
                self._current_gesture.value if self._current_gesture else "none",
            )

        # 绘制摄像头画面作为背景（镜像）
        if self._camera_frame is not None:
            try:
                import numpy as np
                frame = self._camera_frame
                # 转换 BGR → RGB
                if len(frame.shape) == 3 and frame.shape[2] == 3:
                    rgb = frame[:, :, ::-1].copy()
                else:
                    rgb = frame.copy()
                # 镜像翻转
                if self._mirror:
                    rgb = rgb[:, ::-1, :].copy()
                # 创建 QImage 并立即转为 QPixmap（避免数据被GC回收）
                h, w = rgb.shape[:2]
                bytes_per_line = rgb.strides[0]
                qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
                pixmap = QPixmap.fromImage(qimg)  # 拷贝数据，避免GC问题
                # 缩放绘制到预览区域
                painter.drawPixmap(self.rect(), pixmap)
            except Exception as e:
                _logger.debug("Camera frame draw failed: %s", e)
                painter.fillRect(self.rect(), QColor(20, 20, 30, 200))
        else:
            painter.fillRect(self.rect(), QColor(20, 20, 30, 150))

        # 绘制面部 avatar（半透明叠加）
        if self._face_landmarks is not None:
            self._draw_face_avatar(painter, self._face_landmarks)

        # 绘制手势有效区域圆形（以人脸为中心）
        if self._face_landmarks is not None and len(self._face_landmarks) > 454:
            self._draw_valid_area(painter, self._face_landmarks)

        # 绘制手部骨架（半透明叠加）
        if self._hand_landmarks is not None:
            self._draw_hand_skeleton(painter, self._hand_landmarks)

        # 绘制手势标签
        if self._current_gesture != GestureType.NONE:
            self._draw_gesture_label(painter, self._current_gesture)

        # 摄像头未就绪时显示人头虚线引导框
        if self._camera_frame is None:
            self._draw_loading_guide(painter)
        elif self._hand_landmarks is None and self._face_landmarks is None:
            # 摄像头已就绪但未检测到人脸手势
            self._draw_face_guide(painter)

        painter.end()

    def _draw_loading_guide(self, painter: "QPainter") -> None:
        """摄像头未就绪时的引导画面：人头虚线框 + 加载提示。"""
        w, h = self._width, self._height
        cx, cy = w / 2, h / 2

        # 背景填充
        painter.fillRect(self.rect(), QColor(20, 20, 30, 200))

        # 人头虚线轮廓（圆形头部 + 肩膀弧线）
        guide_color = QColor(100, 200, 255, 120)
        painter.setPen(QPen(guide_color, 2, Qt.DashLine))
        painter.setBrush(Qt.NoBrush)

        # 头部圆形（占画面上半部分中心）
        head_r = min(w, h) * 0.18
        painter.drawEllipse(QPointF(cx, cy - h * 0.08), head_r, head_r * 1.15)

        # 肩膀弧线
        shoulder_w = head_r * 2.2
        shoulder_h = head_r * 0.8
        painter.drawArc(
            int(cx - shoulder_w), int(cy + head_r * 0.3),
            int(shoulder_w * 2), int(shoulder_h * 2),
            0 * 16, 180 * 16
        )

        # 加载提示文字
        painter.setPen(QPen(QColor(120, 120, 140)))
        font = QFont("Arial", 9)
        painter.setFont(font)
        painter.drawText(
            QRectF(0, h - 40, w, 30),
            Qt.AlignCenter,
            t("Starting camera..."),
        )

    def _draw_face_guide(self, painter: "QPainter") -> None:
        """摄像头已就绪但未检测到人脸时的人头虚线引导框。"""
        w, h = self._width, self._height
        cx, cy = w / 2, h / 2

        # 半透明人头虚线轮廓
        guide_color = QColor(100, 200, 255, 80)
        painter.setPen(QPen(guide_color, 1.5, Qt.DashLine))
        painter.setBrush(Qt.NoBrush)

        # 头部圆形
        head_r = min(w, h) * 0.18
        painter.drawEllipse(QPointF(cx, cy - h * 0.08), head_r, head_r * 1.15)

        # 肩膀弧线
        shoulder_w = head_r * 2.2
        shoulder_h = head_r * 0.8
        painter.drawArc(
            int(cx - shoulder_w), int(cy + head_r * 0.3),
            int(shoulder_w * 2), int(shoulder_h * 2),
            0 * 16, 180 * 16
        )

        # 提示文字
        painter.setPen(QPen(QColor(120, 120, 140, 180)))
        font = QFont("Arial", 8)
        painter.setFont(font)
        painter.drawText(
            QRectF(0, h - 30, w, 20),
            Qt.AlignCenter,
            t("Align your face here"),
        )

    def _draw_face_avatar(self, painter: "QPainter", landmarks: list) -> None:
        """绘制面部五官标记（叠加在摄像头画面上）。

        绘制：眉毛连线、眼睛轮廓、嘴部轮廓、鼻尖、耳部标记点。

        Args:
            painter: QPainter 对象。
            landmarks: 面部landmark列表。
        """
        w, h = self._width, self._height

        def to_pixel(lm):
            """将归一化坐标转换为像素坐标。"""
            if isinstance(lm, dict):
                x = float(lm["x"])
                y = float(lm["y"])
            else:
                x = float(lm[0])
                y = float(lm[1])
            if self._mirror:
                x = 1.0 - x
            return QPointF(x * w, y * h)

        def safe_point(idx):
            """安全获取landmark像素坐标，越界返回None。"""
            if idx < len(landmarks):
                return to_pixel(landmarks[idx])
            return None

        try:
            # 1. 绘制面部轮廓连线（半透明绿色）
            contour_pen = QPen(QColor(0, 255, 100, 150), 1)
            painter.setPen(contour_pen)
            painter.setBrush(Qt.NoBrush)
            for idx_a, idx_b in FACE_CONTOUR:
                pa = safe_point(idx_a)
                pb = safe_point(idx_b)
                if pa and pb:
                    painter.drawLine(pa, pb)

            # 2. 绘制眉毛（黄色加粗线）
            brow_pen = QPen(QColor(255, 200, 0, 220), 2)
            painter.setPen(brow_pen)
            # 左眉
            p1, p2 = safe_point(70), safe_point(105)
            if p1 and p2:
                painter.drawLine(p1, p2)
            p1, p2 = safe_point(105), safe_point(107)
            if p1 and p2:
                painter.drawLine(p1, p2)
            # 右眉
            p1, p2 = safe_point(300), safe_point(334)
            if p1 and p2:
                painter.drawLine(p1, p2)
            p1, p2 = safe_point(334), safe_point(336)
            if p1 and p2:
                painter.drawLine(p1, p2)

            # 3. 绘制眼睛（青色圆点 + 轮廓）
            eye_color = QColor(0, 229, 255, 240)
            painter.setBrush(QBrush(eye_color))
            painter.setPen(Qt.NoPen)
            for idx in [FACE_LEFT_EYE, FACE_RIGHT_EYE, FACE_LEFT_EYE_TOP, FACE_RIGHT_EYE_TOP]:
                p = safe_point(idx)
                if p:
                    painter.drawEllipse(p, 3, 3)

            # 4. 绘制嘴部（红色连线）
            mouth_pen = QPen(QColor(255, 45, 85, 220), 2)
            painter.setPen(mouth_pen)
            mouth_pts = [safe_point(i) for i in [FACE_MOUTH_LEFT, FACE_MOUTH_TOP, FACE_MOUTH_RIGHT, FACE_MOUTH_BOTTOM]]
            mouth_pts = [p for p in mouth_pts if p]
            if len(mouth_pts) >= 2:
                for i in range(len(mouth_pts)):
                    painter.drawLine(mouth_pts[i], mouth_pts[(i + 1) % len(mouth_pts)])

            # 5. 绘制鼻尖（白色圆点）
            nose = safe_point(FACE_NOSE_TIP)
            if nose:
                painter.setBrush(QBrush(QColor(255, 255, 255, 240)))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(nose, 3, 3)

            # 6. 绘制耳部标记（黄色虚线圆，打电话手势参考）
            ear_pen = QPen(QColor(255, 200, 0, 180), 1, Qt.DotLine)
            painter.setPen(ear_pen)
            painter.setBrush(Qt.NoBrush)
            for idx in [FACE_LEFT_EAR, FACE_RIGHT_EAR]:
                p = safe_point(idx)
                if p:
                    painter.drawEllipse(p, 4, 4)

        except (IndexError, TypeError, KeyError) as e:
            _logger.debug("Face avatar draw failed: %s", e)

    def _draw_valid_area(self, painter: "QPainter", face_landmarks: list) -> None:
        """绘制手势有效区域圆形（以人脸为中心）。

        以鼻尖为圆心，人脸宽度×2.5为半径，绘制虚线圆形。
        手部在此圆形内才会被识别，圆形外的手部被忽略。

        Args:
            painter: QPainter 对象。
            face_landmarks: 面部landmark列表。
        """
        w, h = self._width, self._height

        def get_xy(idx):
            lm = face_landmarks[idx]
            if isinstance(lm, dict):
                x, y = float(lm["x"]), float(lm["y"])
            else:
                x, y = float(lm[0]), float(lm[1])
            if self._mirror:
                x = 1.0 - x
            return x, y

        try:
            import math
            # 圆心：鼻尖
            cx, cy = get_xy(1)
            # 人脸宽度：左耳到右耳
            lx, ly = get_xy(234)
            rx, ry = get_xy(454)
            face_width = math.sqrt((rx - lx) ** 2 + (ry - ly) ** 2)
            radius = face_width * 1.625

            # 绘制虚线圆形
            pen = QPen(QColor(0, 229, 255, 120), 1.5, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(QBrush(QColor(0, 229, 255, 15)))  # 极淡的青色填充
            center = QPointF(cx * w, cy * h)
            painter.drawEllipse(center, radius * w, radius * h)

            # 中心十字标记
            painter.setPen(QPen(QColor(0, 229, 255, 80), 1))
            cross_size = 4
            painter.drawLine(QPointF(cx * w - cross_size, cy * h), QPointF(cx * w + cross_size, cy * h))
            painter.drawLine(QPointF(cx * w, cy * h - cross_size), QPointF(cx * w, cy * h + cross_size))

        except (IndexError, TypeError, KeyError) as e:
            _logger.debug("Valid area draw failed: %s", e)

    def _draw_hand_skeleton(self, painter: "QPainter", landmarks: list) -> None:
        """绘制手部21点骨架连线。

        Args:
            painter: QPainter 对象。
            landmarks: 手部landmark列表。
        """
        w, h = self._width, self._height

        def to_pixel(lm):
            """将归一化坐标转换为像素坐标。"""
            if isinstance(lm, dict):
                x = float(lm["x"])
                y = float(lm["y"])
            else:
                x = float(lm[0])
                y = float(lm[1])
            if self._mirror:
                x = 1.0 - x
            return QPointF(x * w, y * h)

        try:
            points = [to_pixel(lm) for lm in landmarks[:21]]

            # 绘制骨架连线
            line_pen = QPen(QColor(0, 229, 255, 200), 2)
            painter.setPen(line_pen)
            painter.setBrush(Qt.NoBrush)

            for idx_a, idx_b in HAND_CONNECTIONS:
                if idx_a < len(points) and idx_b < len(points):
                    painter.drawLine(points[idx_a], points[idx_b])

            # 绘制关节点
            painter.setBrush(QBrush(QColor(255, 255, 255, 230)))
            painter.setPen(Qt.NoPen)
            for point in points:
                painter.drawEllipse(point, 3, 3)

            # 指尖用不同颜色标记
            tip_indices = [4, 8, 12, 16, 20]
            painter.setBrush(QBrush(QColor(255, 45, 85, 230)))
            for idx in tip_indices:
                if idx < len(points):
                    painter.drawEllipse(points[idx], 4, 4)

        except (IndexError, TypeError) as e:
            _logger.debug("Hand skeleton draw failed: %s", e)

    def _draw_gesture_label(self, painter: "QPainter", gesture: GestureType) -> None:
        """在预览角落绘制手势emoji标签。

        Args:
            painter: QPainter 对象。
            gesture: 手势类型。
        """
        emoji = GESTURE_EMOJI_MAP.get(gesture, "")
        if not emoji:
            return

        font = QFont("Segoe UI Emoji", 16)
        painter.setFont(font)
        painter.setPen(QPen(QColor(255, 255, 255, 200)))

        # 绘制在右上角
        painter.drawText(
            self._width - 40, 25,
            emoji,
        )
