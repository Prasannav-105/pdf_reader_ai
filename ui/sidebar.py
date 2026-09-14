"""
sidebar.py: Left Navigation Sidebar.
Manages PDF Imports, Hierarchical Book Navigator, Study Modes, and Continue Reading.
"""
import os
import streamlit as st
from typing import Dict, Any, List, Optional
from models.schema import BookHierarchy, HierarchicalNode
from notes import StudyManager
from hardware import get_hardware_info, get_hardware_options

def render_sidebar(
    books: List[Dict[str, Any]],
    active_book_id: Optional[str],
    hierarchy: Optional[BookHierarchy],
    study_mgr: StudyManager,
    user_id: str,
    user: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Renders left sidebar with:
    - User Profile & Logout
    - Google Colab-style Compute Hardware Accelerator Selector (CPU / GPU)
    - Book Selector & PDF Upload
    - Mode Selection (Teaching / Revision / Quiz / Search)
    - Continue Reading quick jump
    - Hierarchical Navigator (Unit -> Chapter -> Section)
    """
    st.sidebar.markdown("## 📚 AI Textbook Reader")

    # 0. User Profile Badge & Logout
    if user:
        u_col1, u_col2 = st.sidebar.columns([3, 1])
        with u_col1:
            st.sidebar.markdown(f"<div class='user-profile-badge'>👤 <b>{user.get('username', user_id)}</b></div>", unsafe_allow_html=True)
        with u_col2:
            if st.sidebar.button("🚪 Logout", key="sb_logout_btn", help="Log out of account"):
                st.session_state["user"] = None
                st.session_state["user_id"] = "guest"
                st.rerun()

    # 1. Hardware Accelerator Selector (Colab Style)
    hw_options = get_hardware_options()
    name_map = {opt["name"]: opt.get("num_gpu", 0) for opt in hw_options}
    opt_labels = list(name_map.keys())

    selected_hw = st.sidebar.selectbox(
        "⚡ Compute Accelerator:",
        options=opt_labels,
        index=0,
        help="Switch between System CPU and GPU inference just like Google Colab",
        key="sel_compute_hw"
    )
    num_gpu = name_map.get(selected_hw, 0)
    badge_label = "CPU Mode" if num_gpu == 0 else "GPU Accelerated"
    st.sidebar.markdown(f"<span class='hardware-badge'>⚡ {badge_label}</span>", unsafe_allow_html=True)
    st.sidebar.markdown("---")

    # 1. Book Selector
    book_options = {b["id"]: b["title"] for b in books}
    if not book_options:
        st.sidebar.info("Upload a textbook below to begin.")
        selected_book_id = None
    else:
        book_ids = list(book_options.keys())
        default_idx = book_ids.index(active_book_id) if active_book_id in book_ids else 0
        selected_book_id = st.sidebar.selectbox(
            "📖 Active Textbook:",
            options=book_ids,
            index=default_idx,
            format_func=lambda x: book_options.get(x, x),
            key="sel_active_book"
        )

    # 2. PDF Upload (Single or Multiple)
    with st.sidebar.expander("➕ Import New Textbook(s)", expanded=not bool(books)):
        uploaded_files = st.file_uploader(
            "Upload PDF Book(s)",
            type=["pdf"],
            accept_multiple_files=True,
            key="pdf_uploader"
        )

    # 3. Study Mode Selection
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🎯 Learning Mode")
    study_mode = st.sidebar.radio(
        "Select Mode:",
        ["📖 Teaching Mode", "📄 PDF Reader & Annotator", "📝 Revision Mode", "🎯 Chapter Quiz", "🔍 Search by Topic"],
        key="radio_study_mode"
    )

    # 4. Continue Reading Button
    if selected_book_id:
        pos = study_mgr.get_reading_position(user_id, selected_book_id)
        if pos and pos.get("last_chapter"):
            st.sidebar.markdown("---")
            if st.sidebar.button(f"⏩ Continue Reading\n*{pos['last_chapter'][:24]}*", use_container_width=True):
                st.session_state["nav_chapter"] = pos["last_chapter"]
                st.session_state["nav_section"] = pos["last_section"]
                st.rerun()

    # 5. Hierarchical Tree Navigator
    selected_chapter = None
    selected_section = None
    selected_node = None

    if hierarchy and hierarchy.root_nodes:
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 📑 Chapter Navigator")

        # Flat list of chapters for robust navigation
        chapters = [n.title for n in hierarchy.root_nodes]
        default_chap_idx = 0
        if "nav_chapter" in st.session_state and st.session_state["nav_chapter"] in chapters:
            default_chap_idx = chapters.index(st.session_state["nav_chapter"])

        selected_chapter = st.sidebar.selectbox(
            "Chapter / Topic:",
            options=chapters,
            index=default_chap_idx,
            key="sb_chapter_select"
        )
        st.session_state["nav_chapter"] = selected_chapter

        # Find active node
        for n in hierarchy.root_nodes:
            if n.title == selected_chapter:
                selected_node = n
                break

        # Sections under selected chapter
        if selected_node and selected_node.children:
            sec_titles = [c.title for c in selected_node.children]
            default_sec_idx = 0
            if "nav_section" in st.session_state and st.session_state["nav_section"] in sec_titles:
                default_sec_idx = sec_titles.index(st.session_state["nav_section"])

            selected_section = st.sidebar.selectbox(
                "Section:",
                options=sec_titles,
                index=default_sec_idx,
                key="sb_section_select"
            )
            st.session_state["nav_section"] = selected_section
        else:
            selected_section = selected_chapter
            st.session_state["nav_section"] = selected_section

    # Status footer
    st.sidebar.markdown("---")
    st.sidebar.caption("⚡ Offline Ollama • nomic-embed-text • ChromaDB")

    return {
        "selected_book_id": selected_book_id,
        "uploaded_files": uploaded_files,
        "study_mode": study_mode,
        "chapter": selected_chapter,
        "section": selected_section,
        "active_node": selected_node,
        "num_gpu": num_gpu,
        "compute_device": selected_hw
    }
