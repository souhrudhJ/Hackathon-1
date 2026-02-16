"""
Configuration for the AI-Powered Property Inspection System.
Uses Google Gemini Vision as the primary detection engine.
"""
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUTS_DIR = os.path.join(PROJECT_ROOT, "outputs")
os.makedirs(OUTPUTS_DIR, exist_ok=True)

# ── Gemini API ──────────────────────────────────────────────────
GEMINI_MODEL = "gemini-2.5-flash"  # fast, supports vision + bounding boxes
GEMINI_API_KEY = ""  # hardcoded; not shown on dashboard

# ── Defect categories and severity weights ─────────────────────
# Each defect type has a base severity weight (0-1) used for risk scoring.
DEFECT_TYPES = {
    "structural_crack":    {"label": "Structural Crack",      "weight": 0.95, "priority": "critical", "color": (0, 0, 220)},
    "wall_crack":          {"label": "Wall Crack",            "weight": 0.80, "priority": "high",     "color": (0, 50, 255)},
    "ceiling_crack":       {"label": "Ceiling Crack",         "weight": 0.85, "priority": "high",     "color": (0, 80, 255)},
    "floor_damage":        {"label": "Floor / Tile Damage",   "weight": 0.70, "priority": "high",     "color": (0, 120, 255)},
    "water_damage":        {"label": "Water Leakage / Dampness", "weight": 0.90, "priority": "critical", "color": (200, 100, 0)},
    "mold":                {"label": "Mold / Fungal Growth",  "weight": 0.85, "priority": "high",     "color": (0, 150, 0)},
    "peeling_paint":       {"label": "Paint Deterioration",   "weight": 0.40, "priority": "medium",   "color": (0, 200, 200)},
    "electrical_hazard":   {"label": "Electrical Hazard",     "weight": 1.00, "priority": "critical", "color": (0, 0, 255)},
    "exposed_wiring":      {"label": "Exposed Wiring",        "weight": 1.00, "priority": "critical", "color": (0, 0, 255)},
    "broken_fixture":      {"label": "Broken Fixture",        "weight": 0.55, "priority": "medium",   "color": (180, 0, 180)},
    "plumbing_issue":      {"label": "Plumbing Issue",        "weight": 0.75, "priority": "high",     "color": (200, 100, 0)},
    "window_damage":       {"label": "Window / Door Damage",  "weight": 0.50, "priority": "medium",   "color": (150, 150, 0)},
    "staircase_damage":    {"label": "Staircase Damage",      "weight": 0.80, "priority": "high",     "color": (100, 0, 200)},
    "other":               {"label": "Other Defect",          "weight": 0.30, "priority": "low",      "color": (128, 128, 128)},
}

PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
PRIORITY_COLORS = {
    "critical": "#FF0000",
    "high":     "#FF6600",
    "medium":   "#FFcc00",
    "low":      "#00CC00",
}

# ── Video processing ───────────────────────────────────────────
FRAME_INTERVAL_SEC = 2.0   # extract one frame every N seconds
MAX_FRAMES = 30            # cap to keep Gemini API usage reasonable
