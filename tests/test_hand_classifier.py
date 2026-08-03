"""手势分类器单元测试。

为每种手势构造模拟 21点 landmark 数据，验证分类结果和置信度。
使用 pytest 框架，mock 数据用固定 landmark 坐标数组。
"""

import sys
import os
import pytest
import numpy as np

# 确保项目根目录在路径中
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core.enums import GestureType
from src.recognition.hand_classifier import HandClassifier


def make_landmark(x: float, y: float, z: float = 0.0) -> dict:
    """创建landmark字典。

    Args:
        x: 归一化x坐标。
        y: 归一化y坐标。
        z: 归一化z坐标。

    Returns:
        landmark字典。
    """
    return {"x": x, "y": y, "z": z}


def make_fist_landmarks() -> list:
    """构造握拳手势的mock landmark数据。

    手腕在原点(0.5, 0.7)，所有手指指尖靠近手掌。
    """
    wrist = (0.5, 0.7)
    return [
        make_landmark(wrist[0], wrist[1]),       # 0: 手腕
        make_landmark(0.48, 0.65),                # 1: 拇指CMC
        make_landmark(0.46, 0.60),                # 2: 拇指MCP
        make_landmark(0.47, 0.56),                # 3: 拇指IP
        make_landmark(0.49, 0.53),                # 4: 拇指TIP（弯曲靠近掌心）
        make_landmark(0.52, 0.58),                # 5: 食指MCP
        make_landmark(0.52, 0.62),                # 6: 食指PIP（弯曲）
        make_landmark(0.52, 0.65),                # 7: 食指DIP
        make_landmark(0.51, 0.68),                # 8: 食指TIP（靠近掌心）
        make_landmark(0.54, 0.58),                # 9: 中指MCP
        make_landmark(0.54, 0.62),                # 10: 中指PIP
        make_landmark(0.53, 0.65),                # 11: 中指DIP
        make_landmark(0.52, 0.68),                # 12: 中指TIP
        make_landmark(0.55, 0.58),                # 13: 无名指MCP
        make_landmark(0.54, 0.62),                # 14: 无名指PIP
        make_landmark(0.53, 0.65),                # 15: 无名指DIP
        make_landmark(0.52, 0.68),                # 16: 无名指TIP
        make_landmark(0.56, 0.60),                # 17: 小指MCP
        make_landmark(0.54, 0.63),                # 18: 小指PIP
        make_landmark(0.53, 0.66),                # 19: 小指DIP
        make_landmark(0.52, 0.69),                # 20: 小指TIP
    ]


def make_open_palm_landmarks() -> list:
    """构造张开手掌的mock landmark数据。

    所有手指伸直，指尖远离手腕。
    """
    wrist = (0.5, 0.8)
    return [
        make_landmark(wrist[0], wrist[1]),       # 0: 手腕
        make_landmark(0.45, 0.72),                # 1: 拇指CMC
        make_landmark(0.42, 0.65),                # 2: 拇指MCP
        make_landmark(0.40, 0.58),                # 3: 拇指IP
        make_landmark(0.38, 0.50),                # 4: 拇指TIP（伸直）
        make_landmark(0.52, 0.62),                # 5: 食指MCP
        make_landmark(0.52, 0.50),                # 6: 食指PIP
        make_landmark(0.52, 0.40),                # 7: 食指DIP
        make_landmark(0.52, 0.30),                # 8: 食指TIP（伸直远离手腕）
        make_landmark(0.56, 0.62),                # 9: 中指MCP
        make_landmark(0.56, 0.48),                # 10: 中指PIP
        make_landmark(0.56, 0.36),                # 11: 中指DIP
        make_landmark(0.56, 0.25),                # 12: 中指TIP
        make_landmark(0.60, 0.62),                # 13: 无名指MCP
        make_landmark(0.60, 0.50),                # 14: 无名指PIP
        make_landmark(0.60, 0.40),                # 15: 无名指DIP
        make_landmark(0.60, 0.30),                # 16: 无名指TIP
        make_landmark(0.64, 0.63),                # 17: 小指MCP
        make_landmark(0.64, 0.52),                # 18: 小指PIP
        make_landmark(0.64, 0.44),                # 19: 小指DIP
        make_landmark(0.64, 0.36),                # 20: 小指TIP
    ]


def make_thumbs_up_landmarks() -> list:
    """构造竖拇指手势的mock landmark数据。

    仅拇指伸直且朝上，其余手指弯曲。
    """
    wrist = (0.5, 0.7)
    return [
        make_landmark(wrist[0], wrist[1]),       # 0: 手腕
        make_landmark(0.48, 0.65),                # 1: 拇指CMC
        make_landmark(0.45, 0.58),                # 2: 拇指MCP
        make_landmark(0.44, 0.50),                # 3: 拇指IP
        make_landmark(0.43, 0.40),                # 4: 拇指TIP（朝上，y更小）
        make_landmark(0.52, 0.60),                # 5: 食指MCP
        make_landmark(0.52, 0.64),                # 6: 食指PIP（弯曲）
        make_landmark(0.52, 0.67),                # 7: 食指DIP
        make_landmark(0.51, 0.69),                # 8: 食指TIP
        make_landmark(0.54, 0.60),                # 9: 中指MCP
        make_landmark(0.54, 0.64),                # 10: 中指PIP
        make_landmark(0.53, 0.67),                # 11: 中指DIP
        make_landmark(0.52, 0.69),                # 12: 中指TIP
        make_landmark(0.55, 0.60),                # 13: 无名指MCP
        make_landmark(0.54, 0.64),                # 14: 无名指PIP
        make_landmark(0.53, 0.67),                # 15: 无名指DIP
        make_landmark(0.52, 0.69),                # 16: 无名指TIP
        make_landmark(0.56, 0.61),                # 17: 小指MCP
        make_landmark(0.54, 0.64),                # 18: 小指PIP
        make_landmark(0.53, 0.67),                # 19: 小指DIP
        make_landmark(0.52, 0.69),                # 20: 小指TIP
    ]


def make_ok_landmarks() -> list:
    """构造OK手势的mock landmark数据。

    拇指尖和食指尖成圈（距离近），其余3指（中指/无名指/小指）伸直。
    """
    wrist = (0.5, 0.7)
    return [
        make_landmark(wrist[0], wrist[1]),       # 0: 手腕
        make_landmark(0.48, 0.65),                # 1: 拇指CMC
        make_landmark(0.47, 0.60),                # 2: 拇指MCP
        make_landmark(0.48, 0.56),                # 3: 拇指IP
        make_landmark(0.50, 0.52),                # 4: 拇指TIP（靠近食指尖）
        make_landmark(0.52, 0.58),                # 5: 食指MCP
        make_landmark(0.53, 0.55),                # 6: 食指PIP
        make_landmark(0.52, 0.53),                # 7: 食指DIP
        make_landmark(0.51, 0.52),                # 8: 食指TIP（靠近拇指尖，成圈）
        make_landmark(0.54, 0.58),                # 9: 中指MCP
        make_landmark(0.56, 0.48),                # 10: 中指PIP（伸直）
        make_landmark(0.57, 0.38),                # 11: 中指DIP
        make_landmark(0.58, 0.28),                # 12: 中指TIP（伸直朝上）
        make_landmark(0.56, 0.58),                # 13: 无名指MCP
        make_landmark(0.58, 0.48),                # 14: 无名指PIP（伸直）
        make_landmark(0.60, 0.38),                # 15: 无名指DIP
        make_landmark(0.61, 0.28),                # 16: 无名指TIP（伸直朝上）
        make_landmark(0.58, 0.60),                # 17: 小指MCP
        make_landmark(0.60, 0.50),                # 18: 小指PIP（伸直）
        make_landmark(0.62, 0.40),                # 19: 小指DIP
        make_landmark(0.63, 0.32),                # 20: 小指TIP（伸直朝上）
    ]


def make_thumbs_down_landmarks() -> list:
    """构造拇指朝下的mock landmark数据。

    仅拇指伸直且朝下，其余手指弯曲。
    """
    landmarks = make_thumbs_up_landmarks()
    # 翻转拇指y坐标：朝下（幅度足够大以超过阈值0.15）
    landmarks[4] = make_landmark(0.43, 0.95)  # 拇指TIP朝下
    landmarks[3] = make_landmark(0.44, 0.88)
    landmarks[2] = make_landmark(0.45, 0.78)
    return landmarks


def make_scissor_landmarks() -> list:
    """构造剪刀手的mock landmark数据。

    食指+中指伸直，无名指+小指弯曲。
    """
    wrist = (0.5, 0.8)
    return [
        make_landmark(wrist[0], wrist[1]),       # 0: 手腕
        make_landmark(0.45, 0.72),                # 1: 拇指CMC
        make_landmark(0.46, 0.68),                # 2: 拇指MCP
        make_landmark(0.48, 0.72),                # 3: 拇指IP（弯曲）
        make_landmark(0.50, 0.76),                # 4: 拇指TIP（弯曲靠近掌心）
        make_landmark(0.52, 0.62),                # 5: 食指MCP
        make_landmark(0.52, 0.50),                # 6: 食指PIP
        make_landmark(0.52, 0.40),                # 7: 食指DIP
        make_landmark(0.52, 0.30),                # 8: 食指TIP（伸直）
        make_landmark(0.56, 0.62),                # 9: 中指MCP
        make_landmark(0.56, 0.48),                # 10: 中指PIP
        make_landmark(0.56, 0.36),                # 11: 中指DIP
        make_landmark(0.56, 0.25),                # 12: 中指TIP（伸直）
        make_landmark(0.58, 0.62),                # 13: 无名指MCP
        make_landmark(0.56, 0.66),                # 14: 无名指PIP（弯曲）
        make_landmark(0.54, 0.72),                # 15: 无名指DIP
        make_landmark(0.52, 0.77),                # 16: 无名指TIP（靠近掌心）
        make_landmark(0.60, 0.63),                # 17: 小指MCP
        make_landmark(0.57, 0.67),                # 18: 小指PIP
        make_landmark(0.54, 0.73),                # 19: 小指DIP
        make_landmark(0.52, 0.78),                # 20: 小指TIP（靠近掌心）
    ]


def make_pinch_landmarks() -> list:
    """构造捏合手势的mock landmark数据。

    拇指尖与食指尖距离极近。
    """
    wrist = (0.5, 0.8)
    return [
        make_landmark(wrist[0], wrist[1]),       # 0: 手腕
        make_landmark(0.45, 0.72),                # 1: 拇指CMC
        make_landmark(0.46, 0.65),                # 2: 拇指MCP
        make_landmark(0.48, 0.55),                # 3: 拇指IP
        make_landmark(0.50, 0.45),                # 4: 拇指TIP
        make_landmark(0.52, 0.62),                # 5: 食指MCP
        make_landmark(0.52, 0.55),                # 6: 食指PIP
        make_landmark(0.52, 0.48),                # 7: 食指DIP
        make_landmark(0.51, 0.45),                # 8: 食指TIP（与拇指TIP距离很近）
        make_landmark(0.56, 0.62),                # 9: 中指MCP
        make_landmark(0.56, 0.66),                # 10: 中指PIP
        make_landmark(0.56, 0.69),                # 11: 中指DIP
        make_landmark(0.56, 0.71),                # 12: 中指TIP
        make_landmark(0.60, 0.62),                # 13: 无名指MCP
        make_landmark(0.60, 0.66),                # 14: 无名指PIP
        make_landmark(0.60, 0.69),                # 15: 无名指DIP
        make_landmark(0.60, 0.71),                # 16: 无名指TIP
        make_landmark(0.63, 0.63),                # 17: 小指MCP
        make_landmark(0.63, 0.66),                # 18: 小指PIP
        make_landmark(0.63, 0.69),                # 19: 小指DIP
        make_landmark(0.63, 0.71),                # 20: 小指TIP
    ]


class TestHandClassifier:
    """手势分类器测试类。"""

    @pytest.fixture
    def classifier(self):
        """创建分类器实例。"""
        return HandClassifier()

    def test_classify_phone_call(self, classifier):
        """测试打电话手势分类（拇指+小指伸直）。"""
        landmarks = make_fist_landmarks()  # 握拳数据作为基础
        # 修改为打电话手形：拇指和小指伸直
        landmarks[4] = make_landmark(0.39, 0.38)  # 拇指TIP伸直
        landmarks[20] = make_landmark(0.55, 0.40)  # 小指TIP伸直
        gesture, confidence = classifier.classify(landmarks, "Right")
        assert gesture == GestureType.PHONE_CALL
        assert confidence > 0.5

    def test_classify_open_palm(self, classifier):
        """测试张开手掌分类。"""
        landmarks = make_open_palm_landmarks()
        gesture, confidence = classifier.classify(landmarks, "Right")
        assert gesture == GestureType.OPEN_PALM
        assert confidence > 0.5

    def test_classify_ok(self, classifier):
        """测试OK手势分类（拇指+食指成圈，其余3指伸直）。"""
        landmarks = make_ok_landmarks()
        gesture, confidence = classifier.classify(landmarks, "Right")
        assert gesture == GestureType.OK
        assert confidence > 0.5

    def test_classify_thumbs_down(self, classifier):
        """测试拇指朝下分类（已删除该手势，应返回NONE或THUMBS_UP）。"""
        landmarks = make_thumbs_down_landmarks()
        gesture, confidence = classifier.classify(landmarks, "Right")
        # THUMBS_DOWN已删除，不应返回该手势
        assert gesture != GestureType.THUMBS_DOWN

    def test_classify_scissor(self, classifier):
        """测试剪刀手分类。"""
        landmarks = make_scissor_landmarks()
        gesture, confidence = classifier.classify(landmarks, "Right")
        assert gesture == GestureType.SCISSOR
        assert confidence > 0.5

    def test_classify_pinch(self, classifier):
        """测试捏合手势分类。"""
        landmarks = make_pinch_landmarks()
        gesture, confidence = classifier.classify(landmarks, "Right")
        assert gesture == GestureType.PINCH
        assert confidence > 0.5

    def test_classify_none_with_empty_landmarks(self, classifier):
        """测试空landmark输入返回NONE。"""
        gesture, confidence = classifier.classify([], "Right")
        assert gesture == GestureType.NONE
        assert confidence == 0.0

    def test_classify_none_with_none_landmarks(self, classifier):
        """测试None landmark输入返回NONE。"""
        gesture, confidence = classifier.classify(None, "Right")
        assert gesture == GestureType.NONE
        assert confidence == 0.0

    def test_update_thresholds(self, classifier):
        """测试阈值更新。"""
        new_thresholds = {"finger_extended": 0.6, "confidence": 0.8}
        classifier.update_thresholds(new_thresholds)
        assert classifier._thresholds["finger_extended"] == 0.6
        assert classifier._thresholds["confidence"] == 0.8

    def test_classify_left_hand(self, classifier):
        """测试左手手势分类（handedness=Left，不区分手侧）。"""
        landmarks = make_open_palm_landmarks()
        gesture, confidence = classifier.classify(landmarks, "Left")
        assert gesture == GestureType.OPEN_PALM
        assert confidence > 0.5
