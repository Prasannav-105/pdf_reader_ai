"""
quiz_view.py & revision_view.py: Chapter Assessment and Revision Flashcards.
"""
import streamlit as st
from typing import Dict, Any, List
from notes import StudyManager

def render_chapter_quiz_view(
    book_id: str,
    chapter_title: str,
    study_mgr: StudyManager,
    user_id: str
):
    """Renders comprehensive Chapter Quiz mode."""
    st.markdown(f"## 🎯 Chapter Assessment: *{chapter_title}*")
    st.caption("Test your mastery over all sections covered in this chapter.")

    scores = study_mgr.get_quiz_scores(user_id, book_id)
    if scores:
        st.markdown("##### Previous Quiz Attempts:")
        for s in scores[:5]:
            st.write(f"- **{s['chapter']} / {s['section']}**: Score {s['score']}% on {s['taken_at'][:16]}")

    st.info("💡 To take verification questions for each section, use **📖 Teaching Mode** and complete the interactive test at the bottom of each lesson.")

def render_revision_view(
    book_id: str,
    book_title: str,
    study_mgr: StudyManager,
    user_id: str
):
    """Renders Revision Mode with Saved Notes, Highlights, and Key Takeaways."""
    st.markdown(f"## 📝 Revision Dashboard: *{book_title}*")
    st.caption("Quickly review your highlighted passages, personal notes, and bookmarks.")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 🖍️ Key Highlights")
        highlights = study_mgr.get_highlights(user_id, book_id)
        if highlights:
            for h in highlights:
                hl_t = h['highlight_text']
                hl_c = h['chapter']
                hl_p = h['page_number']
                st.markdown(f"> *'{hl_t}'*\\n> — **{hl_c}** (Page {hl_p})")
        else:
            st.info("No highlights saved yet. Highlight important text while in Teaching Mode!")

    with col2:
        st.markdown("### 📝 Chapter Notes")
        notes = study_mgr.get_notes(user_id, book_id)
        if notes:
            for n in notes:
                with st.expander(f"📌 {n['chapter']} (p. {n['page_number']})"):
                    st.write(n['note_text'])
        else:
            st.info("No notes added yet.")
