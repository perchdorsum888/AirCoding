"""图像预处理模块。

在送入 MediaPipe 之前对原始帧进行光照鲁棒性预处理：
- CLAHE 直方图均衡化（对比度受限自适应直方图均衡化）
- 自适应曝光补偿（Gamma校正）
- 光照等级检测（LOW/NORMAL/HIGH/BACKLIT）

根据光照条件动态调整预处理强度。
"""

from typing import Tuple

import cv2
import numpy as np

from src.core.enums import LightCondition
from src.utils.logger import get_logger

_logger = get_logger("ImageProcessor")

# 光照等级亮度阈值（0~255 灰度均值）
LOW_LIGHT_THRESHOLD = 60.0
HIGH_LIGHT_THRESHOLD = 200.0
# 逆光判定：中心与边缘亮度差
BACKLIT_RATIO_THRESHOLD = 0.4

# CLAHE 参数
CLAHE_CLIP_LIMIT = 2.0
CLAHE_GRID_SIZE = (8, 8)

# Gamma 查找表缓存
_gamma_lut_cache: dict = {}


class ImageProcessor:
    """图像预处理器。

    根据光照条件动态调整预处理参数，提升 MediaPipe 在不同光照下的检测率。

    预处理流程：
        1. 检测光照条件（基于亮度均值和中心/边缘比）
        2. CLAHE 直方图均衡化（LAB颜色空间L通道）
        3. 自适应曝光补偿（Gamma校正）
        4. 返回处理后的帧和光照条件

    Attributes:
        _clahe: CLAHE 实例。
        _config: 配置管理器引用。
    """

    def __init__(self, config_manager=None) -> None:
        """初始化图像预处理器。

        Args:
            config_manager: 配置管理器（可选）。
        """
        self._clahe = cv2.createCLAHE(
            clipLimit=CLAHE_CLIP_LIMIT,
            tileGridSize=CLAHE_GRID_SIZE,
        )
        self._config = config_manager

    def preprocess(self, frame: np.ndarray) -> Tuple[np.ndarray, LightCondition]:
        """预处理图像帧。

        Args:
            frame: BGR格式的原始帧。

        Returns:
            元组 (处理后的BGR帧, 光照条件枚举)。
        """
        if frame is None or frame.size == 0:
            _logger.warning("Empty frame passed to preprocess")
            return frame, LightCondition.NORMAL

        # 1. 检测光照条件
        condition = self._detect_light_condition(frame)

        # 2. CLAHE 直方图均衡化
        processed = self._apply_clahe(frame, condition)

        # 3. 自适应曝光补偿
        processed = self._adaptive_exposure(processed, condition)

        return processed, condition

    def _detect_light_condition(self, frame: np.ndarray) -> LightCondition:
        """检测帧的光照条件。

        基于灰度均值和中心/边缘亮度比判定光照等级。

        Args:
            frame: BGR格式的帧。

        Returns:
            光照条件枚举。
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mean_brightness = float(np.mean(gray))

        # 逆光检测：中心区域与边缘区域亮度比
        h, w = gray.shape
        center_region = gray[int(h * 0.25):int(h * 0.75), int(w * 0.25):int(w * 0.75)]
        edge_top = gray[:int(h * 0.1), :]
        edge_bottom = gray[int(h * 0.9):, :]
        edge_mean = float(np.mean(np.concatenate([edge_top, edge_bottom])))
        center_mean = float(np.mean(center_region))

        if edge_mean > 10 and center_mean > 10:
            ratio = abs(edge_mean - center_mean) / max(edge_mean, center_mean)
            if ratio > BACKLIT_RATIO_THRESHOLD and edge_mean > center_mean:
                _logger.debug("Backlight detected: center=%.1f, edge=%.1f", center_mean, edge_mean)
                return LightCondition.BACKLIT

        if mean_brightness < LOW_LIGHT_THRESHOLD:
            _logger.debug("Low light detected: brightness=%.1f", mean_brightness)
            return LightCondition.LOW
        elif mean_brightness > HIGH_LIGHT_THRESHOLD:
            _logger.debug("High light detected: brightness=%.1f", mean_brightness)
            return LightCondition.HIGH
        else:
            return LightCondition.NORMAL

    def _apply_clahe(
        self, frame: np.ndarray, condition: LightCondition = LightCondition.NORMAL
    ) -> np.ndarray:
        """应用 CLAHE 直方图均衡化。

        在 LAB 颜色空间的 L 通道上应用 CLAHE，
        根据光照条件调整 CLAHE 强度。

        Args:
            frame: BGR格式的帧。
            condition: 光照条件。

        Returns:
            处理后的BGR帧。
        """
        # 根据光照条件调整 CLAHE 参数
        if condition == LightCondition.LOW:
            clip_limit = 3.0  # 低光照增强对比度
        elif condition == LightCondition.BACKLIT:
            clip_limit = 2.5
        elif condition == LightCondition.HIGH:
            clip_limit = 1.5  # 强光照降低对比度增强
        else:
            clip_limit = CLAHE_CLIP_LIMIT

        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=CLAHE_GRID_SIZE)

        # 转换到 LAB 颜色空间
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)

        # 对 L 通道应用 CLAHE
        l_enhanced = clahe.apply(l_channel)

        # 合并并转回 BGR
        lab_enhanced = cv2.merge([l_enhanced, a_channel, b_channel])
        result = cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2BGR)

        return result

    def _adaptive_exposure(
        self, frame: np.ndarray, condition: LightCondition
    ) -> np.ndarray:
        """自适应曝光补偿（Gamma校正）。

        根据光照条件选择 Gamma 值：
            - LOW: Gamma=0.5（提亮暗部）
            - BACKLIT: Gamma=0.7（适度提亮）
            - HIGH: Gamma=1.5（压暗高光）
            - NORMAL: Gamma=1.0（不调整）

        Args:
            frame: BGR格式的帧。
            condition: 光照条件。

        Returns:
            Gamma校正后的BGR帧。
        """
        gamma_map = {
            LightCondition.LOW: 0.5,
            LightCondition.BACKLIT: 0.7,
            LightCondition.HIGH: 1.5,
            LightCondition.NORMAL: 1.0,
        }
        gamma = gamma_map.get(condition, 1.0)

        if gamma == 1.0:
            return frame

        lut = self._get_gamma_lut(gamma)
        return cv2.LUT(frame, lut)

    def _get_gamma_lut(self, gamma: float) -> np.ndarray:
        """获取 Gamma 校正查找表（带缓存）。

        Args:
            gamma: Gamma值。

        Returns:
            256元素的 uint8 查找表。
        """
        if gamma not in _gamma_lut_cache:
            inv_gamma = 1.0 / gamma
            lut = np.array(
                [((i / 255.0) ** inv_gamma) * 255 for i in range(256)],
                dtype=np.uint8,
            )
            _gamma_lut_cache[gamma] = lut
        return _gamma_lut_cache[gamma]
