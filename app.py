"""
AI-Powered Property Inspector
YOLO for real-time defect detection (~3ms/frame) + Gemini for report generation.
"""
from pathlib import Path

import streamlit as st
from PIL import Image

from config import (
    CONFIDENCE_THRESHOLD, FRAME_INTERVAL_SEC, MAX_FRAMES,
    GEMINI_MODEL, PRIORITY_COLORS, YOLO_CLASS_CONFIG, DEFAULT_CLASS_CONFIG,
)
from detector import (
    detect_and_annotate, detect_image, annotate_yolo,
    extract_frames_from_bytes, decode_uploaded_image,
    get_video_info, get_model_info, load_model,
)
from risk_calculator import score_frame, score_property
from analyzer import configure_gemini, generate_report

# ── Page config ────────────────────────────────────────────────
st.set_page_config(page_title="AI Property Inspector", page_icon="🏠", layout="wide")


def _risk_badge(score: float, level: str):
    color = PRIORITY_COLORS.get(level, "#888")
    st.markdown(
        f'<div style="background:{color};color:white;padding:12px 20px;'
        f'border-radius:10px;text-align:center;font-size:1.4em;font-weight:bold;">'
        f'Risk: {score}/100 — {level.upper()}</div>',
        unsafe_allow_html=True,
    )


def _defect_card(d: dict, frame_idx: int | None = None):
    cfg = YOLO_CLASS_CONFIG.get(d.get("class_name", ""), DEFAULT_CLASS_CONFIG)
    severity = d.get("severity", "medium")
    color = PRIORITY_COLORS.get(severity, "#888")
    conf = d.get("confidence", 0)
    frame_tag = f" (Frame {frame_idx})" if frame_idx is not None else ""
    st.markdown(
        f'<div style="border-left:4px solid {color};padding:8px 12px;margin:4px 0;'
        f'background:#1e1e1e;border-radius:4px;">'
        f'<strong style="color:{color};">[{severity.upper()}]</strong> '
        f'<strong>{cfg["label"]}</strong> — {conf:.0%}{frame_tag}</div>',
        unsafe_allow_html=True,
    )


# ── Header ─────────────────────────────────────────────────────
st.title("🏠 AI Property Inspector")
st.caption("Real-time defect detection with YOLOv8 + AI report generation with Gemini")

# Sidebar
with st.sidebar:
    st.subheader("🤖 Model")
    info = get_model_info()
    if info["is_custom"]:
        st.success(f"Defect model loaded ({info['num_classes']} classes)")
        st.caption(f"Classes: {', '.join(info['classes'].values())}")
    else:
        st.warning("Using default COCO model. Add weights/best.pt for defect detection.")

    st.divider()
    st.subheader("⚙️ Settings")
    conf = st.slider("Confidence threshold", 0.10, 0.90, CONFIDENCE_THRESHOLD, 0.05)
    frame_interval = st.slider("Frame interval (sec)", 0.5, 5.0, FRAME_INTERVAL_SEC, 0.5)
    max_frames = st.slider("Max frames", 5, 120, MAX_FRAMES, 5)

    st.divider()
    st.subheader("🔑 Gemini API (for reports)")
    api_key = st.text_input("Gemini API key (optional)", type="password", help="Only needed for AI report generation")
    if api_key:
        configure_gemini(api_key)
        st.success("Key set")

# ── Tabs ───────────────────────────────────────────────────────
tab_upload, tab_camera, tab_report = st.tabs(["📁 Upload & Inspect", "📷 Live Camera", "📊 Report"])

# ── TAB 1: Upload ─────────────────────────────────────────────
with tab_upload:
    uploaded = st.file_uploader(
        "Upload a video or image",
        type=["mp4", "avi", "mov", "webm", "jpg", "jpeg", "png"],
    )

    if uploaded:
        bytes_data = uploaded.read()
        is_video = Path(uploaded.name).suffix.lower() in (".mp4", ".avi", ".mov", ".webm")

        if is_video:
            vi = get_video_info(bytes_data)
            st.info(f"Video: {vi['width']}x{vi['height']} | {vi['duration_sec']:.1f}s | {vi['fps']:.0f} FPS")

        if st.button("🔍 Run Inspection", type="primary", key="upload_btn"):
            try:
                if is_video:
                    with st.spinner("Extracting frames..."):
                        frame_tuples = extract_frames_from_bytes(bytes_data, frame_interval, max_frames)
                        frames = [ft[0] for ft in frame_tuples]
                        timestamps = [ft[2] for ft in frame_tuples]

                    st.info(f"Extracted {len(frames)} frames. Running YOLO detection...")
                    progress = st.progress(0)
                    all_detections = []
                    all_annotated = []

                    for i, frame in enumerate(frames):
                        ann, det = detect_and_annotate(frame, conf=conf)
                        all_annotated.append(ann)
                        all_detections.append(det)
                        progress.progress((i + 1) / len(frames))

                    progress.empty()

                    # Store for report tab
                    st.session_state["frames"] = frames
                    st.session_state["annotated"] = all_annotated
                    st.session_state["detections"] = all_detections
                    st.session_state["timestamps"] = timestamps
                    st.session_state["mode"] = "video"

                    # Score
                    prop = score_property(all_detections)
                    st.session_state["property_score"] = prop

                    _risk_badge(prop["overall_score"], prop["risk_level"])

                    c1, c2, c3 = st.columns(3)
                    c1.metric("Total Defects", prop["total_defects"])
                    c2.metric("Critical", prop["critical_defects"])
                    c3.metric("Frames with Issues", sum(1 for d in all_detections if d["defects"]))

                    # Show frames
                    st.subheader("Annotated Frames")
                    show_n = min(12, len(all_annotated))
                    cols = st.columns(3)
                    for i in range(show_n):
                        n = len(all_detections[i]["defects"])
                        cols[i % 3].image(
                            all_annotated[i],
                            caption=f"Frame {i} | t={timestamps[i]:.1f}s | {n} defects",
                            use_container_width=True,
                        )
                    if len(all_annotated) > show_n:
                        st.caption(f"Showing {show_n} of {len(all_annotated)} frames.")

                else:
                    # Single image
                    with st.spinner("Running YOLO detection..."):
                        pil_img = decode_uploaded_image(bytes_data)
                        ann, det = detect_and_annotate(pil_img, conf=conf)

                    st.session_state["frames"] = [pil_img]
                    st.session_state["annotated"] = [ann]
                    st.session_state["detections"] = [det]
                    st.session_state["mode"] = "image"

                    prop = score_property([det])
                    st.session_state["property_score"] = prop

                    _risk_badge(prop["overall_score"], prop["risk_level"])

                    c1, c2 = st.columns(2)
                    c1.image(pil_img, caption="Original", use_container_width=True)
                    c2.image(ann, caption=f"Detected ({det['num_detections']} defects)", use_container_width=True)

                    if det["defects"]:
                        st.subheader("Defects Found")
                        for d in det["defects"]:
                            _defect_card(d)

            except Exception as e:
                st.error(f"Error: {e}")


# ── TAB 2: Live Camera ───────────────────────────────────────
with tab_camera:
    st.subheader("📷 Capture & Inspect")
    st.caption("Take photos room-by-room. Each is analyzed instantly by YOLO.")

    if "camera_results" not in st.session_state:
        st.session_state.camera_results = []

    room_name = st.text_input("Room name", placeholder="e.g. Kitchen, Bathroom")
    photo = st.camera_input("Take a photo")

    if photo is not None:
        pil_img = Image.open(photo)
        ann, det = detect_and_annotate(pil_img, conf=conf)
        fs = score_frame(det)

        st.session_state.camera_results.append({
            "room": room_name or f"Capture {len(st.session_state.camera_results) + 1}",
            "image": pil_img, "annotated": ann, "detection": det, "score": fs,
        })

        _risk_badge(fs["score"], fs["risk_level"])
        c1, c2 = st.columns(2)
        c1.image(pil_img, caption="Original", use_container_width=True)
        c2.image(ann, caption=f"Detected ({det['num_detections']} defects)", use_container_width=True)

        for d in det["defects"]:
            _defect_card(d)

    if st.session_state.camera_results:
        st.divider()
        st.subheader("Inspection History")

        cam_dets = [r["detection"] for r in st.session_state.camera_results]
        prop = score_property(cam_dets)
        st.session_state["detections"] = cam_dets
        st.session_state["frames"] = [r["image"] for r in st.session_state.camera_results]
        st.session_state["annotated"] = [r["annotated"] for r in st.session_state.camera_results]
        st.session_state["property_score"] = prop
        st.session_state["mode"] = "camera"
        st.session_state["room_names"] = [r["room"] for r in st.session_state.camera_results]

        _risk_badge(prop["overall_score"], prop["risk_level"])

        cols = st.columns(min(3, len(st.session_state.camera_results)))
        for i, r in enumerate(st.session_state.camera_results):
            cols[i % len(cols)].image(
                r["annotated"],
                caption=f"{r['room']} — Risk: {r['score']['score']}",
                use_container_width=True,
            )

        if st.button("🗑️ Clear captures"):
            st.session_state.camera_results = []
            st.rerun()


# ── TAB 3: Report ─────────────────────────────────────────────
with tab_report:
    st.subheader("📊 Inspection Report")

    if "property_score" not in st.session_state:
        st.info("Run an inspection first (Upload or Camera tab).")
    else:
        prop = st.session_state["property_score"]
        detections = st.session_state.get("detections", [])
        frames = st.session_state.get("frames", [])
        annotated = st.session_state.get("annotated", [])

        _risk_badge(prop["overall_score"], prop["risk_level"])
        st.write("")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Risk Score", f"{prop['overall_score']}/100")
        m2.metric("Total Defects", prop["total_defects"])
        m3.metric("Critical", prop["critical_defects"])
        m4.metric("Frames Analyzed", len(detections))

        # Priority defects
        if prop.get("priority_actions"):
            st.subheader("🚨 Priority Issues")
            for d in prop["priority_actions"]:
                _defect_card(d, frame_idx=d.get("frame_index"))

        # Frame breakdown
        st.subheader("Frame-by-Frame")
        for i, (det, fs) in enumerate(zip(detections, prop.get("frame_scores", []))):
            room_label = ""
            if st.session_state.get("mode") == "camera" and "room_names" in st.session_state:
                names = st.session_state["room_names"]
                room_label = f" — {names[i]}" if i < len(names) else ""

            n = len(det.get("defects", []))
            with st.expander(f"Frame {i}{room_label} | Risk: {fs['score']}/100 | {n} defects"):
                if i < len(annotated):
                    st.image(annotated[i], use_container_width=True)
                for d in det.get("defects", []):
                    _defect_card(d)

        # AI Report generation (Gemini — ONE call)
        st.divider()
        st.subheader("🤖 AI Report (Gemini)")
        if not api_key:
            st.info("Enter Gemini API key in sidebar to generate AI report.")
        elif st.button("📝 Generate AI Report", type="primary"):
            with st.spinner("Generating report with Gemini (one API call)..."):
                report = generate_report(detections, len(detections), GEMINI_MODEL)

            if report.get("error"):
                st.warning(f"Report generation had issues: {report.get('error', '')[:100]}")

            st.markdown(f"### Executive Summary")
            st.write(report.get("executive_summary", ""))

            st.markdown(f"### Risk Level: **{report.get('risk_level', 'unknown').upper()}**")

            actions = report.get("priority_actions", [])
            if actions:
                st.markdown("### Priority Actions")
                for i, a in enumerate(actions, 1):
                    st.write(f"{i}. {a}")

            findings = report.get("detailed_findings", "")
            if findings:
                st.markdown("### Detailed Findings")
                st.write(findings)

            cost = report.get("estimated_repair_cost_inr", "")
            if cost:
                st.markdown(f"### Estimated Repair Cost: ₹{cost}")

            rec = report.get("recommendation", "")
            if rec:
                st.markdown("### Recommendation")
                st.write(rec)
