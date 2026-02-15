"""
Gemini report generator — called ONCE after YOLO detection is complete.
Takes the aggregated defect list and generates a professional inspection summary.
NOT used for detection (YOLO handles that).
"""
from __future__ import annotations

import json
import re
import time
from typing import List

import google.generativeai as genai

_MODEL_FALLBACK = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite"]
MAX_RETRIES = 2
RETRY_DELAY = 10

_REPORT_PROMPT = """You are a professional property inspector AI.
Based on the following defect detection results from an automated YOLO-based inspection system,
generate a professional property inspection report.

DETECTED DEFECTS:
{defect_summary}

STATISTICS:
- Total frames analyzed: {total_frames}
- Frames with defects: {frames_with_defects}
- Total defects found: {total_defects}
- Critical issues: {critical_count}
- High severity issues: {high_count}

Generate a JSON response with:
{{
  "executive_summary": "2-3 sentence overview of the property condition",
  "risk_level": "safe|low|medium|high|critical",
  "priority_actions": ["action 1", "action 2", ...],
  "detailed_findings": "paragraph with detailed analysis",
  "estimated_repair_cost_inr": "rough estimate range like 10000-50000",
  "recommendation": "1-2 sentence recommendation for the buyer/tenant"
}}

Return ONLY valid JSON."""


def configure_gemini(api_key: str):
    genai.configure(api_key=api_key)


def generate_report(
    all_detections: List[dict],
    total_frames: int,
    model_name: str = "gemini-2.5-flash",
) -> dict:
    """
    Generate an inspection report from aggregated YOLO detections.
    all_detections: list of detection dicts (one per frame), each with "defects" list.
    Returns report dict.
    """
    # Build defect summary for the prompt
    all_defects = []
    frames_with_defects = 0
    for det in all_detections:
        defects = det.get("defects", [])
        if defects:
            frames_with_defects += 1
        for d in defects:
            all_defects.append(d)

    if not all_defects:
        return {
            "executive_summary": "No defects were detected during the inspection. The property appears to be in good condition.",
            "risk_level": "safe",
            "priority_actions": [],
            "detailed_findings": "The automated inspection system analyzed all provided frames and found no visible defects.",
            "estimated_repair_cost_inr": "0",
            "recommendation": "The property appears to be in good condition. Standard due diligence recommended.",
        }

    critical_count = sum(1 for d in all_defects if d.get("severity") == "critical")
    high_count = sum(1 for d in all_defects if d.get("severity") == "high")

    # Build text summary of defects
    defect_lines = []
    for i, d in enumerate(all_defects[:20], 1):  # cap at 20 to keep prompt short
        defect_lines.append(
            f"  {i}. {d.get('label', d.get('class_name', 'Unknown'))} "
            f"(confidence: {d.get('confidence', 0):.0%}, severity: {d.get('severity', 'unknown')})"
        )
    defect_summary = "\n".join(defect_lines)

    prompt = _REPORT_PROMPT.format(
        defect_summary=defect_summary,
        total_frames=total_frames,
        frames_with_defects=frames_with_defects,
        total_defects=len(all_defects),
        critical_count=critical_count,
        high_count=high_count,
    )

    # Call Gemini
    models_to_try = [model_name] + [m for m in _MODEL_FALLBACK if m != model_name]
    last_error = None

    for m_name in models_to_try:
        for attempt in range(MAX_RETRIES):
            try:
                model = genai.GenerativeModel(m_name)
                response = model.generate_content(
                    prompt,
                    generation_config=genai.GenerationConfig(
                        temperature=0.2,
                        max_output_tokens=2048,
                        response_mime_type="application/json",
                    ),
                )
                return _parse_report(response.text)
            except Exception as e:
                last_error = e
                err = str(e).lower()
                if "404" in err or "not found" in err:
                    break
                elif "429" in err or "quota" in err:
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY * (attempt + 1))
                    else:
                        break
                else:
                    break

    return {
        "executive_summary": f"Report generation failed: {str(last_error)[:150]}",
        "risk_level": "unknown",
        "priority_actions": [],
        "detailed_findings": "Could not generate AI report. Detection results are still valid.",
        "estimated_repair_cost_inr": "N/A",
        "recommendation": "Review the detected defects manually.",
        "error": str(last_error),
    }


def _parse_report(text: str) -> dict:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return {
        "executive_summary": cleaned[:300] if cleaned else "Could not parse report.",
        "risk_level": "unknown",
        "priority_actions": [],
        "detailed_findings": cleaned,
        "estimated_repair_cost_inr": "N/A",
        "recommendation": "Review detections manually.",
    }
