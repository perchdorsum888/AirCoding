"""打电话手势检测模块。

简化版：仅识别手形（拇指+小指伸直，其余三指弯曲），
不需要手放到脸上，不需要面部landmark。
左右手均可识别。

MediaPipe 手部landmark索引：
    0: 手腕
    4: 拇指尖
    8: 食指尖
    12: 中指尖
    16: 无名指尖
    20: 小指尖
"""

import math
from typing import Tuple

import numpy as np

from src.utils.logger import get_logger

_logger = get_logger("PhoneCallDetector")

# 手部landmark索引
THUMB_TIP = 4
THUMB_IP = 3
THUMB_MCP = 2
INDEX_TIP = 8
INDEX_PIP = 6
INDEX_MCP = 5
MIDDLE_TIP = 12
MIDDLE_PIP = 10
MIDDLE_MCP = 9
RING_TIP = 16
RING_PIP = 14
RING_MCP = 13
PINKY_TIP = 20
PINKY_PIP = 18
PINKY_MCP = 17
WRIST = 0


class PhoneCallDetector:
    """打电话手势检测器（纯手形识别）。

    判定条件：拇指+小指伸直，食指+中指+无名指弯曲。
    不需要面部landmark，不需要手放到脸上。
    左右手均可。

    判定逻辑：
        1. 拇指伸直：拇指尖到手腕距离 / 拇指MCP到手腕距离 > 阈值
        2. 小指伸直：小指尖到手腕距离 / 小指MCP到手腕距离 > 阈值
        3. 食指弯曲：食指尖到手腕距离 / 食指MCP到手腕距离 < 阈值
        4. 中指弯曲：中指尖到手腕距离 / 中指MCP到手腕距离 < 阈值
        5. 无名指弯曲：无名指尖到手腕距离 / 无名指MCP到手腕距离 < 阈值
    """

    def __init__(self, extended_threshold: float = 0.6, curled_threshold: float = 0.55) -> None:
        """初始化打电话手势检测器。

        Args:
            extended_threshold: 手指伸直判定阈值（ratio > 此值 = 伸直）
            curled_threshold: 手指弯曲判定阈值（ratio < 此值 = 弯曲）
        """
        self._extended_threshold = extended_threshold
        self._curled_threshold = curled_threshold

    def detect(
        self,
        hand_landmarks: list,
        face_landmarks: list = None,
        handedness: str = "Right",
    ) -> Tuple[bool, float]:
        """检测打电话手势（纯手形，不需要面部）。

        Args:
            hand_landmarks: 21点手部landmark坐标列表。
            face_landmarks: 面部landmark（忽略，保留参数兼容性）。
            handedness: 手部侧别（忽略，左右手均可）。

        Returns:
            元组 (是否检测到打电话手势, 置信度0.0~1.0)。
        """
        if hand_landmarks is None or len(hand_landmarks) < 21:
            return False, 0.0

        try:
            # 提取坐标
            points = self._to_array(hand_landmarks)
            wrist = points[0]

            # 计算各手指的伸直比例
            ratios = {}
            for name, tip_idx, mcp_idx in [
                ("thumb", THUMB_TIP, THUMB_MCP),
                ("index", INDEX_TIP, INDEX_MCP),
                ("middle", MIDDLE_TIP, MIDDLE_MCP),
                ("ring", RING_TIP, RING_MCP),
                ("pinky", PINKY_TIP, PINKY_MCP),
            ]:
                dist_tip = float(np.linalg.norm(points[tip_idx] - wrist))
                dist_mcp = float(np.linalg.norm(points[mcp_idx] - wrist))
                ratios[name] = dist_tip / max(dist_mcp, 1e-6)

            # 判定条件
            thumb_extended = ratios["thumb"] > self._extended_threshold
            pinky_extended = ratios["pinky"] > self._extended_threshold
            index_curled = ratios["index"] < self._curled_threshold
            middle_curled = ratios["middle"] < self._curled_threshold
            ring_curled = ratios["ring"] < self._curled_threshold

            if thumb_extended and pinky_extended and index_curled and middle_curled and ring_curled:
                # 计算置信度：基于伸直和弯曲的明确程度
                extended_scores = [ratios["thumb"], ratios["pinky"]]
                curled_scores = [ratios["index"], ratios["middle"], ratios["ring"]]

                # 伸直手指ratio越高越好，弯曲手指ratio越低越好
                avg_extended = np.mean(extended_scores)
                avg_curled = np.mean(curled_scores)

                # 分离度 = 伸直均值 - 弯曲均值，越大越明确
                separation = avg_extended - avg_curled
                confidence = min(0.95, 0.6 + separation * 0.5)

                return True, max(0.85, confidence)

            return False, 0.0

        except Exception as e:
            _logger.debug("Phone call gesture detection exception: %s", e)
            return False, 0.0

    def _to_array(self, landmarks: list) -> np.ndarray:
        """将landmark列表转为numpy数组。

        支持tuple格式 (x,y,z) 和dict格式 {"x":..,"y":..,"z":..}。
        """
        points = []
        for lm in landmarks[:21]:
            if isinstance(lm, dict):
                points.append([float(lm["x"]), float(lm["y"])])
            else:
                points.append([float(lm[0]), float(lm[1])])
        return np.array(points)
