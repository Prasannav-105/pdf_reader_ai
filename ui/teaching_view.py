"""
teaching_view.py: Center Teaching Content Canvas.
Displays Section Masterclass, Auto-Healing Mermaid Diagrams with Zoom/Pan,
Key Points, 3 MCQs, and 2 Short-Answer Questions.
"""
import re
import streamlit as st
import streamlit.components.v1 as components
from typing import Dict, Any, List, Optional
from teacher import TeacherEngine
from quiz_generator import QuizEngine
from notes import StudyManager
from ui.tts_player import render_tts_player

def render_mermaid_viewer(mermaid_code: str, element_id: str = "mermaid_chart"):
    """Renders interactive Mermaid diagram with Zoom In (+), Zoom Out (-), and Reset (⟲)."""
    clean_code = TeacherEngine.sanitize_mermaid(mermaid_code)
    
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"></script>
        <style>
            body {{
                margin: 0;
                padding: 10px;
                background-color: #0B1120;
                color: #F8FAFC;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                overflow: hidden;
            }}
            .toolbar {{
                display: flex;
                gap: 8px;
                margin-bottom: 8px;
                background: #1E293B;
                padding: 6px 12px;
                border-radius: 6px;
                border: 1px solid #334155;
            }}
            .btn {{
                background: #334155;
                color: #F8FAFC;
                border: 1px solid #475569;
                border-radius: 4px;
                padding: 4px 10px;
                cursor: pointer;
                font-weight: 600;
                font-size: 12px;
            }}
            .btn:hover {{
                background: #4F46E5;
                border-color: #6366F1;
            }}
            #viewport {{
                width: 100%;
                height: 380px;
                overflow: auto;
                background: #0F172A;
                border-radius: 8px;
                border: 1px solid #1E293B;
                display: flex;
                align-items: center;
                justify-content: center;
            }}
            #chart-container {{
                transform-origin: center center;
                transition: transform 0.15s ease-out;
            }}
        </style>
    </head>
    <body>
        <div class="toolbar">
            <span style="font-size: 12px; font-weight: 600; margin-right: auto; color: #94A3B8;">📐 Architectural Flow</span>
            <button class="btn" onclick="zoom(0.15)">➕ Zoom In</button>
            <button class="btn" onclick="zoom(-0.15)">➖ Zoom Out</button>
            <button class="btn" onclick="resetZoom()">⟲ Reset</button>
        </div>
        <div id="viewport">
            <div id="chart-container">
                <pre class="mermaid">
{clean_code}
                </pre>
            </div>
        </div>
        <script>
            mermaid.initialize({{
                startOnLoad: true,
                theme: 'dark',
                securityLevel: 'loose',
                themeVariables: {{
                    darkMode: true,
                    background: '#0F172A',
                    primaryColor: '#312E81',
                    primaryTextColor: '#F8FAFC',
                    primaryBorderColor: '#6366F1',
                    lineColor: '#38BDF8',
                    secondaryColor: '#1E293B',
                    tertiaryColor: '#0F172A'
                }}
            }});

            let currentScale = 1.0;
            function zoom(delta) {{
                currentScale = Math.max(0.4, Math.min(3.0, currentScale + delta));
                document.getElementById('chart-container').style.transform = `scale(${{currentScale}})`;
            }}
            function resetZoom() {{
                currentScale = 1.0;
                document.getElementById('chart-container').style.transform = 'scale(1.0)';
            }}
        </script>
    </body>
    </html>
    """
    components.html(html_code, height=440, scrolling=False)

def render_teaching_view(
    teacher: TeacherEngine,
    quiz_engine: QuizEngine,
    study_mgr: StudyManager,
    user_id: str,
    book_id: str,
    book_title: str,
    chapter_title: str,
    section_title: str,
    context_chunks: List[Dict[str, Any]],
    num_gpu: int = 0
):
    """Renders full pedagogical section lesson with Q&A verification and offline audio narration."""
    # 1. Breadcrumb bar
    start_p = context_chunks[0]["metadata"].get("start_page", 1) if context_chunks else 1
    end_p = context_chunks[-1]["metadata"].get("end_page", start_p) if context_chunks else start_p

    # Save reading position
    study_mgr.save_reading_position(user_id, book_id, chapter_title, section_title, start_p)

    lesson_cache_key = f"lesson_{book_id}_{chapter_title}_{section_title}"

    # If lesson has not been analyzed yet, show the Launchpad card and require user click to start
    if lesson_cache_key not in st.session_state:
        st.markdown(f"""
        <div class='dark-card' style='text-align: center; padding: 36px 24px; border: 1px solid #28354A; margin-top: 10px;'>
            <div style='font-size: 2.2rem; margin-bottom: 8px;'>📖</div>
            <h2 style='margin-bottom: 8px; color: #F8FAFC;'>{section_title}</h2>
            <div style='display: flex; justify-content: center; align-items: center; gap: 10px; margin-bottom: 16px; color: #94A3B8; font-size: 0.9rem;'>
                <span>📚 <b>{book_title}</b></span>
                <span>•</span>
                <span>📑 <b>{chapter_title}</b></span>
                <span>•</span>
                <span class='badge-page'>Pages {start_p}–{end_p}</span>
            </div>
            <p style='color: #CBD5E1; max-width: 580px; margin: 0 auto 24px auto; font-size: 0.95rem; line-height: 1.5;'>
                This section is selected and ready. Click the button below to extract textbook concepts, generate architectural flowcharts, source code mechanics, and mastery verification questions.
            </p>
        </div>
        """, unsafe_allow_html=True)

        col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
        with col_btn2:
            if st.button("🚀 Start Analyzing Section", type="primary", use_container_width=True, key=f"btn_start_{lesson_cache_key}"):
                with st.spinner(f"Analyzing '{section_title}' strictly from textbook pages {start_p}–{end_p}..."):
                    lesson_text = ""
                    for delta in teacher.teach_section_stream(book_title, chapter_title, section_title, context_chunks, num_gpu=num_gpu):
                        lesson_text += delta
                    st.session_state[lesson_cache_key] = lesson_text
                    st.rerun()
        return

    # If lesson is already analyzed, show toolbar with Regenerate option
    col_bc, col_regen = st.columns([8, 2])
    with col_bc:
        st.markdown(f"""
        <div class="breadcrumb-bar">
            <span>📖 <b>{book_title}</b></span> &gt;
            <span>📑 {chapter_title}</span> &gt;
            <span style="color: #F8FAFC; font-weight: 600;">{section_title}</span>
            <span class="badge-page" style="margin-left: auto;">Pages {start_p}–{end_p}</span>
        </div>
        """, unsafe_allow_html=True)
    with col_regen:
        if st.button("🔄 Regenerate", help="Re-generate lesson using current hardware & prompt rules", use_container_width=True):
            if lesson_cache_key in st.session_state:
                del st.session_state[lesson_cache_key]
            st.rerun()

    lesson_content = st.session_state.get(lesson_cache_key, "")

    # Extract Mermaid diagram if present
    mermaid_match = re.search(r'```mermaid\s*(.*?)```', lesson_content, re.DOTALL)
    diagram_code = mermaid_match.group(1).strip() if mermaid_match else ""
    text_without_mermaid = re.sub(r'```mermaid\s*.*?```', '', lesson_content, flags=re.DOTALL)

    # Render Offline Text-to-Speech Audio Player
    render_tts_player(text_without_mermaid, label=f"Audio: {section_title[:30]}")

    # Apply saved user highlights with color markers to chapter content
    rendered_text = text_without_mermaid
    try:
        user_highlights = study_mgr.get_highlights(user_id, book_id)
        hl_colors = {
            "yellow": "rgba(250, 204, 21, 0.4)",
            "green": "rgba(74, 222, 128, 0.4)",
            "blue": "rgba(56, 189, 248, 0.4)",
            "pink": "rgba(244, 114, 182, 0.4)"
        }
        for hl in user_highlights:
            hl_t = hl.get("highlight_text", "").strip()
            if hl_t and len(hl_t) > 2 and hl_t in rendered_text:
                c_name = (hl.get("color") or "yellow").lower()
                c_val = hl_colors.get(c_name, hl_colors["yellow"])
                mark_html = f"<mark style='background-color: {c_val}; color: #FFFFFF; padding: 2px 5px; border-radius: 4px; font-weight: 600;'>{hl_t}</mark>"
                rendered_text = rendered_text.replace(hl_t, mark_html)
    except Exception:
        pass

    # Render Main Teaching Content
    st.markdown(f"<div class='dark-card'>", unsafe_allow_html=True)
    st.markdown(rendered_text, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # Render Mermaid Diagram with Zoom/Pan
    if diagram_code:
        st.markdown("#### 📐 Architectural & Process Flow")
        render_mermaid_viewer(diagram_code)

    # Render End-of-Section Verification Questions (3 MCQs + 2 Short Questions)
    st.divider()
    st.markdown("### 🎯 End-of-Section Mastery Verification")

    mcqs, short_qs = quiz_engine.parse_quiz_from_lesson(lesson_content)

    # Render MCQs
    if mcqs:
        st.markdown("#### 🔘 Multiple Choice Questions (3 MCQs)")
        for i, q in enumerate(mcqs[:3]):
            st.markdown(f"**Q{i+1}: {q.question}**")
            user_choice = st.radio(
                f"Select answer for Q{i+1}:",
                options=q.options,
                key=f"mcq_{lesson_cache_key}_{i}",
                index=None
            )
            if user_choice:
                selected_letter = user_choice[0].upper()
                if selected_letter == q.correct_option:
                    st.success(f"✅ **Correct!** {q.explanation}")
                else:
                    st.error(f"❌ **Incorrect.** Correct answer is **{q.correct_option}**. {q.explanation}")

    # Render Short Questions
    if short_qs:
        st.markdown("#### ✍️ Conceptual Short-Answer Questions")
        raw_textbook_ctx = " ".join([c.get("text", "") for c in context_chunks])
        for j, sq in enumerate(short_qs[:2]):
            st.markdown(f"**Q{j+1}: {sq.question}**")
            ans_input = st.text_area("Your explanation:", key=f"sq_ans_{lesson_cache_key}_{j}", height=70)
            if st.button(f"Submit Answer for Q{j+1}", key=f"btn_sq_{lesson_cache_key}_{j}"):
                with st.spinner("Grading answer against textbook criteria..."):
                    result = quiz_engine.grade_short_answer(sq.question, ans_input, raw_textbook_ctx)
                    score = result.get("score", 70)
                    if score >= 80:
                        st.success(f"🌟 **{result.get('verdict', 'Mastered')} ({score}/100)**: {result.get('feedback', '')}")
                    else:
                        st.warning(f"📝 **{result.get('verdict', 'Review Needed')} ({score}/100)**: {result.get('feedback', '')}")
                    if result.get("textbook_quote"):
                        q_ref = result['textbook_quote']
                        st.caption(f"📖 *Textbook reference:* '{q_ref}'")
