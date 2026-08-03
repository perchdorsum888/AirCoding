#!/usr/bin/env python3
"""AirCoding — 真实摄像头测试与Debug分析程序。

使用真实摄像头 + MediaPipe 识别管线，引导用户做出手势，
记录每帧的 landmark、识别结果、置信度、耗时，生成测试日志。
支持根据日志自动化分析识别问题。

使用方式：
    python test_runner.py                    # 交互式测试（打开摄像头）
    python test_runner.py --analyze <log>    # 分析测试日志
    python test_runner.py --frames 30        # 每手势采集30帧
"""

import sys
import os
import time
import json
import argparse
import traceback
import threading
from pathlib import Path
from datetime import datetime

PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))
sys.dont_write_bytecode = True

import cv2
import numpy as np

from src.core.enums import GestureType
from src.core.config_manager import ConfigManager
from src.camera.image_processor import ImageProcessor
from src.recognition.hand_classifier import HandClassifier
from src.recognition.phone_call_detector import PhoneCallDetector
from src.recognition.gesture_validator import GestureValidator
from src.recognition.calibrator import Calibrator
from src.utils.logger import get_logger

_logger = get_logger("TestRunner")

TEST_LOG_DIR = Path(os.environ.get("APPDATA", "")) / "AirCoding" / "test_logs"
TEST_LOG_DIR.mkdir(parents=True, exist_ok=True)


class CameraTestRunner:
    """真实摄像头测试运行器。

    打开摄像头，运行 MediaPipe 识别，引导用户做出手势，
    记录真实识别结果并生成测试日志。
    """

    TEST_GESTURES = [
        (GestureType.OK, "👌", "OK Gesture", "Form a circle with thumb and index finger, keep other fingers straight"),
        (GestureType.OPEN_PALM, "✋", "Open Palm", "Open your palm with all five fingers spread, facing the camera"),
        (GestureType.SCISSOR, "✌️", "Scissor", "Extend index and middle fingers, curl ring and pinky"),
        (GestureType.PINCH, "🤏", "Pinch", "Touch the tip of your thumb to the tip of your index finger"),
        (GestureType.PHONE_CALL, "🤙", "Phone Call", "Thumb + pinky extended, others curled (or thumb to ear + pinky to mouth)"),
    ]

    def __init__(self, frames_per_gesture=30, auto_mode=False):
        self.frames_per_gesture = frames_per_gesture
        self.auto_mode = auto_mode
        self.config_manager = ConfigManager()
        self.image_processor = ImageProcessor(self.config_manager)
        self.classifier = HandClassifier()
        self.phone_detector = PhoneCallDetector()
        self.validator = GestureValidator(
            confirm_frames=3,
            cooldown_ms=500,
            confidence_threshold=0.85,
        )
        self.calibrator = Calibrator()

        # MediaPipe 模型
        self._mp_hands = None
        self._mp_face = None
        self._cap = None

        # 测试结果
        self.test_results = []
        self.start_time = None

    def _init_camera(self):
        """初始化摄像头和MediaPipe模型。"""
        try:
            print("Initializing camera...", flush=True)

            # DSHOW后端优先（不容易卡死），MSMF备选
            for backend in [cv2.CAP_DSHOW, cv2.CAP_MSMF]:
                self._cap = cv2.VideoCapture(0, backend)
                if self._cap.isOpened():
                    backend_name = "DSHOW" if backend == cv2.CAP_DSHOW else "MSMF"
                    print(f"  Backend {backend_name} OK", flush=True)
                    break
            if not self._cap.isOpened():
                self._cap = cv2.VideoCapture(0)
            if not self._cap.isOpened():
                print("ERROR: Failed to open camera!", flush=True)
                print("Please ensure: 1) a camera is connected 2) no other app is using it 3) restart the PC", flush=True)
                return False

            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            # 验证能读到帧（带3秒超时，防止摄像头被占用时卡死）
            import threading
            read_result = [False, None]
            def _try_read():
                read_result[0], read_result[1] = self._cap.read()
            t = threading.Thread(target=_try_read, daemon=True)
            t.start()
            t.join(timeout=3.0)
            if t.is_alive():
                print("ERROR: Camera read timeout (3s)!", flush=True)
                print("The camera may be held by another app. Close the main AirCoding app and retry.", flush=True)
                self._cap.release()
                return False
            if not read_result[0] or read_result[1] is None:
                print("ERROR: Camera opened but cannot read frames!", flush=True)
                self._cap.release()
                return False

            w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            print(f"Camera ready: {w}x{h}", flush=True)

            print("Initializing MediaPipe models...", flush=True)
            import mediapipe as mp
            self._mp_hands = mp.solutions.hands.Hands(
                static_image_mode=False,
                max_num_hands=1,
                min_detection_confidence=0.6,
                min_tracking_confidence=0.5,
                model_complexity=0,
            )
            self._mp_face = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=False,
                max_num_faces=1,
                refine_landmarks=False,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            print("MediaPipe models ready", flush=True)
            return True
        except Exception as e:
            print(f"Initialization failed: {e}", flush=True)
            traceback.print_exc()
            return False

    def _capture_frame(self):
        """采集一帧并运行识别。"""
        ret, frame = self._cap.read()
        if not ret or frame is None:
            _logger.warning("Camera read failed ret=%s", ret)
            return None

        try:
            # 预处理
            processed, light = self.image_processor.preprocess(frame)
            rgb = cv2.cvtColor(processed, cv2.COLOR_BGR2RGB)

            # 手部识别
            hand_result = self._mp_hands.process(rgb)
            hand_landmarks = None
            handedness = "Right"
            hand_confidence = 0.0

            if hand_result.multi_hand_landmarks:
                lm_list = hand_result.multi_hand_landmarks[0]
                hand_landmarks = [(lm.x, lm.y, lm.z) for lm in lm_list.landmark]
                if hand_result.multi_handedness:
                    handedness = hand_result.multi_handedness[0].classification[0].label
                    hand_confidence = hand_result.multi_handedness[0].classification[0].score

            # 面部识别
            face_result = self._mp_face.process(rgb)
            face_landmarks = None
            face_detected = False

            if face_result.multi_face_landmarks:
                lm_list = face_result.multi_face_landmarks[0]
                face_landmarks = [(lm.x, lm.y, lm.z) for lm in lm_list.landmark]
                face_detected = True

            return (frame, hand_landmarks, handedness, hand_confidence, face_landmarks, face_detected, light)
        except Exception as e:
            _logger.error("Frame processing exception: %s\n%s", e, traceback.format_exc())
            return None

    def _classify(self, hand_landmarks, handedness, face_landmarks):
        """运行完整分类管线，返回详细结果。"""
        result = {
            'gesture': 'none',
            'confidence': 0.0,
            'phone_detected': False,
            'phone_confidence': 0.0,
            'confirmed': False,
            'finger_ratios': {},
            'errors': [],
        }

        if hand_landmarks is None:
            return result

        try:
            # 手势分类
            gesture, confidence = self.classifier.classify(hand_landmarks, handedness)
            result['gesture'] = gesture.value
            result['confidence'] = round(confidence, 4)

            # 打电话检测
            phone_det, phone_conf = self.phone_detector.detect(hand_landmarks, face_landmarks, handedness)
            result['phone_detected'] = phone_det
            result['phone_confidence'] = round(phone_conf, 4)

            # 验证器
            result['confirmed'] = self.validator.validate(gesture, confidence)

            # 记录手指ratio（用于debug分析）
            points = np.array([[lm[0], lm[1]] for lm in hand_landmarks[:21]])
            wrist = points[0]
            for name, tip, mcp in [("thumb",4,2),("index",8,5),("middle",12,9),("ring",16,13),("pinky",20,17)]:
                dt = float(np.linalg.norm(points[tip][:2] - wrist[:2]))
                dm = float(np.linalg.norm(points[mcp][:2] - wrist[:2]))
                result['finger_ratios'][name] = round(dt / max(dm, 1e-6), 3)

        except Exception as e:
            result['errors'].append(str(e))
            result['errors'].append(traceback.format_exc())

        return result

    def run(self):
        """运行完整测试流程。"""
        print("=" * 60, flush=True)
        print("AirCoding — Real Camera Test Runner", flush=True)
        print("=" * 60, flush=True)
        print(f"Frames per gesture: {self.frames_per_gesture}", flush=True)
        print(f"Test gestures: {len(self.TEST_GESTURES)}", flush=True)
        print(f"Log dir: {TEST_LOG_DIR}", flush=True)
        print("=" * 60, flush=True)

        if not self._init_camera():
            print("Camera initialization failed, exiting.", flush=True)
            print("Please ensure: 1) a camera is connected 2) no other app is using it 3) restart the PC", flush=True)
            return

        self.start_time = time.time()
        log_file = TEST_LOG_DIR / f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        print(f"Test log: {log_file}")

        # 写入元数据
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(json.dumps({
                "type": "test_meta",
                "timestamp": datetime.now().isoformat(),
                "frames_per_gesture": self.frames_per_gesture,
                "classifier_thresholds": self.classifier._thresholds,
                "calibrator_thresholds": self.calibrator.get_thresholds() or "无校准",
                "camera_resolution": f"{int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}",
            }, ensure_ascii=False) + "\n")

        # 逐一手势测试
        for i, (expected, emoji, name, instruction) in enumerate(self.TEST_GESTURES):
            print(f"\n[{i+1}/{len(self.TEST_GESTURES)}] {emoji} {name}")
            print(f"  Instruction: {instruction}")
            if not self.auto_mode:
                print(f"  Make the gesture and hold it, press Enter to start capture...")
                input()
            else:
                print(f"  [AUTO MODE] Capture starts in 3s...")
                time.sleep(3)

            result = self._test_gesture(expected, emoji, name, instruction, log_file)
            self.test_results.append(result)

            # 实时显示结果
            detected = result['detected_count']
            total = result['total_frames']
            accuracy = detected / total * 100 if total > 0 else 0
            print(f"  Result: {detected}/{total} frames correct ({accuracy:.0f}%)")
            if result['avg_confidence'] > 0:
                print(f"  Avg confidence: {result['avg_confidence']:.3f}")
            if result['misidentified_as']:
                print(f"  Misidentified as: {result['misidentified_as']}")

        self._generate_report(log_file)
        self._cleanup()

    def _test_gesture(self, expected, emoji, name, instruction, log_file):
        """测试单个手势（真实摄像头采集）。"""
        result = {
            'gesture': expected.value,
            'emoji': emoji,
            'name': name,
            'total_frames': 0,
            'detected_count': 0,
            'avg_confidence': 0.0,
            'misidentified_as': [],
            'frame_details': [],
            'hand_detected_count': 0,
            'face_detected_count': 0,
        }

        print(f"  Capturing ({self.frames_per_gesture} frames)...", end='', flush=True)
        _logger.info("Starting capture %s (expected gesture=%s, %d frames)", name, expected.value, self.frames_per_gesture)

        with open(log_file, 'a', encoding='utf-8') as f:
            for frame_idx in range(self.frames_per_gesture):
                try:
                    capture_data = self._capture_frame()

                    if capture_data is None:
                        _logger.warning("Frame#%d capture failed, skipping", frame_idx)
                        continue

                    frame, hand_lm, handedness, hand_conf, face_lm, face_det, light = capture_data

                    frame_data = {
                        'frame': frame_idx,
                        'timestamp': time.time() - self.start_time,
                        'expected': expected.value,
                        'hand_detected': hand_lm is not None,
                        'face_detected': face_det,
                        'handedness': handedness,
                        'hand_confidence': round(hand_conf, 4),
                        'light': light.value if light else 'unknown',
                    }

                    if hand_lm is not None:
                        result['hand_detected_count'] += 1
                        _logger.info("Frame#%d: hand detection success (handedness=%s, conf=%.2f, %d points)",
                                    frame_idx, handedness, hand_conf, len(hand_lm))
                    if face_det:
                        result['face_detected_count'] += 1

                    # 分类
                    cls_result = self._classify(hand_lm, handedness, face_lm)
                    frame_data.update(cls_result)

                    _logger.info("Frame#%d: classification result gesture=%s conf=%.3f phone=%s confirmed=%s",
                                frame_idx,
                                cls_result['gesture'],
                                cls_result['confidence'],
                                cls_result['phone_detected'],
                                cls_result['confirmed'])

                    # 统计
                    result['total_frames'] += 1
                    if cls_result['gesture'] == expected.value:
                        result['detected_count'] += 1
                    elif cls_result['gesture'] != 'none':
                        result['misidentified_as'].append(cls_result['gesture'])
                    result['avg_confidence'] += cls_result['confidence']

                    # 写入日志
                    f.write(json.dumps(frame_data, ensure_ascii=False) + "\n")

                except Exception as e:
                    _logger.error("Frame#%d processing exception: %s\n%s", frame_idx, e, traceback.format_exc())
                    result['frame_details'].append({
                        'frame': frame_idx,
                        'error': str(e),
                    })

                # 间隔（~100ms = 10fps）
                time.sleep(0.1)

        if result['total_frames'] > 0:
            result['avg_confidence'] /= result['total_frames']
        result['misidentified_as'] = list(set(result['misidentified_as']))

        print(" done")
        return result

    def _generate_report(self, log_file):
        """生成TEST REPORT。"""
        total_time = time.time() - self.start_time
        total_frames = sum(r['total_frames'] for r in self.test_results)
        total_detected = sum(r['detected_count'] for r in self.test_results)
        overall_accuracy = total_detected / total_frames * 100 if total_frames > 0 else 0

        print("\n" + "=" * 60)
        print("TEST REPORT")
        print("=" * 60)
        print(f"Total time: {total_time:.1f}s")
        print(f"Total frames: {total_frames}")
        print(f"Overall accuracy: {overall_accuracy:.1f}%")
        print()

        for r in self.test_results:
            accuracy = r['detected_count'] / r['total_frames'] * 100 if r['total_frames'] > 0 else 0
            hand_rate = r['hand_detected_count'] / r['total_frames'] * 100 if r['total_frames'] > 0 else 0
            status = "✅" if accuracy >= 80 else "⚠️" if accuracy >= 50 else "❌"
            print(f"  {status} {r['emoji']} {r['name']:8s}: {r['detected_count']}/{r['total_frames']} ({accuracy:.0f}%)"
                  f"  手检测={hand_rate:.0f}%  置信度={r['avg_confidence']:.3f}"
                  f"  误识别={r['misidentified_as'] or '无'}")

        # 写入汇总
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps({
                "type": "test_summary",
                "total_time": total_time,
                "total_frames": total_frames,
                "overall_accuracy": overall_accuracy,
                "results": [{
                    "gesture": r['gesture'],
                    "detected": r['detected_count'],
                    "total": r['total_frames'],
                    "accuracy": r['detected_count'] / r['total_frames'] if r['total_frames'] > 0 else 0,
                    "hand_detected": r['hand_detected_count'],
                    "face_detected": r['face_detected_count'],
                    "avg_confidence": r['avg_confidence'],
                    "misidentified_as": r['misidentified_as'],
                } for r in self.test_results],
            }, ensure_ascii=False) + "\n")

        print(f"\nTest log saved: {log_file}")
        print(f"Analyze: python test_runner.py --analyze {log_file}")

    def _cleanup(self):
        """释放资源。"""
        if self._cap:
            self._cap.release()
        if self._mp_hands:
            self._mp_hands.close()
        if self._mp_face:
            self._mp_face.close()
        cv2.destroyAllWindows()
        print("Camera closed, resources released")


class TestAnalyzer:
    """测试日志自动化分析器。"""

    def __init__(self, log_file):
        self.log_file = Path(log_file)
        self.frames = []
        self.meta = {}
        self.summary = {}

    def analyze(self):
        if not self.log_file.exists():
            print(f"Log file not found: {self.log_file}")
            return

        print(f"Analyzed log: {self.log_file}")
        print("=" * 60)

        with open(self.log_file, 'r', encoding='utf-8') as f:
            for line in f:
                data = json.loads(line)
                if data.get("type") == "test_meta":
                    self.meta = data
                elif data.get("type") == "test_summary":
                    self.summary = data
                else:
                    self.frames.append(data)

        print(f"Frames: {len(self.frames)}")
        print(f"Camera: {self.meta.get('camera_resolution', '?')}")
        print(f"Classifier thresholds: {self.meta.get('classifier_thresholds', {})}")
        print()

        self._analyze_per_gesture()
        self._analyze_detection_rate()
        self._analyze_confidence()
        self._analyze_misidentification()
        self._analyze_finger_ratios()
        self._analyze_errors()
        self._suggest_fixes()

    def _analyze_per_gesture(self):
        print("--- Per-Gesture Results ---")
        gesture_stats = {}
        for frame in self.frames:
            expected = frame.get('expected', 'unknown')
            if expected not in gesture_stats:
                gesture_stats[expected] = {'total': 0, 'correct': 0, 'confs': [], 'hand_det': 0, 'face_det': 0}
            gesture_stats[expected]['total'] += 1
            gesture_stats[expected]['hand_det'] += 1 if frame.get('hand_detected') else 0
            gesture_stats[expected]['face_det'] += 1 if frame.get('face_detected') else 0
            if frame.get('gesture') == expected:
                gesture_stats[expected]['correct'] += 1
            gesture_stats[expected]['confs'].append(frame.get('confidence', 0))

        for g, s in gesture_stats.items():
            acc = s['correct'] / s['total'] * 100 if s['total'] > 0 else 0
            hand_rate = s['hand_det'] / s['total'] * 100 if s['total'] > 0 else 0
            face_rate = s['face_det'] / s['total'] * 100 if s['total'] > 0 else 0
            avg_c = sum(s['confs']) / len(s['confs']) if s['confs'] else 0
            status = "✅" if acc >= 80 else "⚠️" if acc >= 50 else "❌"
            print(f"  {status} {g:12s}: acc={acc:5.1f}%  hand={hand_rate:.0f}%  face={face_rate:.0f}%  conf={avg_c:.3f}")
        print()

    def _analyze_detection_rate(self):
        print("--- Detection Rate Analysis ---")
        total = len(self.frames)
        hand_det = sum(1 for f in self.frames if f.get('hand_detected'))
        face_det = sum(1 for f in self.frames if f.get('face_detected'))
        print(f"  Hand detection: {hand_det}/{total} ({hand_det/total*100:.0f}%)")
        print(f"  Face detection: {face_det}/{total} ({face_det/total*100:.0f}%)")
        if hand_det < total * 0.8:
            print("  ⚠️ Low hand detection rate — check lighting, hand position, camera angle")
        if face_det < total * 0.8:
            print("  ⚠️ Low face detection rate — make sure your face is in frame")
        print()

    def _analyze_confidence(self):
        print("--- Confidence Analysis ---")
        confs = [f.get('confidence', 0) for f in self.frames if f.get('hand_detected')]
        if confs:
            print(f"  avg={sum(confs)/len(confs):.3f} min={min(confs):.3f} max={max(confs):.3f}")
            low = [f for f in self.frames if f.get('confidence', 0) < 0.85 and f.get('hand_detected')]
            if low:
                print(f"  Low-confidence frames (<0.85): {len(low)}")
        print()

    def _analyze_misidentification(self):
        print("--- Misidentification Analysis ---")
        misident = {}
        for frame in self.frames:
            expected = frame.get('expected', 'unknown')
            classified = frame.get('gesture', 'none')
            if classified != expected and classified != 'none':
                key = f"{expected} → {classified}"
                misident[key] = misident.get(key, 0) + 1
        if misident:
            for pattern, count in sorted(misident.items(), key=lambda x: -x[1]):
                print(f"  {pattern}: {count} times")
        else:
            print("  No misidentifications")
        print()

    def _analyze_finger_ratios(self):
        print("--- Finger Ratio Analysis (debug thresholds) ---")
        gesture_ratios = {}
        for frame in self.frames:
            expected = frame.get('expected', 'unknown')
            ratios = frame.get('finger_ratios', {})
            if ratios:
                if expected not in gesture_ratios:
                    gesture_ratios[expected] = {k: [] for k in ratios}
                for k, v in ratios.items():
                    gesture_ratios[expected][k].append(v)

        for gesture, ratio_lists in gesture_ratios.items():
            print(f"  {gesture}:")
            for finger, values in ratio_lists.items():
                if values:
                    print(f"    {finger:8s}: avg={sum(values)/len(values):.3f} min={min(values):.3f} max={max(values):.3f}")
        print()

    def _analyze_errors(self):
        print("--- Error Analysis ---")
        errors = [f for f in self.frames if f.get('errors')]
        if errors:
            print(f"  Anomalous frames: {len(errors)}")
            for e in errors[:3]:
                print(f"    frame#{e.get('frame', '?')}: {e['errors'][0]}")
        else:
            print("  No anomalies")
        print()

    def _suggest_fixes(self):
        print("--- Recommendations ---")
        suggestions = []

        # 检查检测率
        total = len(self.frames)
        hand_det = sum(1 for f in self.frames if f.get('hand_detected'))
        if hand_det < total * 0.8:
            suggestions.append("⚠️ 手部检测率低 — 检查光照条件、手部是否完全在画面内、摄像头分辨率")

        # 检查低准确率手势
        gesture_stats = {}
        for frame in self.frames:
            expected = frame.get('expected', 'unknown')
            if expected not in gesture_stats:
                gesture_stats[expected] = {'total': 0, 'correct': 0, 'confs': []}
            gesture_stats[expected]['total'] += 1
            if frame.get('gesture') == expected:
                gesture_stats[expected]['correct'] += 1
            gesture_stats[expected]['confs'].append(frame.get('confidence', 0))

        for g, s in gesture_stats.items():
            acc = s['correct'] / s['total'] if s['total'] > 0 else 0
            avg_conf = sum(s['confs']) / len(s['confs']) if s['confs'] else 0
            if acc < 0.5:
                suggestions.append(f"❌ {g}: 准确率={acc:.0f}% — 需检查分类器逻辑或重新校准")
            elif acc < 0.8:
                suggestions.append(f"⚠️ {g}: 准确率={acc:.0f}% — 建议重新校准或调整阈值")
            elif avg_conf < 0.88:
                suggestions.append(f"💡 {g}: 置信度偏低({avg_conf:.3f}) — 建议重新校准")

        if suggestions:
            for s in suggestions:
                print(f"  {s}")
        else:
            print("  ✅ All gestures recognized correctly")
        print()


def main():
    parser = argparse.ArgumentParser(description="AirCoding真实摄像头测试程序")
    parser.add_argument('--analyze', metavar='LOG', help='分析测试日志')
    parser.add_argument('--frames', type=int, default=30, help='每手势采集帧数（默认30）')
    parser.add_argument('--auto', action='store_true', help='全自动模式（无需按Enter）')
    args = parser.parse_args()

    if args.analyze:
        TestAnalyzer(args.analyze).analyze()
        if not args.auto:
            input("\n分析完成，按Enter退出...")
    else:
        try:
            runner = CameraTestRunner(frames_per_gesture=args.frames, auto_mode=args.auto)
            runner.run()
        except KeyboardInterrupt:
            print("\nInterrupted by user", flush=True)
        except Exception as e:
            print(f"\nProgram error: {e}", flush=True)
            traceback.print_exc()
        finally:
            if not args.auto:
                input("\n按Enter退出...")


if __name__ == "__main__":
    main()
