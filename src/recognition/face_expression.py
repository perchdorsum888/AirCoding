"""面部表情识别模块。

基于 MediaPipe 468点面部 landmark 进行：
- 挑眉检测（双眉上移量 vs 自适应基准）
- 面部关键点定位（耳部/嘴部/鼻尖），供 PhoneCallDetector 使用

挑眉基准每5分钟自动更新，适应用户面部变化。

MediaPipe FaceMesh 关键landmark索引：
    耳部：左耳 234，右耳 454
    嘴部：上唇中心 13，下唇中心 14
    鼻尖：1
    眉毛：左眉内 55/左眉外 105，右眉内 285/右眉外 334
"""

import time
from typing import Tuple

import numpy as np

from src.utils.logger import get_logger

_logger = get_logger("FaceExpression")

# 面部关键landmark索引
EAR_LEFT_IDX = 234
EAR_RIGHT_IDX = 454
MOUTH_TOP_IDX = 13
MOUTH_BOTTOM_IDX = 14
NOSE_TIP_IDX = 1
# 眉毛landmark（用于挑眉检测）
LEFT_EYEBROW_INNER = 55
LEFT_EYEBROW_OUTER = 105
RIGHT_EYEBROW_INNER = 285
RIGHT_EYEBROW_OUTER = 334
# 眼睛landmark（用于计算眉毛-眼睛距离）
LEFT_EYE_TOP = 159
RIGHT_EYE_TOP = 386

# 默认配置
DEFAULT_EYEBROW_THRESHOLD = 1.5   # 标准差倍数
BASELINE_UPDATE_INTERVAL_S = 300  # 5分钟更新基准


class FaceExpressionRecognizer:
    """面部表情识别器。

    提供挑眉检测和面部关键点定位功能。

    挑眉检测原理：
        1. 采集基准：计算双眉4个landmark的纵坐标均值作为基准
        2. 实时检测：当前双眉纵坐标均值相对基准的上移量
        3. 阈值判定：上移量超过 eyebrow_threshold × std(基准历史) 即判定为挑眉
        4. 自适应更新：每5分钟自动更新基准

    Attributes:
        _baseline: 挑眉基准值（双眉纵坐标均值）。
        _baseline_std: 基准历史标准差。
        _eyebrow_threshold: 挑眉检测阈值（标准差倍数）。
        _last_baseline_update: 上次基准更新时间。
        _baseline_history: 基准历史样本（用于计算标准差）。
    """

    def __init__(
        self,
        eyebrow_threshold: float = DEFAULT_EYEBROW_THRESHOLD,
        update_interval: float = BASELINE_UPDATE_INTERVAL_S,
    ) -> None:
        """初始化面部表情识别器。

        Args:
            eyebrow_threshold: 挑眉检测阈值（标准差倍数，默认1.5）。
            update_interval: 基准自动更新间隔（秒，默认300=5分钟）。
        """
        self._baseline: float = 0.0
        self._baseline_std: float = 0.01  # 初始小值避免除零
        self._eyebrow_threshold = eyebrow_threshold
        self._update_interval = update_interval
        self._last_baseline_update: float = 0.0
        self._baseline_history: list = []
        self._initialized = False

    def initialize_baseline(self, landmarks: list) -> None:
        """初始化挑眉基准。

        使用前若干帧的landmark计算初始基准值。

        Args:
            landmarks: 468点面部landmark坐标列表。
        """
        if landmarks is None or len(landmarks) < 300:
            return

        brow_y = self._compute_eyebrow_y(landmarks)
        self._baseline = brow_y
        self._baseline_history = [brow_y]
        self._baseline_std = 0.01
        self._last_baseline_update = time.monotonic()
        self._initialized = True
        _logger.info("Eyebrow baseline initialized: y=%.4f", brow_y)

    def detect_eyebrow_raise(self, landmarks: list) -> Tuple[bool, float]:
        """检测挑眉表情。

        Args:
            landmarks: 468点面部landmark坐标列表。

        Returns:
            元组 (是否挑眉, 置信度0.0~1.0)。
        """
        if landmarks is None or len(landmarks) < 300:
            return False, 0.0

        if not self._initialized:
            self.initialize_baseline(landmarks)
            return False, 0.0

        # 自动更新基准
        self._auto_update_baseline(landmarks)

        # 计算当前眉毛位置
        current_brow_y = self._compute_eyebrow_y(landmarks)

        # 上移量（y减小=上移，屏幕坐标系）
        raise_amount = self._baseline - current_brow_y

        # 阈值判定
        threshold = self._eyebrow_threshold * self._baseline_std

        if raise_amount > threshold and self._baseline_std > 0:
            confidence = min(1.0, raise_amount / (threshold * 2))
            return True, confidence

        return False, 0.0

    def _compute_eyebrow_y(self, landmarks: list) -> float:
        """计算双眉4个landmark的纵坐标均值。

        使用眉毛与眼睛的相对距离作为特征，消除头部俯仰影响。

        Args:
            landmarks: 面部landmark列表。

        Returns:
            双眉相对眼睛的纵坐标偏移均值。
        """
        try:
            # 眉毛y坐标
            brow_ys = [
                landmarks[LEFT_EYEBROW_INNER][1],
                landmarks[LEFT_EYEBROW_OUTER][1],
                landmarks[RIGHT_EYEBROW_INNER][1],
                landmarks[RIGHT_EYEBROW_OUTER][1],
            ]
            # 眼睛y坐标
            eye_ys = [
                landmarks[LEFT_EYE_TOP][1],
                landmarks[RIGHT_EYE_TOP][1],
            ]

            brow_mean = float(np.mean(brow_ys))
            eye_mean = float(np.mean(eye_ys))

            # 眉毛相对眼睛的距离（归一化）
            return brow_mean - eye_mean
        except (IndexError, TypeError, KeyError) as e:
            _logger.error("Failed to compute eyebrow position: %s", e)
            return 0.0

    def _auto_update_baseline(self, landmarks: list) -> None:
        """自动更新挑眉基准。

        每隔 _update_interval 秒，将当前眉毛位置加入历史样本，
        重新计算基准均值和标准差。

        Args:
            landmarks: 面部landmark列表。
        """
        now = time.monotonic()
        if now - self._last_baseline_update < self._update_interval:
            return

        brow_y = self._compute_eyebrow_y(landmarks)
        self._baseline_history.append(brow_y)

        # 保留最近100个样本
        if len(self._baseline_history) > 100:
            self._baseline_history = self._baseline_history[-100:]

        if len(self._baseline_history) >= 5:
            self._baseline = float(np.mean(self._baseline_history))
            self._baseline_std = max(0.005, float(np.std(self._baseline_history)))

        self._last_baseline_update = now
        _logger.debug(
            "Eyebrow baseline updated: mean=%.4f, std=%.4f",
            self._baseline,
            self._baseline_std,
        )

    def get_ear_landmarks(self, landmarks: list) -> dict:
        """获取耳部landmark坐标。

        供 PhoneCallDetector 使用。

        Args:
            landmarks: 面部landmark列表。

        Returns:
            字典 {"left": (x, y), "right": (x, y)}。
        """
        if landmarks is None or len(landmarks) <= max(EAR_LEFT_IDX, EAR_RIGHT_IDX):
            return {"left": None, "right": None}

        try:
            return {
                "left": (landmarks[EAR_LEFT_IDX][0], landmarks[EAR_LEFT_IDX][1]),
                "right": (landmarks[EAR_RIGHT_IDX][0], landmarks[EAR_RIGHT_IDX][1]),
            }
        except (IndexError, TypeError, KeyError):
            return {"left": None, "right": None}

    def get_mouth_landmarks(self, landmarks: list) -> dict:
        """获取嘴部landmark坐标。

        供 PhoneCallDetector 使用。

        Args:
            landmarks: 面部landmark列表。

        Returns:
            字典 {"top": (x, y), "bottom": (x, y), "center": (x, y)}。
        """
        if landmarks is None or len(landmarks) <= max(MOUTH_TOP_IDX, MOUTH_BOTTOM_IDX):
            return {"top": None, "bottom": None, "center": None}

        try:
            top = (landmarks[MOUTH_TOP_IDX][0], landmarks[MOUTH_TOP_IDX][1])
            bottom = (landmarks[MOUTH_BOTTOM_IDX][0], landmarks[MOUTH_BOTTOM_IDX][1])
            center = ((top[0] + bottom[0]) / 2, (top[1] + bottom[1]) / 2)
            return {"top": top, "bottom": bottom, "center": center}
        except (IndexError, TypeError, KeyError):
            return {"top": None, "bottom": None, "center": None}

    def get_nose_tip(self, landmarks: list) -> Tuple[float, float]:
        """获取鼻尖landmark坐标。

        供 PhoneCallDetector 使用。

        Args:
            landmarks: 面部landmark列表。

        Returns:
            (x, y) 元组，未检测到返回 (0, 0)。
        """
        if landmarks is None or len(landmarks) <= NOSE_TIP_IDX:
            return (0.0, 0.0)

        try:
            return (landmarks[NOSE_TIP_IDX][0], landmarks[NOSE_TIP_IDX][1])
        except (IndexError, TypeError, KeyError):
            return (0.0, 0.0)

    def get_face_center(self, landmarks: list) -> Tuple[float, float]:
        """计算面部中心坐标（鼻尖位置）。

        Args:
            landmarks: 面部landmark列表。

        Returns:
            (x, y) 元组。
        """
        return self.get_nose_tip(landmarks)
