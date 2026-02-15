"""
Risk scoring engine.
Aggregates defect data into room-level and property-level risk scores.
"""
from __future__ import annotations

from typing import List

from config import DEFECT_TYPES, PRIORITY_ORDER


def score_frame(analysis: dict) -> dict:
    """
    Compute a risk score (0–100) for a single frame / image analysis.
    Returns dict with score, risk_level, critical_count, defect_counts.
    """
    defects = analysis.get("defects", [])
    if not defects:
        return {
            "score": 0,
            "risk_level": "safe",
            "critical_count": 0,
            "high_count": 0,
            "defect_counts": {},
        }

    weighted_sum = 0.0
    critical_count = 0
    high_count = 0
    defect_counts: dict[str, int] = {}

    for d in defects:
        dtype = d.get("type", "other")
        severity = d.get("severity", "medium")
        cfg = DEFECT_TYPES.get(dtype, DEFECT_TYPES["other"])

        # Base weight from config * severity multiplier
        severity_mult = {"critical": 1.0, "high": 0.75, "medium": 0.5, "low": 0.25}.get(severity, 0.5)
        score_contribution = cfg["weight"] * severity_mult * 25  # scale factor
        weighted_sum += score_contribution

        if severity == "critical":
            critical_count += 1
        elif severity == "high":
            high_count += 1

        defect_counts[dtype] = defect_counts.get(dtype, 0) + 1

    # Clamp to 0-100
    raw_score = min(100, weighted_sum)

    # Risk level
    if raw_score >= 70 or critical_count >= 2:
        risk_level = "critical"
    elif raw_score >= 45 or critical_count >= 1:
        risk_level = "high"
    elif raw_score >= 20:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "score": round(raw_score, 1),
        "risk_level": risk_level,
        "critical_count": critical_count,
        "high_count": high_count,
        "defect_counts": defect_counts,
    }


def score_property(frame_analyses: List[dict]) -> dict:
    """
    Aggregate risk across all frames / rooms for a property-level score.
    Returns dict with overall_score, risk_level, total defects, priority_actions, etc.
    """
    if not frame_analyses:
        return {
            "overall_score": 0,
            "risk_level": "safe",
            "total_defects": 0,
            "critical_defects": 0,
            "frame_scores": [],
            "priority_actions": [],
            "all_defects": [],
        }

    frame_scores = [score_frame(a) for a in frame_analyses]
    all_defects = []
    for i, a in enumerate(frame_analyses):
        for d in a.get("defects", []):
            all_defects.append({**d, "frame_index": i})

    total_defects = len(all_defects)
    critical_defects = sum(1 for d in all_defects if d.get("severity") == "critical")
    high_defects = sum(1 for d in all_defects if d.get("severity") == "high")

    # Overall score: weighted average of frame scores biased toward worst frames
    scores = [fs["score"] for fs in frame_scores]
    if scores:
        avg = sum(scores) / len(scores)
        worst = max(scores)
        overall = 0.4 * avg + 0.6 * worst  # bias toward worst
    else:
        overall = 0

    overall = min(100, overall)

    if overall >= 70 or critical_defects >= 3:
        risk_level = "critical"
    elif overall >= 45 or critical_defects >= 1:
        risk_level = "high"
    elif overall >= 20:
        risk_level = "medium"
    else:
        risk_level = "low"

    # Priority actions: sort defects by severity
    priority_sorted = sorted(
        all_defects,
        key=lambda d: PRIORITY_ORDER.get(d.get("severity", "low"), 3),
    )
    priority_actions = priority_sorted[:5]  # top 5

    return {
        "overall_score": round(overall, 1),
        "risk_level": risk_level,
        "total_defects": total_defects,
        "critical_defects": critical_defects,
        "high_defects": high_defects,
        "frame_scores": frame_scores,
        "priority_actions": priority_actions,
        "all_defects": all_defects,
    }
