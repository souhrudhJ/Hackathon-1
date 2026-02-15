"""
PDF report generator for property inspection.
Report includes: annotated images, defect list per frame, risk score, executive summary, priority actions.
"""
from __future__ import annotations

import io
import os
import re
import tempfile
from datetime import datetime
from typing import List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image as RLImage,
    Table,
    TableStyle,
    PageBreak,
)

from config import DEFECT_TYPES
from detector import annotate_image


# Max width for images in PDF (inches)
IMG_MAX_WIDTH = 5.5
# Max frames to include in PDF to keep file size reasonable
MAX_FRAMES_IN_PDF = 24


def _pil_to_reportlab_image(pil_img, max_width_inch=IMG_MAX_WIDTH):
    """Convert PIL Image to ReportLab Image flowable with constrained size (points)."""
    w, h = pil_img.size
    aspect = h / w if w else 1
    width_pt = max_width_inch * inch
    height_pt = width_pt * aspect
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        pil_img.save(f, format="PNG")
        path = f.name
    # ReportLab reads the file at build time; temp file is left for OS cleanup
    return RLImage(path, width=width_pt, height=height_pt)


def _markdown_to_plain(text: str) -> str:
    """Strip markdown to plain text for PDF paragraphs."""
    if not text:
        return ""
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*]\s+", "• ", text, flags=re.MULTILINE)
    return text.strip()


def generate_pdf(
    frames: List,
    analyses: List[dict],
    property_score: dict,
    full_report_text: str = "",
    timestamps: List[float] = None,
) -> bytes:
    """
    Build PDF report. Returns PDF as bytes.

    Args:
        frames: List of PIL Images (RGB)
        analyses: List of analysis dicts (defects, summary, room_condition)
        property_score: From score_property()
        full_report_text: Optional full report markdown from Gemini
        timestamps: Optional list of frame timestamps (for video)
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        name="ReportTitle",
        parent=styles["Heading1"],
        fontSize=18,
        spaceAfter=12,
    )
    heading_style = ParagraphStyle(
        name="SectionHeading",
        parent=styles["Heading2"],
        fontSize=12,
        spaceBefore=14,
        spaceAfter=8,
    )
    body_style = ParagraphStyle(
        name="Body",
        parent=styles["Normal"],
        fontSize=9,
        spaceAfter=6,
    )
    small_style = ParagraphStyle(
        name="Small",
        parent=styles["Normal"],
        fontSize=8,
        spaceAfter=4,
    )

    story = []

    # ── Title and date ───────────────────────────────────────────
    story.append(Paragraph("Property Inspection Report", title_style))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%d %B %Y, %H:%M')}", small_style))
    story.append(Spacer(1, 12))

    # ── Risk score ──────────────────────────────────────────────
    score = property_score.get("overall_score", 0)
    level = property_score.get("risk_level", "unknown").upper()
    total_defects = property_score.get("total_defects", 0)
    critical = property_score.get("critical_defects", 0)
    high = property_score.get("high_defects", 0)

    score_table = Table(
        [
            ["Overall risk score", f"{score}/100"],
            ["Risk level", level],
            ["Total defects", str(total_defects)],
            ["Critical", str(critical)],
            ["High", str(high)],
        ],
        colWidths=[2.5 * inch, 2 * inch],
    )
    score_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f0f0")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#fafafa")]),
            ]
        )
    )
    story.append(score_table)
    story.append(Spacer(1, 16))

    # ── Executive summary ──────────────────────────────────────
    if full_report_text:
        story.append(Paragraph("Executive summary", heading_style))
        for block in _markdown_to_plain(full_report_text).split("\n\n")[:6]:
            if block.strip():
                story.append(Paragraph(block.replace("\n", " "), body_style))
        story.append(Spacer(1, 12))

    # ── Annotated images and defects (required) ─────────────────
    n_include = min(len(frames), len(analyses), MAX_FRAMES_IN_PDF)
    timestamps = timestamps or [0.0] * n_include

    for i in range(n_include):
        frame = frames[i]
        analysis = analyses[i]
        ts = timestamps[i] if i < len(timestamps) else 0.0

        story.append(Paragraph(f"Frame {i + 1} (t = {ts:.1f}s)", heading_style))

        # Annotated image (required)
        ann = annotate_image(frame, analysis)
        story.append(_pil_to_reportlab_image(ann))
        story.append(Spacer(1, 8))

        # Defects list (required)
        defects = analysis.get("defects", [])
        if defects:
            story.append(Paragraph("Defects identified:", small_style))
            for d in defects:
                dtype = d.get("type", "other")
                cfg = DEFECT_TYPES.get(dtype, DEFECT_TYPES["other"])
                label = cfg["label"]
                sev = d.get("severity", "medium").upper()
                desc = (d.get("description") or "")[:200]
                story.append(
                    Paragraph(
                        f"• <b>{label}</b> [{sev}] — {desc}",
                        small_style,
                    )
                )
        else:
            story.append(Paragraph("No defects identified in this frame.", small_style))

        story.append(Spacer(1, 6))
        if (i + 1) % 6 == 0 and i + 1 < n_include:
            story.append(PageBreak())

    # ── Priority actions ────────────────────────────────────────
    actions = property_score.get("priority_actions", [])[:10]
    if actions:
        story.append(PageBreak())
        story.append(Paragraph("Priority actions", heading_style))
        for idx, act in enumerate(actions, 1):
            dtype = act.get("type", "other")
            cfg = DEFECT_TYPES.get(dtype, DEFECT_TYPES["other"])
            label = cfg["label"]
            sev = act.get("severity", "medium").upper()
            desc = (act.get("description") or "")[:180]
            story.append(
                Paragraph(
                    f"{idx}. <b>{label}</b> [{sev}] — {desc}",
                    body_style,
                )
            )

    doc.build(story)
    buffer.seek(0)
    return buffer.read()
