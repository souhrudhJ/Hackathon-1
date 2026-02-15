"""
Configuration for the AI-Powered Property Inspection System.
YOLO for real-time detection, Gemini for report generation.
"""
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
WEIGHTS_DIR = os.path.join(PROJECT_ROOT, "weights")
OUTPUTS_DIR = os.path.join(PROJECT_ROOT, "outputs")
os.makedirs(WEIGHTS_DIR, exist_ok=True)
os.makedirs(OUTPUTS_DIR, exist_ok=True)

# ── YOLO model ─────────────────────────────────────────────────
CUSTOM_WEIGHTS = os.path.join(WEIGHTS_DIR, "best.pt")
FALLBACK_WEIGHTS = "yolov8n.pt"
CONFIDENCE_THRESHOLD = 0.25
IOU_THRESHOLD = 0.45
IMAGE_SIZE = 640

# ── Gemini (report generation only) ───────────────────────────
GEMINI_MODEL = "gemini-2.5-flash"

# ── YOLO class → display info mapping ─────────────────────────
# The trained model has these 5 classes (from Roboflow dataset):
YOLO_CLASS_CONFIG = {
    "crack":           {"label": "Crack",              "weight": 0.85, "priority": "high",   "color": (0, 50, 255)},
    "mold":            {"label": "Mold / Fungal Growth","weight": 0.80, "priority": "high",   "color": (0, 180, 0)},
    "peeling_paint":   {"label": "Peeling Paint",      "weight": 0.50, "priority": "medium", "color": (0, 200, 200)},
    "stairstep_crack": {"label": "Stairstep Crack",    "weight": 0.90, "priority": "critical","color": (0, 0, 220)},
    "water_seepage":   {"label": "Water Seepage",      "weight": 0.90, "priority": "critical","color": (200, 100, 0)},
}

# Fallback for unknown class names
DEFAULT_CLASS_CONFIG = {"label": "Defect", "weight": 0.50, "priority": "medium", "color": (128, 128, 128)}

PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
PRIORITY_COLORS = {
    "critical": "#FF0000",
    "high":     "#FF6600",
    "medium":   "#FFcc00",
    "low":      "#00CC00",
}

# ── Video processing ───────────────────────────────────────────
FRAME_INTERVAL_SEC = 1.0   # extract one frame every N seconds
MAX_FRAMES = 60            # more frames OK — YOLO is fast
