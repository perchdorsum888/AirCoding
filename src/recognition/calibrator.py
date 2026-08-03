"""手势与面部表情校准模块。

像录入指纹一样，支持：
1. 初始注册：引导用户逐一录入每种手势和面部表情
2. 持续适配：在使用过程中持续学习用户特征，提高准确率
3. 用户档案：保存/加载用户校准数据

注册流程：
    每种手势采集30帧 → 计算关键特征均值±标准差 → 生成专属阈值
    面部表情采集基准 → 计算挑眉阈值

持续适配：
    每次成功识别后，将landmark数据加入历史样本
    每100次成功识别后重新计算阈值
    保留最近200个样本（滑动窗口）

档案存储：
    %APPDATA%/AirCoding/calibration_profile.json
"""

import json
import os
import time
from collections import deque
from typing import Optional, Dict, List, Tuple
import math

import numpy as np

from src.core.enums import GestureType
from src.utils.logger import get_logger

_logger = get_logger("Calibrator")

# 采样配置
SAMPLES_PER_GESTURE = 30
MAX_HISTORY = 200
ADAPT_INTERVAL = 100
FACE_BASELINE_FRAMES = 30


class Calibrator:
    """手势与面部表情校准器。"""

    def __init__(self, profile_path: Optional[str] = None) -> None:
        if profile_path is None:
            appdata = os.environ.get("APPDATA", "")
            profile_dir = os.path.join(appdata, "AirCoding")
            os.makedirs(profile_dir, exist_ok=True)
            profile_path = os.path.join(profile_dir, "calibration_profile.json")

        self._profile_path = profile_path
        self._profiles: Dict[GestureType, dict] = {}
        self._enrollment_samples: List[list] = []
        self._current_enrollment: Optional[GestureType] = None
        self._face_baseline_samples: List[float] = []
        self._success_counts: Dict[GestureType, int] = {}
        self._adapt_history: Dict[GestureType, deque] = {}
        self._adapt_callback = None
        self._face_profile = {}

        self.load_profile()

    def load_profile(self) -> bool:
        if not os.path.exists(self._profile_path):
            _logger.info("No calibration profile found, using default thresholds")
            return False
        try:
            with open(self._profile_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for key, profile in data.get("gestures", {}).items():
                try:
                    gesture = GestureType(key)
                    self._profiles[gesture] = profile
                    self._adapt_history[gesture] = deque(maxlen=MAX_HISTORY)
                    self._success_counts[gesture] = 0
                except ValueError:
                    pass
            if "face" in data:
                self._face_profile = data["face"]
            _logger.info("Calibration profile loaded: %d gestures", len(self._profiles))
            return True
        except Exception as e:
            _logger.error("Failed to load calibration profile: %s", e)
            return False

    def save_profile(self) -> bool:
        try:
            data = {
                "version": 2,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "gestures": {g.value: p for g, p in self._profiles.items()},
                "face": getattr(self, "_face_profile", {}),
            }
            with open(self._profile_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            _logger.info("Calibration profile saved: %s", self._profile_path)
            return True
        except Exception as e:
            _logger.error("Failed to save calibration profile: %s", e)
            return False

    def is_gesture_calibrated(self, gesture: GestureType) -> bool:
        return gesture in self._profiles

    def is_face_calibrated(self) -> bool:
        return bool(getattr(self, "_face_profile", {}))

    def is_all_calibrated(self) -> bool:
        all_gestures = [GestureType.OK, GestureType.OPEN_PALM, GestureType.SCISSOR, GestureType.PINCH, GestureType.PHONE_CALL]
        return all(self.is_gesture_calibrated(g) for g in all_gestures)

    def get_calibration_progress(self) -> dict:
        gestures = [GestureType.OK, GestureType.OPEN_PALM, GestureType.SCISSOR, GestureType.PINCH, GestureType.PHONE_CALL]
        return {g.value: self.is_gesture_calibrated(g) for g in gestures}

    # ========== 注册阶段 ==========

    def start_enrollment(self, gesture: GestureType) -> None:
        self._current_enrollment = gesture
        self._enrollment_samples = []
        _logger.info("Starting gesture enrollment: %s", gesture.value)

    def collect_enrollment_sample(self, hand_landmarks: list) -> bool:
        if self._current_enrollment is None:
            return False
        if hand_landmarks is None or len(hand_landmarks) < 21:
            return False
        try:
            features = self._extract_features(hand_landmarks)
            self._enrollment_samples.append(features)
            return True
        except Exception as e:
            _logger.debug("Sample collection failed: %s", e)
            return False

    def get_enrollment_progress(self) -> Tuple[int, int]:
        return (len(self._enrollment_samples), SAMPLES_PER_GESTURE)

    def finish_enrollment(self) -> Optional[dict]:
        if self._current_enrollment is None:
            return None
        if len(self._enrollment_samples) < 10:
            _logger.warning("Not enough enrollment samples: %d/10", len(self._enrollment_samples))
            self._current_enrollment = None
            self._enrollment_samples = []
            return None

        feature_names = self._enrollment_samples[0].keys()
        features_array = {}
        for name in feature_names:
            values = [s[name] for s in self._enrollment_samples]
            features_array[name] = {
                "mean": float(np.mean(values)),
                "std": max(0.001, float(np.std(values))),
                "min": float(np.min(values)),
                "max": float(np.max(values)),
            }

        # 多角度合并：如果该手势已有档案，合并而非覆盖
        existing = self._profiles.get(self._current_enrollment)
        if existing:
            for name in feature_names:
                old_stats = existing["features"].get(name, {})
                new_stats = features_array[name]
                old_mean = old_stats.get("mean", new_stats["mean"])
                old_count = existing.get("sample_count", len(self._enrollment_samples))
                new_count = len(self._enrollment_samples)
                total_count = old_count + new_count
                merged_mean = (old_mean * old_count + new_stats["mean"] * new_count) / total_count
                merged_std = max(0.001, (old_stats.get("std", new_stats["std"]) * old_count + new_stats["std"] * new_count) / total_count)
                features_array[name] = {
                    "mean": merged_mean,
                    "std": merged_std,
                    "min": min(old_stats.get("min", new_stats["min"]), new_stats["min"]),
                    "max": max(old_stats.get("max", new_stats["max"]), new_stats["max"]),
                }
            sample_count = existing.get("sample_count", 0) + len(self._enrollment_samples)
            angles_count = existing.get("angles_count", 1) + 1
            _logger.info("Multi-angle merge: %s, cumulative %d frames, %d angles", self._current_enrollment.value, sample_count, angles_count)
        else:
            sample_count = len(self._enrollment_samples)
            angles_count = 1

        profile = {
            "gesture": self._current_enrollment.value,
            "features": features_array,
            "sample_count": sample_count,
            "angles_count": angles_count,
            "calibrated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        self._profiles[self._current_enrollment] = profile
        self._adapt_history[self._current_enrollment] = deque(maxlen=MAX_HISTORY)
        self._success_counts[self._current_enrollment] = 0

        _logger.info("Gesture enrollment complete: %s, %d features, %d frame samples",
                    self._current_enrollment.value, len(features_array), sample_count)

        self._current_enrollment = None
        self._enrollment_samples = []
        self.save_profile()
        return profile

    def start_face_enrollment(self) -> None:
        self._face_baseline_samples = []
        _logger.info("Starting face expression enrollment")

    def collect_face_sample(self, face_landmarks: list) -> bool:
        if face_landmarks is None or len(face_landmarks) < 300:
            return False
        try:
            brow_ys = [self._get_y(face_landmarks, i) for i in [55, 105, 285, 334]]
            eye_ys = [self._get_y(face_landmarks, i) for i in [159, 386]]
            distance = float(np.mean(brow_ys)) - float(np.mean(eye_ys))
            self._face_baseline_samples.append(distance)
            return True
        except Exception:
            return False

    def finish_face_enrollment(self) -> Optional[dict]:
        if len(self._face_baseline_samples) < 10:
            return None
        self._face_profile = {
            "baseline_mean": float(np.mean(self._face_baseline_samples)),
            "baseline_std": max(0.005, float(np.std(self._face_baseline_samples))),
            "threshold_multiplier": 1.5,
            "sample_count": len(self._face_baseline_samples),
        }
        self._face_baseline_samples = []
        self.save_profile()
        return self._face_profile

    def get_face_profile(self) -> dict:
        return getattr(self, "_face_profile", {})

    # ========== 持续适配 ==========

    def record_success(self, gesture: GestureType, hand_landmarks: list) -> None:
        if gesture not in self._profiles:
            return
        if gesture not in self._adapt_history:
            self._adapt_history[gesture] = deque(maxlen=MAX_HISTORY)
        try:
            features = self._extract_features(hand_landmarks)
            self._adapt_history[gesture].append(features)
            self._success_counts[gesture] = self._success_counts.get(gesture, 0) + 1
            if self._success_counts[gesture] >= ADAPT_INTERVAL:
                self._adapt_thresholds(gesture)
                self._success_counts[gesture] = 0
        except Exception as e:
            _logger.debug("Failed to record continuous adaptation: %s", e)

    def _adapt_thresholds(self, gesture: GestureType) -> None:
        history = self._adapt_history.get(gesture)
        if not history or len(history) < 20:
            return
        profile = self._profiles.get(gesture)
        if not profile:
            return

        all_features = {}
        feature_names = history[0].keys()
        for name in feature_names:
            values = [s[name] for s in history]
            old_mean = profile["features"].get(name, {}).get("mean", 0)
            old_std = profile["features"].get(name, {}).get("std", 0.01)
            new_mean = float(np.mean(values))
            new_std = max(0.001, float(np.std(values)))
            adapted_mean = 0.7 * old_mean + 0.3 * new_mean
            adapted_std = 0.7 * old_std + 0.3 * new_std
            all_features[name] = {
                "mean": adapted_mean,
                "std": max(0.001, adapted_std),
                "min": min(profile["features"].get(name, {}).get("min", float(np.min(values))), float(np.min(values))),
                "max": max(profile["features"].get(name, {}).get("max", float(np.max(values))), float(np.max(values))),
            }
        profile["features"] = all_features
        profile["adapted_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        profile["adapt_count"] = profile.get("adapt_count", 0) + 1
        _logger.info("Gesture %s thresholds adapted (iteration %d)", gesture.value, profile["adapt_count"])
        self.save_profile()

        if self._adapt_callback:
            try:
                new_thresholds = self.get_thresholds()
                self._adapt_callback(new_thresholds)
                _logger.info("Adapted thresholds pushed to classifier")
            except Exception as e:
                _logger.error("Failed to push adapted thresholds: %s", e)

    def get_thresholds(self) -> dict:
        """获取per-finger校准阈值。

        为每根手指单独计算伸直/弯曲阈值，而非全局单一阈值。
        拇指/食指/中指/无名指/小指各有独立的 finger_extended_{name} 和 finger_curled_{name}。

        Returns:
            阈值字典，如 {"finger_extended_thumb": 0.7, "finger_curled_index": 0.4, ...}
        """
        if not self._profiles:
            return {}

        # 各手势中每根手指的伸直(e)/弯曲(c)/模糊(-)状态
        GESTURE_FINGER_STATES = {
            "ok":         {"thumb": "-", "index": "-", "middle": "e", "ring": "e", "pinky": "e"},
            "open_palm":  {"thumb": "e", "index": "e", "middle": "e", "ring": "e", "pinky": "e"},
            "scissor":    {"thumb": "-", "index": "e", "middle": "e", "ring": "c", "pinky": "c"},
            "pinch":      {"thumb": "-", "index": "c", "middle": "c", "ring": "c", "pinky": "c"},
            "phone_call": {"thumb": "e", "index": "c", "middle": "c", "ring": "c", "pinky": "e"},
        }

        # 收集每根手指的伸直/弯曲ratio
        finger_data = {f: {"extended": [], "curled": []} for f in ["thumb", "index", "middle", "ring", "pinky"]}

        for gesture, profile in self._profiles.items():
            features = profile.get("features", {})
            states = GESTURE_FINGER_STATES.get(gesture.value)
            if not states:
                continue
            for finger, state in states.items():
                ratio_name = f"{finger}_ratio"
                if ratio_name not in features:
                    continue
                mean_val = features[ratio_name]["mean"]
                if state == "e":
                    finger_data[finger]["extended"].append(mean_val)
                elif state == "c":
                    finger_data[finger]["curled"].append(mean_val)

        # 为每根手指计算独立阈值
        thresholds = {}
        for finger, data in finger_data.items():
            ext = data["extended"]
            curl = data["curled"]
            if ext and curl:
                min_ext = min(ext)
                max_curl = max(curl)
                thresholds[f"finger_extended_{finger}"] = (min_ext + max_curl) / 2
                thresholds[f"finger_curled_{finger}"] = max_curl
            elif ext:
                thresholds[f"finger_extended_{finger}"] = min(ext) * 0.8
            elif curl:
                thresholds[f"finger_curled_{finger}"] = max(curl) * 1.2

        if thresholds:
            _logger.info("Per-finger calibration thresholds (%d items): %s", len(thresholds), thresholds)

        # pinch距离阈值
        pinch_profile = self._profiles.get(GestureType.PINCH, {})
        if pinch_profile:
            pinch_dist_stats = pinch_profile.get("features", {}).get("thumb_index_dist", {})
            if pinch_dist_stats:
                thresholds["pinch_distance"] = pinch_dist_stats["mean"] + 2 * pinch_dist_stats["std"]
                _logger.info("Calibration threshold: pinch_distance=%.3f", thresholds["pinch_distance"])

        thresholds["confidence"] = 0.85
        return thresholds

    # ========== 特征提取 ==========

    def _extract_features(self, hand_landmarks: list) -> dict:
        """从手部landmark提取8个关键特征。"""
        def get_xy(idx):
            lm = hand_landmarks[idx]
            if isinstance(lm, dict):
                return float(lm["x"]), float(lm["y"])
            return float(lm[0]), float(lm[1])

        wrist_x, wrist_y = get_xy(0)
        features = {}

        finger_indices = {
            "thumb": (4, 2), "index": (8, 5), "middle": (12, 9),
            "ring": (16, 13), "pinky": (20, 17),
        }
        for name, (tip_idx, mcp_idx) in finger_indices.items():
            tip_x, tip_y = get_xy(tip_idx)
            mcp_x, mcp_y = get_xy(mcp_idx)
            dist_tip = math.sqrt((tip_x - wrist_x) ** 2 + (tip_y - wrist_y) ** 2)
            dist_mcp = math.sqrt((mcp_x - wrist_x) ** 2 + (mcp_y - wrist_y) ** 2)
            features[f"{name}_ratio"] = dist_tip / max(dist_mcp, 1e-6)

        thumb_tip_x, thumb_tip_y = get_xy(4)
        thumb_mcp_x, thumb_mcp_y = get_xy(2)
        features["thumb_direction_y"] = thumb_tip_y - thumb_mcp_y

        index_tip_x, index_tip_y = get_xy(8)
        features["thumb_index_dist"] = math.sqrt(
            (thumb_tip_x - index_tip_x) ** 2 + (thumb_tip_y - index_tip_y) ** 2
        )

        index_mcp_x, index_mcp_y = get_xy(5)
        middle_mcp_x, middle_mcp_y = get_xy(9)
        middle_tip_x, middle_tip_y = get_xy(12)
        v1 = (index_tip_x - index_mcp_x, index_tip_y - index_mcp_y)
        v2 = (middle_tip_x - middle_mcp_x, middle_tip_y - middle_mcp_y)
        cos_angle = (v1[0] * v2[0] + v1[1] * v2[1]) / max(
            math.sqrt(v1[0] ** 2 + v1[1] ** 2) * math.sqrt(v2[0] ** 2 + v2[1] ** 2), 1e-6
        )
        features["index_middle_angle"] = float(np.arccos(np.clip(cos_angle, -1, 1)))

        return features

    def _get_y(self, landmarks: list, idx: int) -> float:
        lm = landmarks[idx]
        if isinstance(lm, dict):
            return float(lm["y"])
        return float(lm[1])

    def reset(self) -> None:
        self._profiles = {}
        self._adapt_history = {}
        self._success_counts = {}
        self._face_profile = {}
        self._enrollment_samples = []
        self._current_enrollment = None
        self._face_baseline_samples = []
        if os.path.exists(self._profile_path):
            try:
                os.remove(self._profile_path)
            except Exception:
                pass
        _logger.info("Calibration data reset")
