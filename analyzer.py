"""
Gemini Vision analyzer – the brain of the inspection system.
Sends images to Gemini and gets back structured defect analysis with bounding boxes.
"""
from __future__ import annotations

import json
import re
import time
from typing import List, Optional

import google.generativeai as genai
from PIL import Image

from config import DEFECT_TYPES

# Models to try in order (fallback chain)
_MODEL_FALLBACK_CHAIN = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.5-pro",
]

MAX_RETRIES = 2
RETRY_BASE_DELAY = 12  # seconds

# ── Gemini prompt ───────────────────────────────────────────────
_SYSTEM_PROMPT = """You are an expert property / building inspector AI.
Analyze the provided image for ANY building or property defects.

Defect categories you MUST check for:
- structural_crack: major cracks in load-bearing walls, beams, columns, foundation
- wall_crack: surface cracks on walls (hairline, diagonal, horizontal, vertical)
- ceiling_crack: cracks or sagging in ceilings
- floor_damage: cracked tiles, damaged flooring, uneven surfaces
- water_damage: water stains, dampness, leakage marks, wet patches, water seepage
- mold: mold spots, mildew, fungal growth (dark patches, green/black spots)
- peeling_paint: paint peeling, bubbling, flaking, discoloration
- electrical_hazard: damaged switches, outlets, sparking, burn marks
- exposed_wiring: visible/exposed electrical wires not properly insulated
- broken_fixture: broken door handles, taps, railings, fittings, light fixtures
- plumbing_issue: leaking pipes, damaged taps, blocked drains, rust on pipes
- window_damage: cracked glass, damaged window frames, broken locks
- staircase_damage: damaged steps, broken railings, uneven treads
- other: any other property defect not in the above list

For EACH defect found, return:
- "type": one of the category keys above
- "severity": "critical" | "high" | "medium" | "low"
- "description": one sentence describing the specific defect
- "bbox": [y_min, x_min, y_max, x_max] as integers 0-1000 (normalized coords)

Also provide:
- "room_condition": "good" | "fair" | "poor" | "critical"
- "summary": 2-3 sentence professional summary of findings

IMPORTANT RULES:
- Only report REAL defects you are confident about. Do NOT flag normal building features (windows, doors, furniture) as defects.
- If no defects are found, return an empty defects list and say the room is in good condition.
- Be specific in descriptions. Say exactly what the defect is and where.
- Bounding boxes must tightly surround only the defect, not the whole image.

Return ONLY valid JSON in this exact format:
{
  "defects": [
    {
      "type": "wall_crack",
      "severity": "high",
      "description": "Diagonal crack approximately 30cm long on the upper left wall near the ceiling junction",
      "bbox": [50, 100, 200, 300]
    }
  ],
  "room_condition": "poor",
  "summary": "The room shows significant wall damage with multiple cracks indicating potential structural settlement. Immediate professional assessment recommended."
}"""


def configure_gemini(api_key: str):
    """Set the Gemini API key."""
    genai.configure(api_key=api_key)


def analyze_image(
    image: Image.Image,
    model_name: str = "gemini-2.0-flash",
) -> dict:
    """
    Send a single PIL image to Gemini Vision and get structured defect analysis.
    Returns dict with keys: defects, room_condition, summary.
    Retries on rate-limit errors and falls back to alternative models.
    """
    models_to_try = [model_name] + [m for m in _MODEL_FALLBACK_CHAIN if m != model_name]

    last_error = None
    for m_name in models_to_try:
        for attempt in range(MAX_RETRIES):
            try:
                model = genai.GenerativeModel(m_name)
                response = model.generate_content(
                    [_SYSTEM_PROMPT, image],
                    generation_config=genai.GenerationConfig(
                        temperature=0.1,
                        max_output_tokens=4096,
                        response_mime_type="application/json",
                    ),
                )
                return _parse_response(response.text)
            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                if "404" in err_str or "not found" in err_str:
                    # Model doesn't exist — skip to next model immediately
                    break
                elif "429" in err_str or "quota" in err_str or "resource" in err_str:
                    # Rate limited — wait and retry, or move to next model
                    wait = RETRY_BASE_DELAY * (attempt + 1)
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(wait)
                        continue
                    else:
                        break  # try next model
                else:
                    # Other error — don't retry
                    raise

    # All models and retries exhausted
    return {
        "defects": [],
        "room_condition": "unknown",
        "summary": f"API error after retries: {str(last_error)[:200]}. "
                   "Check your API key quota at https://ai.dev/rate-limit — "
                   "you may need to wait a minute or use a different key.",
        "error": str(last_error),
    }


def analyze_frames(
    frames: List[Image.Image],
    model_name: str = "gemini-2.0-flash",
    progress_callback=None,
) -> List[dict]:
    """
    Analyze multiple frames sequentially.
    Returns list of analysis dicts (one per frame).
    progress_callback(current, total) is called after each frame.
    """
    results = []
    for i, frame in enumerate(frames):
        try:
            result = analyze_image(frame, model_name)
        except Exception as e:
            result = {
                "defects": [],
                "room_condition": "unknown",
                "summary": f"Analysis failed: {str(e)}",
                "error": str(e),
            }
        results.append(result)
        if progress_callback:
            progress_callback(i + 1, len(frames))
    return results


def _parse_response(text: str) -> dict:
    """Extract JSON from Gemini response text (handles markdown code fences)."""
    # Strip markdown code fences if present
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                return {
                    "defects": [],
                    "room_condition": "unknown",
                    "summary": f"Could not parse AI response. Raw: {text[:300]}",
                }
        else:
            return {
                "defects": [],
                "room_condition": "unknown",
                "summary": f"Could not parse AI response. Raw: {text[:300]}",
            }

    # Validate and normalize defect types
    defects = data.get("defects", [])
    valid_types = set(DEFECT_TYPES.keys())
    for d in defects:
        if d.get("type") not in valid_types:
            d["type"] = "other"
        if d.get("severity") not in ("critical", "high", "medium", "low"):
            d["severity"] = "medium"
        if "bbox" not in d or not isinstance(d["bbox"], list) or len(d["bbox"]) != 4:
            d["bbox"] = [0, 0, 1000, 1000]  # fallback: full image

    return {
        "defects": defects,
        "room_condition": data.get("room_condition", "unknown"),
        "summary": data.get("summary", "No summary available."),
    }
