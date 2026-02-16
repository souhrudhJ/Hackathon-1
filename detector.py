"""
Frame extraction and visual annotation engine.
Handles: video → frames, image decoding, drawing bounding boxes from Gemini results.
"""
from __future__ import annotations

import os
import tempfile
from typing import List, Tuple, Optional

import cv2
import numpy as np
from PIL import Image

from config import DEFECT_TYPES, FRAME_INTERVAL_SEC, MAX_FRAMES


# ── Frame extraction ───────────────────────────────────────────

def extract_frames(
    video_path: str,
    interval_sec: float = FRAME_INTERVAL_SEC,
    max_frames: int = MAX_FRAMES,
) -> List[Tuple[Image.Image, int, float]]:
    """
    Extract frames from video at a fixed time interval.
    Returns list of (PIL Image RGB, frame_index, timestamp_sec).
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_interval = max(1, int(fps * interval_sec))
    frames: List[Tuple[Image.Image, int, float]] = []
    frame_idx = 0
    read_idx = 0

    while len(frames) < max_frames:
        ret, frame = cap.read()
        if not ret:
            break
        if read_idx % frame_interval == 0:
            t_sec = read_idx / fps
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb)
            frames.append((pil_img, frame_idx, t_sec))
            frame_idx += 1
        read_idx += 1

    cap.release()
    return frames


def extract_frames_from_bytes(
    video_bytes: bytes,
    interval_sec: float = FRAME_INTERVAL_SEC,
    max_frames: int = MAX_FRAMES,
) -> List[Tuple[Image.Image, int, float]]:
    """Extract frames from video uploaded as bytes."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(video_bytes)
        path = f.name
    try:
        return extract_frames(path, interval_sec, max_frames)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def decode_uploaded_image(image_bytes: bytes) -> Image.Image:
    """Decode uploaded image bytes to PIL Image."""
    npy = np.frombuffer(image_bytes, np.uint8)
    bgr = cv2.imdecode(npy, cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError("Could not decode image")
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


# ── Visual annotation ─────────────────────────────────────────

def annotate_image(image: Image.Image, analysis: dict) -> Image.Image:
    """
    Draw bounding boxes and labels on image from Gemini analysis.
    analysis: dict with "defects" list, each having type, severity, description, bbox.
    Returns annotated PIL Image (RGB).
    """
    img = np.array(image).copy()  # RGB
    h, w = img.shape[:2]
    defects = analysis.get("defects", [])

    for defect in defects:
        dtype = defect.get("type", "other")
        severity = defect.get("severity", "medium")
        desc = defect.get("description", dtype)
        bbox = defect.get("bbox", [0, 0, 1000, 1000])

        # Convert Gemini normalized coords (0-1000) to pixel coords
        # Gemini returns [y_min, x_min, y_max, x_max]
        y_min, x_min, y_max, x_max = bbox
        x1 = int(x_min * w / 1000)
        y1 = int(y_min * h / 1000)
        x2 = int(x_max * w / 1000)
        y2 = int(y_max * h / 1000)

        # Clamp
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w - 1, x2), min(h - 1, y2)

        # Color based on defect type config (BGR in config, but we're in RGB)
        cfg = DEFECT_TYPES.get(dtype, DEFECT_TYPES["other"])
        bgr_color = cfg["color"]
        rgb_color = (bgr_color[2], bgr_color[1], bgr_color[0])

        # Thickness based on severity (bolder for readability)
        thickness = {"critical": 5, "high": 4, "medium": 3, "low": 3}.get(severity, 3)

        # Draw box (thicker outline)
        cv2.rectangle(img, (x1, y1), (x2, y2), rgb_color, thickness)

        # Label (bigger text, bolder)
        label = cfg["label"]
        sev_tag = severity.upper()
        label_text = f"{label} [{sev_tag}]"

        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.75
        (tw, th_text), baseline = cv2.getTextSize(label_text, font, font_scale, 2)

        # Background rectangle for label (more padding)
        pad = 10
        label_y = max(y1 - th_text - pad, 0)
        cv2.rectangle(img, (x1, label_y), (x1 + tw + pad * 2, label_y + th_text + pad * 2), rgb_color, -1)
        cv2.putText(img, label_text, (x1 + pad // 2, label_y + th_text + pad), font, font_scale, (255, 255, 255), 2)

    return Image.fromarray(img)


def get_video_info(video_bytes: bytes) -> dict:
    """Get basic info about an uploaded video (from bytes)."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(video_bytes)
        path = f.name
    try:
        return _get_video_info_from_path(path)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def get_video_info_from_path(video_path: str) -> dict:
    """Get basic info about a video file (from path). Use for local recordings."""
    return _get_video_info_from_path(video_path)


def _get_video_info_from_path(path: str) -> dict:
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {path}")
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return {
            "fps": fps,
            "total_frames": total,
            "duration_sec": total / fps if fps else 0,
            "width": w,
            "height": h,
        }
    finally:
        cap.release()
