"""
Detection engine: YOLO for real-time defect detection + frame extraction + annotation.
"""
from __future__ import annotations

import os
import tempfile
from typing import List, Tuple, Optional

import cv2
import numpy as np
from PIL import Image
from ultralytics import YOLO

from config import (
    CUSTOM_WEIGHTS, FALLBACK_WEIGHTS,
    CONFIDENCE_THRESHOLD, IOU_THRESHOLD, IMAGE_SIZE,
    YOLO_CLASS_CONFIG, DEFAULT_CLASS_CONFIG,
    FRAME_INTERVAL_SEC, MAX_FRAMES,
)


# ── Model loading ──────────────────────────────────────────────

_model_cache: Optional[YOLO] = None


def load_model() -> YOLO:
    """Load YOLO model. Uses custom defect weights if available, else fallback."""
    global _model_cache
    if _model_cache is not None:
        return _model_cache
    path = CUSTOM_WEIGHTS if os.path.isfile(CUSTOM_WEIGHTS) else FALLBACK_WEIGHTS
    _model_cache = YOLO(path)
    return _model_cache


def get_model_info() -> dict:
    """Return info about the loaded model."""
    model = load_model()
    path = CUSTOM_WEIGHTS if os.path.isfile(CUSTOM_WEIGHTS) else FALLBACK_WEIGHTS
    return {
        "path": path,
        "is_custom": os.path.isfile(CUSTOM_WEIGHTS),
        "classes": model.names,
        "num_classes": len(model.names),
    }


# ── YOLO detection ─────────────────────────────────────────────

def detect_image(
    image: Image.Image,
    conf: float = CONFIDENCE_THRESHOLD,
    iou: float = IOU_THRESHOLD,
) -> dict:
    """
    Run YOLO on a single PIL image. Returns dict compatible with risk_calculator:
    {
        "defects": [{"class_name", "confidence", "bbox", "type", "severity"}],
        "num_detections": int,
    }
    """
    model = load_model()
    img_np = np.array(image)
    results = model.predict(img_np, conf=conf, iou=iou, imgsz=IMAGE_SIZE, verbose=False)
    result = results[0] if results else None

    defects = []
    if result and result.boxes is not None:
        names = result.names or {}
        for i in range(len(result.boxes)):
            cls_id = int(result.boxes.cls[i].cpu().numpy())
            confidence = float(result.boxes.conf[i].cpu().numpy())
            xyxy = result.boxes.xyxy[i].cpu().numpy().tolist()
            class_name = names.get(cls_id, f"class_{cls_id}")

            cfg = YOLO_CLASS_CONFIG.get(class_name, DEFAULT_CLASS_CONFIG)
            # Assign severity based on confidence + weight
            if confidence >= 0.7 and cfg["weight"] >= 0.85:
                severity = "critical"
            elif confidence >= 0.5 and cfg["weight"] >= 0.7:
                severity = "high"
            elif confidence >= 0.3:
                severity = "medium"
            else:
                severity = "low"

            defects.append({
                "class_name": class_name,
                "confidence": confidence,
                "bbox": xyxy,  # [x1, y1, x2, y2] pixel coords
                "type": class_name,
                "severity": severity,
                "label": cfg["label"],
                "priority": cfg["priority"],
            })

    return {"defects": defects, "num_detections": len(defects)}


def detect_and_annotate(
    image: Image.Image,
    conf: float = CONFIDENCE_THRESHOLD,
) -> Tuple[Image.Image, dict]:
    """Run detection and return (annotated_image, detection_result)."""
    result = detect_image(image, conf=conf)
    annotated = annotate_yolo(image, result)
    return annotated, result


# ── Annotation ─────────────────────────────────────────────────

def annotate_yolo(image: Image.Image, detection: dict) -> Image.Image:
    """Draw YOLO bounding boxes on PIL image."""
    img = np.array(image).copy()
    for d in detection.get("defects", []):
        x1, y1, x2, y2 = map(int, d["bbox"])
        conf = d["confidence"]
        class_name = d["class_name"]
        severity = d["severity"]

        cfg = YOLO_CLASS_CONFIG.get(class_name, DEFAULT_CLASS_CONFIG)
        bgr = cfg["color"]
        rgb = (bgr[2], bgr[1], bgr[0])

        thickness = 3 if severity in ("critical", "high") else 2
        cv2.rectangle(img, (x1, y1), (x2, y2), rgb, thickness)

        label = f"{cfg['label']} {conf:.0%}"
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.5
        (tw, th), _ = cv2.getTextSize(label, font, scale, 1)
        ly = max(y1 - th - 6, 0)
        cv2.rectangle(img, (x1, ly), (x1 + tw + 4, ly + th + 8), rgb, -1)
        cv2.putText(img, label, (x1 + 2, ly + th + 4), font, scale, (255, 255, 255), 1)

    return Image.fromarray(img)


# ── Frame extraction ───────────────────────────────────────────

def extract_frames_from_bytes(
    video_bytes: bytes,
    interval_sec: float = FRAME_INTERVAL_SEC,
    max_frames: int = MAX_FRAMES,
) -> List[Tuple[Image.Image, int, float]]:
    """Extract frames from uploaded video bytes."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(video_bytes)
        path = f.name
    try:
        return _extract_frames(path, interval_sec, max_frames)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _extract_frames(
    video_path: str,
    interval_sec: float,
    max_frames: int,
) -> List[Tuple[Image.Image, int, float]]:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    step = max(1, int(fps * interval_sec))
    frames = []
    idx = 0
    read_idx = 0
    while len(frames) < max_frames:
        ret, frame = cap.read()
        if not ret:
            break
        if read_idx % step == 0:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append((Image.fromarray(rgb), idx, read_idx / fps))
            idx += 1
        read_idx += 1
    cap.release()
    return frames


def decode_uploaded_image(image_bytes: bytes) -> Image.Image:
    npy = np.frombuffer(image_bytes, np.uint8)
    bgr = cv2.imdecode(npy, cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError("Could not decode image")
    return Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))


def get_video_info(video_bytes: bytes) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(video_bytes)
        path = f.name
    try:
        cap = cv2.VideoCapture(path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        return {"fps": fps, "total_frames": total, "duration_sec": total / fps, "width": w, "height": h}
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
