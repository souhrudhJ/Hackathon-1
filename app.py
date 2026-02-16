"""
AI-Powered Property Inspection System
Upload video/images or use live camera → Gemini Vision detects ALL defect types →
annotated results + risk scores + professional summary.
"""
import os
import tempfile
import threading
import time
from pathlib import Path

import cv2
import streamlit as st
from PIL import Image

from config import (
    DEFECT_TYPES,
    PRIORITY_COLORS,
    FRAME_INTERVAL_SEC,
    MAX_FRAMES,
    GEMINI_MODEL,
    GEMINI_API_KEY,
)
from analyzer import configure_gemini, analyze_image, analyze_frames, generate_property_report

# Configure API once at startup (key not shown on dashboard)
configure_gemini(GEMINI_API_KEY)
from detector import (
    extract_frames,
    extract_frames_from_bytes,
    decode_uploaded_image,
    annotate_image,
    get_video_info,
    get_video_info_from_path,
)
from risk_calculator import score_frame, score_property
from report_generator import generate_pdf

# ── Page config ────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Property Inspector",
    page_icon="",
    layout="wide",
)


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


def _record_webcam_to_file(stop_flag: list, output_path: str) -> None:
    """Background thread: capture webcam and write to file until stop_flag[0] is True.
    Uses AVI + MJPEG for compatibility with OpenCV on Windows."""
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        return
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    out = cv2.VideoWriter(output_path, fourcc, 10.0, (w, h))
    try:
        while not stop_flag[0]:
            ret, frame = cap.read()
            if not ret:
                break
            out.write(frame)
            time.sleep(0.1)
    finally:
        cap.release()
        out.release()


# ── MAIN ───────────────────────────────────────────────────────

st.title("AI-Powered Property Inspector")
st.caption(
    "Structural cracks, water damage, electrical hazards, mold, exposed wiring, "
    "broken fixtures. AI-powered defect detection and reporting."
)

# Sidebar settings
with st.sidebar:
    st.divider()
    st.subheader("Settings")
    frame_interval = st.slider("Frame interval (sec)", 0.5, 5.0, FRAME_INTERVAL_SEC, 0.5)
    max_frames = st.slider("Max frames (video)", 5, 60, MAX_FRAMES, 5)

tab_upload, tab_camera, tab_report = st.tabs(["Upload & Inspect", "Live Camera", "Report"])

# ── TAB 1: Upload & Inspect ───────────────────────────────────
with tab_upload:
    uploaded = st.file_uploader(
        "Upload a video or image of the property",
        type=["mp4", "avi", "mov", "webm", "jpg", "jpeg", "png"],
    )

    if uploaded:
        bytes_data = uploaded.read()
        is_video = Path(uploaded.name).suffix.lower() in (".mp4", ".avi", ".mov", ".webm")

        if is_video:
            info = get_video_info(bytes_data)
            st.info(
                f"Video: {info['width']}x{info['height']} | "
                f"{info['duration_sec']:.1f}s | {info['fps']:.0f} FPS"
            )

        if st.button("Run Inspection", type="primary", key="upload_run"):
            try:
                if is_video:
                    with st.spinner("Extracting frames (OpenCV)..."):
                        frame_tuples = extract_frames_from_bytes(bytes_data, frame_interval, max_frames)
                        frames = [ft[0] for ft in frame_tuples]
                        timestamps = [ft[2] for ft in frame_tuples]

                    st.info(f"**Step 1 — Live detection:** {len(frames)} frames. Results appear below as each frame is analyzed.")
                    progress = st.progress(0, text="Analyzing frame 1...")

                    analyses = []
                    live_container = st.container()

                    for i, frame in enumerate(frames):
                        progress.progress((i + 1) / len(frames), text=f"Analyzing frame {i + 1}/{len(frames)}...")
                        analysis = analyze_image(frame, GEMINI_MODEL)
                        analyses.append(analysis)

                        # Show this frame’s result immediately (progressive display)
                        with live_container:
                            ann = annotate_image(frame, analysis)
                            n_defs = len(analysis.get("defects", []))
                            fs = score_frame(analysis)
                            row1, row2 = st.columns([1, 1])
                            with row1:
                                st.image(ann, caption=f"Frame {i + 1} · t={timestamps[i]:.1f}s · {n_defs} defects · Risk {fs['score']}/100", use_container_width=True)
                            with row2:
                                st.caption(f"**{analysis.get('room_condition', 'unknown').upper()}**")
                                st.write((analysis.get("summary") or "")[:280] + ("…" if len(analysis.get("summary") or "") > 280 else ""))
                            st.divider()

                    progress.empty()

                    # Check for errors
                    errors = [a for a in analyses if a.get("error")]
                    if errors:
                        st.warning(f"{len(errors)} frame(s) had API errors. Results may be partial.")

                    # Store for report tab
                    st.session_state["analyses"] = analyses
                    st.session_state["frames"] = frames
                    st.session_state["timestamps"] = timestamps
                    st.session_state["mode"] = "video"

                    prop_score = score_property(analyses)
                    st.session_state["property_score"] = prop_score

                    _render_risk_badge(prop_score["overall_score"], prop_score["risk_level"])
                    col_m1, col_m2, col_m3 = st.columns(3)
                    col_m1.metric("Total Defects", prop_score["total_defects"])
                    col_m2.metric("Critical", prop_score["critical_defects"])
                    col_m3.metric("High", prop_score.get("high_defects", 0))

                    # Step 2 — Full report (generated after detections are shown)
                    st.subheader("Step 2 — Full property report")
                    with st.spinner("Generating report from findings..."):
                        full_report = generate_property_report(analyses, GEMINI_MODEL)
                    st.session_state["full_report_text"] = full_report
                    st.markdown(full_report)

                    # PDF download (same as Report tab)
                    try:
                        pdf_bytes = generate_pdf(
                            frames=frames,
                            analyses=analyses,
                            property_score=prop_score,
                            full_report_text=full_report,
                            timestamps=timestamps,
                        )
                        st.download_button(
                            label="Download PDF Report",
                            data=pdf_bytes,
                            file_name=f"property_inspection_report_{prop_score['overall_score']:.0f}.pdf",
                            mime="application/pdf",
                            type="primary",
                            key="pdf_download_upload_video",
                        )
                    except Exception as e:
                        st.warning(f"PDF could not be generated: {e}")

                else:
                    # Single image
                    with st.spinner("Analyzing image..."):
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

                        # PDF download for single image
                        try:
                            pdf_bytes = generate_pdf(
                                frames=[pil_img],
                                analyses=[analysis],
                                property_score=prop_score,
                                full_report_text=analysis.get("summary", ""),
                                timestamps=[0.0],
                            )
                            st.download_button(
                                label="Download PDF Report",
                                data=pdf_bytes,
                                file_name=f"property_inspection_report_{fs['score']:.0f}.pdf",
                                mime="application/pdf",
                                type="primary",
                                key="pdf_download_upload_image",
                            )
                        except Exception as e:
                            st.warning(f"PDF could not be generated: {e}")

            except Exception as e:
                st.error(f"Error during inspection: {str(e)}")
                if "429" in str(e) or "quota" in str(e).lower():
                    st.warning(
                        "**Rate limit hit.** API quota exceeded. Wait 1–2 minutes and try again."
                    )

# ── TAB 2: Live Camera ────────────────────────────────────────
with tab_camera:
    st.subheader("Capture & Inspect")
    st.caption(
        "Use your webcam to take photos or record a short video. "
        "Each capture is analyzed for defects."
    )

    # Session state for camera
    if "camera_results" not in st.session_state:
        st.session_state.camera_results = []
    if "camera_mode" not in st.session_state:
        st.session_state.camera_mode = "photo"
    if "recording_active" not in st.session_state:
        st.session_state.recording_active = False
    if "recording_stop_flag" not in st.session_state:
        st.session_state.recording_stop_flag = [False]
    if "recording_thread" not in st.session_state:
        st.session_state.recording_thread = None
    if "recorded_video_path" not in st.session_state:
        st.session_state.recorded_video_path = None
    if "recorded_video_analyzed" not in st.session_state:
        st.session_state.recorded_video_analyzed = False

    camera_mode = st.radio(
        "Mode",
        options=["photo", "video_recording"],
        format_func=lambda x: "Photo" if x == "photo" else "Video recording",
        horizontal=True,
        key="camera_mode_radio",
    )
    st.session_state.camera_mode = camera_mode

    # ── Photo mode (existing flow) ──────────────────────────────
    if camera_mode == "photo":
        room_name = st.text_input("Room name (optional)", placeholder="e.g. Kitchen, Bedroom 1, Bathroom")
        camera_photo = st.camera_input("Take a photo")

        if camera_photo is not None:
            pil_img = Image.open(camera_photo)
            try:
                with st.spinner("Analyzing image..."):
                    analysis = analyze_image(pil_img, GEMINI_MODEL)

                if analysis.get("error"):
                    st.error(f"API error: {analysis['summary']}")
                else:
                    fs = score_frame(analysis)
                    ann = annotate_image(pil_img, analysis)

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
                    st.warning("Rate limit hit. Wait 1-2 minutes and try again.")

    # ── Video recording mode ────────────────────────────────────
    else:
        if not st.session_state.recording_active and st.session_state.recorded_video_path is None:
            if st.button("Start recording", type="primary"):
                st.session_state.recording_stop_flag[0] = False
                fd, path = tempfile.mkstemp(suffix=".avi")
                os.close(fd)
                st.session_state.recorded_video_path = path
                t = threading.Thread(
                    target=_record_webcam_to_file,
                    args=(st.session_state.recording_stop_flag, path),
                )
                t.daemon = True
                t.start()
                st.session_state.recording_thread = t
                st.session_state.recording_active = True
                st.session_state.recorded_video_analyzed = False
                st.rerun()

        elif st.session_state.recording_active:
            st.warning("Recording in progress. Move the camera to cover the area, then click **Stop recording**.")
            if st.button("Stop recording"):
                st.session_state.recording_stop_flag[0] = True
                if st.session_state.recording_thread is not None:
                    st.session_state.recording_thread.join(timeout=3.0)
                time.sleep(0.5)  # allow OS to release file handle before we open it
                st.session_state.recording_active = False
                st.session_state.recording_thread = None
                st.rerun()

        # Have a recorded file: offer to run inspection or discard
        if not st.session_state.recording_active and st.session_state.recorded_video_path is not None:
            rec_path = st.session_state.recorded_video_path
            if Path(rec_path).exists():
                st.success("Recording saved. Run inspection to analyze it, or clear to record again.")
                col_run, col_clear = st.columns(2)
                with col_run:
                    if st.button("Run inspection on recording", type="primary") and not st.session_state.recorded_video_analyzed:
                        try:
                            info = get_video_info_from_path(rec_path)
                            st.info(f"Recorded: {info['width']}x{info['height']} | {info['duration_sec']:.1f}s")
                            frame_tuples = extract_frames(rec_path, frame_interval, max_frames)
                            frames = [ft[0] for ft in frame_tuples]
                            timestamps = [ft[2] for ft in frame_tuples]

                            st.info(f"Analyzing {len(frames)} frames from recording...")
                            progress = st.progress(0, text="Analyzing frame 1...")
                            analyses = []
                            live_container = st.container()

                            for i, frame in enumerate(frames):
                                progress.progress((i + 1) / len(frames), text=f"Analyzing frame {i + 1}/{len(frames)}...")
                                analysis = analyze_image(frame, GEMINI_MODEL)
                                analyses.append(analysis)
                                with live_container:
                                    ann = annotate_image(frame, analysis)
                                    n_defs = len(analysis.get("defects", []))
                                    fs = score_frame(analysis)
                                    row1, row2 = st.columns([1, 1])
                                    with row1:
                                        st.image(ann, caption=f"Frame {i + 1} · {n_defs} defects · Risk {fs['score']}/100", use_container_width=True)
                                    with row2:
                                        st.caption(f"**{analysis.get('room_condition', 'unknown').upper()}**")
                                        st.write((analysis.get("summary") or "")[:280] + ("…" if len(analysis.get("summary") or "") > 280 else ""))
                                    st.divider()

                            progress.empty()
                            prop_score = score_property(analyses)
                            full_report = generate_property_report(analyses, GEMINI_MODEL)

                            st.session_state["analyses"] = analyses
                            st.session_state["frames"] = frames
                            st.session_state["timestamps"] = timestamps
                            st.session_state["property_score"] = prop_score
                            st.session_state["full_report_text"] = full_report
                            st.session_state["mode"] = "video"
                            st.session_state.recorded_video_analyzed = True

                            _render_risk_badge(prop_score["overall_score"], prop_score["risk_level"])
                            st.subheader("Step 2 — Full property report")
                            st.markdown(full_report)
                            try:
                                pdf_bytes = generate_pdf(
                                    frames=frames,
                                    analyses=analyses,
                                    property_score=prop_score,
                                    full_report_text=full_report,
                                    timestamps=timestamps,
                                )
                                st.download_button(
                                    label="Download PDF Report",
                                    data=pdf_bytes,
                                    file_name=f"property_inspection_report_{prop_score['overall_score']:.0f}.pdf",
                                    mime="application/pdf",
                                    type="primary",
                                    key="pdf_download_camera_recording",
                                )
                            except Exception as e:
                                st.warning(f"PDF could not be generated: {e}")
                        except Exception as e:
                            st.error(f"Error: {str(e)}")
                            if "429" in str(e) or "quota" in str(e).lower():
                                st.warning("Rate limit hit. Wait 1-2 minutes and try again.")
                with col_clear:
                    if st.button("Clear recording"):
                        try:
                            Path(rec_path).unlink(missing_ok=True)
                        except Exception:
                            pass
                        st.session_state.recorded_video_path = None
                        st.session_state.recorded_video_analyzed = False
                        st.rerun()

                if st.session_state.recorded_video_analyzed and "property_score" in st.session_state:
                    st.divider()
                    _render_risk_badge(
                        st.session_state["property_score"]["overall_score"],
                        st.session_state["property_score"]["risk_level"],
                    )
                    st.markdown(st.session_state.get("full_report_text", ""))
                    try:
                        pdf_bytes = generate_pdf(
                            frames=st.session_state.get("frames", []),
                            analyses=st.session_state.get("analyses", []),
                            property_score=st.session_state["property_score"],
                            full_report_text=st.session_state.get("full_report_text", ""),
                            timestamps=st.session_state.get("timestamps", []),
                        )
                        st.download_button(
                            label="Download PDF Report",
                            data=pdf_bytes,
                            file_name=f"property_inspection_report_{st.session_state['property_score']['overall_score']:.0f}.pdf",
                            mime="application/pdf",
                            type="primary",
                            key="pdf_download_camera_recording_2",
                        )
                    except Exception:
                        pass

    # ── Shared: inspection history (photo captures) ──────────────
    if st.session_state.camera_results:
        st.divider()
        st.subheader("Inspection History")

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

        if st.button("Clear all captures"):
            st.session_state.camera_results = []
            st.rerun()


# ── TAB 3: Report ─────────────────────────────────────────────
with tab_report:
    st.subheader("Inspection Report")

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

        # PDF download
        timestamps = st.session_state.get("timestamps", [0.0] * len(frames))
        full_report = st.session_state.get("full_report_text", "")
        try:
            pdf_bytes = generate_pdf(
                frames=frames,
                analyses=analyses,
                property_score=prop,
                full_report_text=full_report,
                timestamps=timestamps,
            )
            st.download_button(
                                label="Download PDF Report",
                data=pdf_bytes,
                file_name=f"property_inspection_report_{prop['overall_score']:.0f}.pdf",
                mime="application/pdf",
                type="primary",
                key="pdf_download_report",
            )
        except Exception as e:
            st.warning(f"PDF could not be generated: {e}")

        # Full property report (from Step 2, when run from video)
        if st.session_state.get("full_report_text"):
            st.subheader("Full Property Report")
            st.markdown(st.session_state["full_report_text"])

        # Priority actions
        if prop.get("priority_actions"):
            st.subheader("Priority Actions")
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
