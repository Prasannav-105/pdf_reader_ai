"""
notes_panel.py: Right Study Panel UI.
Displays Reading Progress, Bookmarks, Highlights, and Section Notes.
"""
import streamlit as st
from typing import Dict, Any, List
from notes import StudyManager

def render_notes_panel(
    study_mgr: StudyManager,
    user_id: str,
    book_id: str,
    current_chapter: str,
    current_section: str,
    current_page: int,
    total_sections: int = 1
):
    """Renders study dashboard with Progress, Notes, Highlights, and Bookmarks."""
    st.markdown("### 📊 Study & Notes")

    # 1. Progress Overview
    pos = study_mgr.get_reading_position(user_id, book_id)
    completed = pos.get("completed_sections", []) if pos else []
    pct = min(len(completed) / max(total_sections, 1), 1.0)

    st.markdown(f"**Reading Progress:** {int(pct * 100)}%")
    st.progress(pct)
    st.caption(f"Completed {len(completed)} of {total_sections} sections")

    # Section Completed Toggle
    section_key = f"{current_chapter}::{current_section}"
    is_done = section_key in completed
    if st.checkbox("✅ Mark this section as Completed", value=is_done, key=f"chk_done_{section_key}"):
        if not is_done:
            study_mgr.mark_section_completed(user_id, book_id, section_key)
            st.rerun()

    st.divider()

    tabs = st.tabs(["📝 Notes", "🔖 Bookmarks", "🖍️ Highlights"])

    # TAB 1: Notes
    with tabs[0]:
        st.caption(f"Notes for: *{current_section}*")
        note_text = st.text_area("Add note:", key="input_new_note", height=80, placeholder="Write key concepts, exam reminders...")
        if st.button("💾 Save Note", key="btn_save_note", use_container_width=True):
            if note_text.strip():
                study_mgr.add_note(user_id, book_id, current_chapter, current_section, current_page, note_text.strip())
                st.success("Note saved!")
                st.rerun()

        # Display Existing Notes
        notes = study_mgr.get_notes(user_id, book_id, current_chapter)
        if notes:
            st.markdown("##### Saved Chapter Notes:")
            for n in notes:
                with st.expander(f"📝 {n['created_at'][:16]} (p. {n['page_number']})"):
                    st.write(n["note_text"])
                    if st.button("🗑️ Delete", key=f"del_note_{n['id']}"):
                        study_mgr.delete_note(n["id"])
                        st.rerun()
        else:
            st.info("No notes saved for this chapter yet.")

    # TAB 2: Bookmarks
    with tabs[1]:
        bm_title = st.text_input("Bookmark Title:", value=current_section[:30], key="input_bm_title")
        if st.button("📌 Bookmark This Section", key="btn_save_bm", use_container_width=True):
            study_mgr.add_bookmark(user_id, book_id, current_chapter, current_section, current_page, bm_title.strip())
            st.success("Bookmarked!")
            st.rerun()

        bookmarks = study_mgr.get_bookmarks(user_id, book_id)
        if bookmarks:
            st.markdown("##### Your Bookmarks:")
            for b in bookmarks:
                col_bm1, col_bm2 = st.columns([4, 1])
                with col_bm1:
                    st.markdown(f"**{b['title']}** (p. {b['page_number']})")
                    st.caption(b['chapter'])
                with col_bm2:
                    if st.button("✕", key=f"del_bm_{b['id']}"):
                        study_mgr.delete_bookmark(b['id'])
                        st.rerun()
        else:
            st.caption("No bookmarks yet.")

    # TAB 3: Highlights
    with tabs[2]:
        hl_text = st.text_area("Snippet to highlight:", key="input_new_hl", height=70, placeholder="Paste important excerpt...")
        hl_color = st.selectbox("Highlight color:", ["yellow", "green", "blue", "pink"], key="sel_hl_color")
        if st.button("🖍️ Save Highlight", key="btn_save_hl", use_container_width=True):
            if hl_text.strip():
                study_mgr.add_highlight(user_id, book_id, current_chapter, current_section, current_page, hl_text.strip(), hl_color)
                st.success("Highlight saved!")
                st.rerun()

        highlights = study_mgr.get_highlights(user_id, book_id)
        if highlights:
            for h in highlights:
                hl_t = h['highlight_text']
                hl_p = h['page_number']
                st.markdown(f"> *'{hl_t}'* — (p. {hl_p})")
                if st.button("🗑️", key=f"del_hl_{h['id']}"):
                    study_mgr.delete_highlight(h['id'])
                    st.rerun()
