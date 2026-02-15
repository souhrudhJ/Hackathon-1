"""
AI-Powered Property Inspection System
Upload video/images or use live camera → Gemini Vision detects ALL defect types →
annotated results + risk scores + professional summary.
"""
from pathlib import Path

import streamlit as st
from PIL import Image

from config import (
    DEFECT_TYPES,
    PRIORITY_COLORS,
    FRAME_INTERVAL_SEC,
    MAX_FRAMES,
    GEMINI_MODEL,
)
from analyzer import configure_gemini, analyze_image, analyze_frames
from detector import (
    extract_frames_from_bytes,
    decode_uploaded_image,
    annotate_image,
    get_video_info,
)
from risk_calculator import score_frame, score_property

# ── Page config ────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Property Inspector",
    page_icon="🏠",
    layout="wide",
)


def _get_api_key() -> str | None:
    """Get Gemini API key from sidebar input or session."""
    if "gemini_key" not in st.session_state:
        st.session_state.gemini_key = ""
    with st.sidebar:
        st.subheader("🔑 Gemini API Key")
        key = st.text_input(
            "Enter your Google Gemini API key",
            value=st.session_state.gemini_key,
            type="password",
            help="Free at https://aistudio.google.com/apikey",
        )
        if key:
            st.session_state.gemini_key = key
            configure_gemini(key)
            st.success("API key set")
            return key
        else:
            st.warning("Required to run analysis.")
            st.markdown("[Get a free API key →](https://aistudio.google.com/apikey)")
            return None


def _render_risk_badge(score: float, level: str):
    """Render a colored risk score badge."""
    color = PRIORITY_COLORS.get(level, "#888")
    st.markdown(
        f'<div style="background:{color};color:white;padding:12px 20px;'
        f'border-radius:10px;text-align:center;font-size:1.5em;font-weight:bold;">'
        f'Risk: {score}/100 — {level.upper()}</div>',
        unsafe_allow_html=True,
    )


def _render_defect_card(defect: dict, frame_idx: int | None = None):
    """Render a single defect as a styled card."""
    dtype = defect.get("type", "other")
    cfg = DEFECT_TYPES.get(dtype, DEFECT_TYPES["other"])
    severity = defect.get("severity", "medium")
    color = PRIORITY_COLORS.get(severity, "#888")
    desc = defect.get("description", "No description")
    frame_tag = f" (Frame {frame_idx})" if frame_idx is not None else ""

    st.markdown(
        f'<div style="border-left:4px solid {color};padding:8px 12px;margin:6px 0;'
        f'background:#1e1e1e;border-radius:4px;">'
        f'<strong style="color:{color};">[{severity.upper()}]</strong> '
        f'<strong>{cfg["label"]}</strong>{frame_tag}<br/>'
        f'<span style="color:#ccc;font-size:0.9em;">{desc}</span></div>',
        unsafe_allow_html=True,
    )


# ── MAIN ───────────────────────────────────────────────────────

st.title("🏠 AI-Powered Property Inspector")
st.caption(
    "Detect structural cracks, water damage, electrical hazards, mold, exposed wiring, "
    "broken fixtures, and more — powered by Google Gemini Vision."
)

api_key = _get_api_key()

# Sidebar settings
with st.sidebar:
    st.divider()
    st.subheader("⚙️ Settings")
    frame_interval = st.slider("Frame interval (sec)", 0.5, 5.0, FRAME_INTERVAL_SEC, 0.5)
    max_frames = st.slider("Max frames (video)", 5, 60, MAX_FRAMES, 5)

tab_upload, tab_camera, tab_report = st.tabs(["📁 Upload & Inspect", "📷 Live Camera", "📊 Report"])

# ── TAB 1: Upload & Inspect ───────────────────────────────────
with tab_upload:
    uploaded = st.file_uploader(
        "Upload a video or image of the property",
        type=["mp4", "avi", "mov", "webm", "jpg", "jpeg", "png"],
    )

    if uploaded and api_key:
        bytes_data = uploaded.read()
        is_video = Path(uploaded.name).suffix.lower() in (".mp4", ".avi", ".mov", ".webm")

        if is_video:
            info = get_video_info(bytes_data)
            st.info(
                f"Video: {info['width']}x{info['height']} | "
                f"{info['duration_sec']:.1f}s | {info['fps']:.0f} FPS"
            )

        if st.button("🔍 Run Inspection", type="primary", key="upload_run"):
            try:
                if is_video:
                    with st.spinner("Extracting frames from video..."):
                        frame_tuples = extract_frames_from_bytes(bytes_data, frame_interval, max_frames)
                        frames = [ft[0] for ft in frame_tuples]
                        timestamps = [ft[2] for ft in frame_tuples]

                    st.info(f"Extracted {len(frames)} frames. Analyzing each with Gemini Vision...")
                    progress = st.progress(0, text="Analyzing frames...")

                    def update_progress(current, total):
                        progress.progress(current / total, text=f"Analyzing frame {current}/{total}...")

                    analyses = analyze_frames(frames, GEMINI_MODEL, progress_callback=update_progress)
                    progress.empty()

                    # Check if any analysis had errors
                    errors = [a for a in analyses if a.get("error")]
                    if errors:
                        st.warning(f"{len(errors)} frame(s) had API errors. Results may be partial.")

                    # Store results in session state for report tab
                    st.session_state["analyses"] = analyses
                    st.session_state["frames"] = frames
                    st.session_state["timestamps"] = timestamps
                    st.session_state["mode"] = "video"

                    # Score
                    prop_score = score_property(analyses)
                    st.session_state["property_score"] = prop_score

                    _render_risk_badge(prop_score["overall_score"], prop_score["risk_level"])

                    col_m1, col_m2, col_m3 = st.columns(3)
                    col_m1.metric("Total Defects", prop_score["total_defects"])
                    col_m2.metric("Critical", prop_score["critical_defects"])
                    col_m3.metric("High", prop_score.get("high_defects", 0))

                    # Show annotated frames
                    st.subheader("Annotated Frames")
                    display_count = min(12, len(frames))
                    cols = st.columns(3)
                    for i in range(display_count):
                        ann = annotate_image(frames[i], analyses[i])
                        n_defs = len(analyses[i].get("defects", []))
                        fs = score_frame(analyses[i])
                        caption = f"Frame {i} | t={timestamps[i]:.1f}s | {n_defs} defects | Risk: {fs['score']}"
                        cols[i % 3].image(ann, caption=caption, use_container_width=True)

                    if len(frames) > display_count:
                        st.caption(f"Showing first {display_count} of {len(frames)} frames.")

                else:
                    # Single image
                    with st.spinner("Analyzing image with Gemini Vision..."):
                        pil_img = decode_uploaded_image(bytes_data)
                        analysis = analyze_image(pil_img, GEMINI_MODEL)

                    if analysis.get("error"):
                        st.error(f"API error: {analysis['summary']}")
                    else:
                        st.session_state["analyses"] = [analysis]
                        st.session_state["frames"] = [pil_img]
                        st.session_state["timestamps"] = [0.0]
                        st.session_state["mode"] = "image"

                        fs = score_frame(analysis)
                        prop_score = score_property([analysis])
                        st.session_state["property_score"] = prop_score

                        _render_risk_badge(fs["score"], fs["risk_level"])

                        c1, c2 = st.columns(2)
                        c1.image(pil_img, caption="Original", use_container_width=True)
                        ann = annotate_image(pil_img, analysis)
                        c2.image(ann, caption="Defects Detected", use_container_width=True)

                        st.subheader("AI Analysis")
                        st.write(analysis.get("summary", ""))

                        if analysis.get("defects"):
                            st.subheader("Defects Found")
                            for d in analysis["defects"]:
                                _render_defect_card(d)

            except Exception as e:
                st.error(f"Error during inspection: {str(e)}")
                if "429" in str(e) or "quota" in str(e).lower():
                    st.warning(
                        "**Rate limit hit.** Your Gemini API key has exceeded its quota. Options:\n"
                        "1. Wait 1-2 minutes and try again\n"
                        "2. Use a different API key\n"
                        "3. Check your quota at https://ai.dev/rate-limit"
                    )

    elif uploaded and not api_key:
        st.warning("Enter your Gemini API key in the sidebar to run analysis.")


# ── TAB 2: Live Camera ────────────────────────────────────────
with tab_camera:
    st.subheader("📷 Capture & Inspect")
    st.caption(
        "Use your webcam or phone camera to capture photos of rooms. "
        "Each capture is analyzed instantly for defects."
    )

    if not api_key:
        st.warning("Enter your Gemini API key in the sidebar first.")
    else:
        # Initialize session storage for camera captures
        if "camera_results" not in st.session_state:
            st.session_state.camera_results = []

        room_name = st.text_input("Room name (optional)", placeholder="e.g. Kitchen, Bedroom 1, Bathroom")
        camera_photo = st.camera_input("Take a photo")

        if camera_photo is not None:
            pil_img = Image.open(camera_photo)
            try:
                with st.spinner("Analyzing with Gemini Vision..."):
                    analysis = analyze_image(pil_img, GEMINI_MODEL)

                if analysis.get("error"):
                    st.error(f"API error: {analysis['summary']}")
                else:
                    fs = score_frame(analysis)
                    ann = annotate_image(pil_img, analysis)

                    # Store result
                    st.session_state.camera_results.append({
                        "room": room_name or f"Capture {len(st.session_state.camera_results) + 1}",
                        "image": pil_img,
                        "annotated": ann,
                        "analysis": analysis,
                        "score": fs,
                    })

                    _render_risk_badge(fs["score"], fs["risk_level"])

                    c1, c2 = st.columns(2)
                    c1.image(pil_img, caption="Original", use_container_width=True)
                    c2.image(ann, caption="Defects Detected", use_container_width=True)

                    st.write(analysis.get("summary", ""))
                    for d in analysis.get("defects", []):
                        _render_defect_card(d)

            except Exception as e:
                st.error(f"Error: {str(e)}")
                if "429" in str(e) or "quota" in str(e).lower():
                    st.warning("Rate limit hit. Wait 1-2 minutes or use a different API key.")

        # Show history of captures
        if st.session_state.camera_results:
            st.divider()
            st.subheader("Inspection History")

            # Build analyses list for report tab
            cam_analyses = [r["analysis"] for r in st.session_state.camera_results]
            cam_frames = [r["image"] for r in st.session_state.camera_results]
            prop_score = score_property(cam_analyses)

            st.session_state["analyses"] = cam_analyses
            st.session_state["frames"] = cam_frames
            st.session_state["timestamps"] = [0.0] * len(cam_frames)
            st.session_state["property_score"] = prop_score
            st.session_state["mode"] = "camera"
            st.session_state["room_names"] = [r["room"] for r in st.session_state.camera_results]

            _render_risk_badge(prop_score["overall_score"], prop_score["risk_level"])

            cols = st.columns(min(3, len(st.session_state.camera_results)))
            for i, r in enumerate(st.session_state.camera_results):
                col = cols[i % len(cols)]
                col.image(r["annotated"], caption=f"{r['room']} — Risk: {r['score']['score']}", use_container_width=True)

            if st.button("🗑️ Clear all captures"):
                st.session_state.camera_results = []
                st.rerun()


# ── TAB 3: Report ─────────────────────────────────────────────
with tab_report:
    st.subheader("📊 Inspection Report")

    if "property_score" not in st.session_state:
        st.info("Run an inspection in the Upload or Camera tab first.")
    else:
        prop = st.session_state["property_score"]
        analyses = st.session_state.get("analyses", [])
        frames = st.session_state.get("frames", [])

        # Header
        _render_risk_badge(prop["overall_score"], prop["risk_level"])
        st.write("")

        # Metrics row
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Overall Risk Score", f"{prop['overall_score']}/100")
        m2.metric("Total Defects", prop["total_defects"])
        m3.metric("Critical Issues", prop["critical_defects"])
        m4.metric("Frames Analyzed", len(analyses))

        # Priority actions
        if prop.get("priority_actions"):
            st.subheader("🚨 Priority Actions")
            for i, action in enumerate(prop["priority_actions"], 1):
                _render_defect_card(action, frame_idx=action.get("frame_index"))

        # Frame-by-frame breakdown
        st.subheader("Frame-by-Frame Breakdown")
        frame_scores = prop.get("frame_scores", [])
        for i, (analysis, fs) in enumerate(zip(analyses, frame_scores)):
            room_label = ""
            if st.session_state.get("mode") == "camera" and "room_names" in st.session_state:
                room_names = st.session_state["room_names"]
                if i < len(room_names):
                    room_label = f" — {room_names[i]}"

            with st.expander(
                f"{'Frame' if st.session_state.get('mode') != 'camera' else 'Room'} {i}{room_label} "
                f"| Risk: {fs['score']}/100 ({fs['risk_level'].upper()}) "
                f"| {len(analysis.get('defects', []))} defects"
            ):
                if i < len(frames):
                    c1, c2 = st.columns(2)
                    c1.image(frames[i], caption="Original", use_container_width=True)
                    ann = annotate_image(frames[i], analysis)
                    c2.image(ann, caption="Annotated", use_container_width=True)
                st.write(analysis.get("summary", ""))
                for d in analysis.get("defects", []):
                    _render_defect_card(d)

        # AI summaries
        st.subheader("AI Summary")
        summaries = [a.get("summary", "") for a in analyses if a.get("summary")]
        if summaries:
            for s in summaries:
                st.write(f"- {s}")
