"""手势分类器模块。

基于 MediaPipe 21点手部 landmark 解析，判定5种基础手势：
OK/打电话/张开/剪刀/捏合。
返回 (GestureType, confidence) 元组。

MediaPipe 21点手部landmark索引：
    0:  手腕
    1-4:  拇指（CMC→MCP→IP→TIP）
    5-8:  食指（MCP→PIP→DIP→TIP）
    9-12: 中指
    13-16: 无名指
    17-20: 小指

手指伸直判定：指尖到掌心距离 > 阈值 且 指尖比PIP关节更远离掌心。
"""

import math
from typing import Tuple

import numpy as np

from src.core.enums import GestureType
from src.utils.logger import get_logger

_logger = get_logger("HandClassifier")

# 手指landmark索引：(指尖, PIP, MCP)
FINGER_LANDMARKS = {
    "thumb": (4, 3, 2),    # 拇指：TIP, IP, MCP
    "index": (8, 6, 5),    # 食指：TIP, PIP, MCP
    "middle": (12, 10, 9),  # 中指
    "ring": (16, 14, 13),   # 无名指
    "pinky": (20, 18, 17),  # 小指
}

# 默认阈值（全局回退值，校准后会被per-finger阈值覆盖）
DEFAULT_THRESHOLDS = {
    "finger_extended": 0.6,       # 全局回退
    "finger_curled": 0.5,         # 全局回退
    "pinch_distance": 0.07,       # 拇指食指尖距离（可校准）
    "confidence": 0.85,
    # per-finger阈值（校准后自动添加）:
    # "finger_extended_thumb": 0.7, "finger_curled_thumb": 0.4,
    # "finger_extended_index": 0.6, "finger_curled_index": 0.4,
    # ...
}

# tip_idx→手指名称映射（用于per-finger阈值查找）
FINGER_NAMES = {
    4: "thumb", 8: "index", 12: "middle", 16: "ring", 20: "pinky",
}


class HandClassifier:
    """手势分类器。

    基于21点归一化 landmark 坐标判定手势类型。

    判定优先级：
        1. PHONE_CALL（打电话）—— 拇指+小指伸直，其余弯曲
        2. OK（OK手势）—— 拇指+食指成圈，其余3指伸直
        3. PINCH（捏合）—— 拇指尖与食指尖距离近，其余弯曲
        4. SCISSOR（剪刀手）—— 食指+中指伸直，其余弯曲
        5. OPEN_PALM（张开）—— 所有手指伸直
        6. NONE —— 不匹配以上任何手势

    Attributes:
        _thresholds: 判定阈值字典。
    """

    def __init__(self, thresholds: dict = None) -> None:
        """初始化手势分类器。

        Args:
            thresholds: 判定阈值字典，覆盖默认值。
        """
        self._thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}

    def classify(
        self, landmarks: list, handedness: str = "Right"
    ) -> Tuple[GestureType, float]:
        """分类手势类型。

        Args:
            landmarks: 21点归一化landmark坐标列表，每个元素为 (x, y, z)。
            handedness: 手部侧别字符串（"Left" 或 "Right"）。

        Returns:
            元组 (手势类型, 置信度0.0~1.0)。
        """
        if landmarks is None or len(landmarks) < 21:
            return GestureType.NONE, 0.0

        try:
            # 提取landmark坐标（兼容dict和list/tuple格式）
            if isinstance(landmarks[0], dict):
                points = np.array([[lm["x"], lm["y"], lm.get("z", 0.0)] for lm in landmarks])
            else:
                points = np.array([[lm[0], lm[1], lm[2] if len(lm) > 2 else 0.0] for lm in landmarks])

            # 判定各手指伸直状态
            fingers_extended = self._get_fingers_extended(points)

            # 按优先级判定手势

            # 1. 打电话手势：拇指+小指伸直，其余弯曲
            if self._is_phone_call_shape(points, fingers_extended):
                return GestureType.PHONE_CALL, 0.90

            # 2. OK手势：拇指+食指成圈（距离近），其余3指伸直
            if self._is_ok(points, fingers_extended):
                return GestureType.OK, 0.92

            # 3. 捏合：拇指尖与食指尖距离很近，其余手指弯曲
            if self._is_pinch(points, fingers_extended):
                return GestureType.PINCH, 0.90

            # 4. 剪刀手：食指+中指伸直，无名指+小指弯曲
            if self._is_scissor(points, fingers_extended):
                return GestureType.SCISSOR, 0.90

            # 5. 张开：所有手指伸直
            if self._is_open_palm(points, fingers_extended):
                return GestureType.OPEN_PALM, 0.92

            return GestureType.NONE, 0.3

        except Exception as e:
            import traceback
            _logger.error("Gesture classification exception: %s\n%s", e, traceback.format_exc())
            return GestureType.NONE, 0.0

    def _get_fingers_extended(self, points: np.ndarray) -> dict:
        """判定各手指是否伸直。

        Args:
            points: 21×3 landmark坐标数组。

        Returns:
            字典 {手指名: 是否伸直}。
        """
        result = {}
        palm_center = points[0]  # 手腕作为掌心参考

        for finger_name, (tip_idx, pip_idx, mcp_idx) in FINGER_LANDMARKS.items():
            if finger_name == "thumb":
                # 拇指特殊处理：比较拇指尖到掌心距离 vs 拇指MCP到掌心距离
                result[finger_name] = self._finger_extended(
                    points, tip_idx, mcp_idx
                )
            else:
                # 其他手指：指尖比PIP更远离掌心
                result[finger_name] = self._finger_extended(
                    points, tip_idx, mcp_idx
                )

        return result

    def _finger_extended(
        self, points: np.ndarray, tip_idx: int, mcp_idx: int
    ) -> bool:
        """判定手指是否伸直（per-finger双阈值方案）。

        优先使用校准的per-finger阈值（finger_extended_{name}），
        无校准数据时回退到全局阈值。

        Args:
            points: landmark坐标数组。
            tip_idx: 指尖landmark索引。
            mcp_idx: MCP关节landmark索引。

        Returns:
            True 如果手指伸直。
        """
        wrist = points[0]
        tip = points[tip_idx]
        mcp = points[mcp_idx]

        dist_tip_wrist = float(np.linalg.norm(tip[:2] - wrist[:2]))
        dist_mcp_wrist = float(np.linalg.norm(mcp[:2] - wrist[:2]))

        if dist_mcp_wrist < 1e-6:
            return False

        ratio = dist_tip_wrist / dist_mcp_wrist

        # 查找per-finger阈值
        finger_name = FINGER_NAMES.get(tip_idx, "")
        ext_key = f"finger_extended_{finger_name}"
        curl_key = f"finger_curled_{finger_name}"

        if ext_key in self._thresholds:
            extended_thresh = self._thresholds[ext_key]
        else:
            extended_thresh = self._thresholds.get("finger_extended", 0.6)

        if curl_key in self._thresholds:
            curled_thresh = self._thresholds[curl_key]
        else:
            curled_thresh = self._thresholds.get("finger_curled", 0.5)

        # 双阈值：超过伸直阈值=伸直，低于弯曲阈值=弯曲，灰区=伸直
        if ratio >= extended_thresh:
            return True
        elif ratio < curled_thresh:
            return False
        else:
            return True  # 灰区判定为伸直（保守策略）

    def _is_phone_call_shape(self, points: np.ndarray, fingers_extended: dict) -> bool:
        """判定打电话手形：拇指+小指伸直，食指+中指+无名指弯曲。

        小指必须明确伸直（ratio超过伸直阈值），不接受灰区。
        这样其他手势（如OK）小指在灰区时不会被误判为打电话。

        Args:
            points: landmark坐标数组。
            fingers_extended: 手指伸直状态字典。

        Returns:
            True 如果是打电话手形。
        """
        if not fingers_extended["thumb"]:
            return False
        if fingers_extended["index"] or fingers_extended["middle"] or fingers_extended["ring"]:
            return False

        # 小指必须明确伸直（严格检查，不接受灰区）
        pinky_ratio = self._get_finger_ratio(points, 20, 17)
        pinky_extended_thresh = self._thresholds.get("finger_extended_pinky", 0.6)
        return pinky_ratio >= pinky_extended_thresh

    def _get_finger_ratio(self, points: np.ndarray, tip_idx: int, mcp_idx: int) -> float:
        """计算手指的伸直比例（指尖到手腕距离 / MCP到手腕距离）。"""
        wrist = points[0]
        tip = points[tip_idx]
        mcp = points[mcp_idx]
        dist_tip = float(np.linalg.norm(tip[:2] - wrist[:2]))
        dist_mcp = float(np.linalg.norm(mcp[:2] - wrist[:2]))
        if dist_mcp < 1e-6:
            return 0.0
        return dist_tip / dist_mcp

    def _finger_distance(
        self, points: np.ndarray, idx_a: int, idx_b: int
    ) -> float:
        """计算两个landmark之间的2D欧氏距离（归一化坐标）。

        Args:
            points: landmark坐标数组。
            idx_a: 第一个landmark索引。
            idx_b: 第二个landmark索引。

        Returns:
            2D欧氏距离。
        """
        return float(np.linalg.norm(points[idx_a][:2] - points[idx_b][:2]))

    def _is_fist(self, points: np.ndarray, fingers_extended: dict) -> bool:
        """判定握拳手势。

        所有非拇指手指弯曲，拇指可弯曲或微弯。

        Args:
            points: landmark坐标数组。
            fingers_extended: 手指伸直状态字典。

        Returns:
            True 如果是握拳。
        """
        curled_count = sum(
            1 for k in ["index", "middle", "ring", "pinky"]
            if not fingers_extended[k]
        )
        # 四指全弯即为握拳
        return curled_count >= 4

    def _is_open_palm(self, points: np.ndarray, fingers_extended: dict) -> bool:
        """判定张开手掌。

        所有手指伸直。

        Args:
            points: landmark坐标数组。
            fingers_extended: 手指伸直状态字典。

        Returns:
            True 如果是张开手掌。
        """
        extended_count = sum(1 for v in fingers_extended.values() if v)
        return extended_count >= 5

    def _is_thumbs_up(self, points: np.ndarray) -> bool:
        """判定竖拇指（已废弃，THUMBS_UP手势已删除，方法保留供测试使用）。

        用手腕作为参照点：拇指尖y坐标高于手腕即可判定朝上。
        兼容手掌朝前和手背朝前两种朝向。

        Args:
            points: landmark坐标数组。

        Returns:
            True 如果拇指朝上。
        """
        thumb_tip_y = points[4][1]
        wrist_y = points[0][1]
        # 拇指尖必须高于手腕（屏幕坐标y向下，越小越高）
        return thumb_tip_y < wrist_y - 0.03

    def _is_thumbs_down(self, points: np.ndarray) -> bool:
        """判定拇指朝下。

        拇指尖y坐标显著低于拇指MCP（屏幕坐标系y向下）。

        Args:
            points: landmark坐标数组。

        Returns:
            True 如果拇指朝下。
        """
        thumb_tip = points[4]
        thumb_mcp = points[2]
        # y越大越靠下
        return thumb_tip[1] > thumb_mcp[1] + self._thresholds["thumb_direction"]

    def _is_scissor(self, points: np.ndarray, fingers_extended: dict) -> bool:
        """判定剪刀手。

        食指+中指伸直，无名指+小指弯曲。

        Args:
            points: landmark坐标数组。
            fingers_extended: 手指伸直状态字典。

        Returns:
            True 如果是剪刀手。
        """
        return (
            fingers_extended["index"]
            and fingers_extended["middle"]
            and not fingers_extended["ring"]
            and not fingers_extended["pinky"]
        )

    def _is_ok(self, points: np.ndarray, fingers_extended: dict) -> bool:
        """判定OK手势：拇指+食指成圈，其余3指明确伸直（ratio≥0.7）。

        OK与PINCH的区别：OK的其余3指明确伸直，PINCH的其余手指弯曲。

        Args:
            points: landmark坐标数组。
            fingers_extended: 手指伸直状态字典。

        Returns:
            True 如果是OK手势。
        """
        dist = self._finger_distance(points, 4, 8)
        pinch_threshold = self._thresholds.get("pinch_distance", 0.07)
        if dist >= pinch_threshold:
            return False
        # 其余3指必须明确伸直（ratio >= 0.7，排除灰区）
        for tip, mcp in [(12, 9), (16, 13), (20, 17)]:
            if self._get_finger_ratio(points, tip, mcp) < 0.7:
                return False
        return True

    def _is_pinch(self, points: np.ndarray, fingers_extended: dict) -> bool:
        """判定捏合手势：拇指尖与食指尖距离近，中指明确弯曲（ratio < 0.7）。

        PINCH与OK的区别：PINCH的其余手指弯曲，OK的其余3指伸直。

        Args:
            points: landmark坐标数组。
            fingers_extended: 手指伸直状态字典。

        Returns:
            True 如果是捏合。
        """
        dist = self._finger_distance(points, 4, 8)
        pinch_threshold = self._thresholds.get("pinch_distance", 0.07)
        if dist >= pinch_threshold:
            return False
        # 中指必须明确弯曲（ratio < 0.7），排除OK
        middle_ratio = self._get_finger_ratio(points, 12, 9)
        return middle_ratio < 0.7

    def update_thresholds(self, thresholds: dict) -> None:
        """更新判定阈值。

        Args:
            thresholds: 新的阈值字典（合并到现有阈值）。
        """
        self._thresholds.update(thresholds)
        _logger.info("Gesture classifier thresholds updated: %s", thresholds)
