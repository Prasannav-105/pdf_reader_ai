"""
pdf_viewer.py: High-Resolution PDF Visualizer, Annotator & Highlighter.
Powered by PyMuPDF (pymupdf).
Allows students to view actual textbook pages, search & highlight text in colors,
add sticky notes, and export/save the annotated PDF file.
"""
import os
import io
import pymupdf
import streamlit as st
from typing import Dict, Any, Optional
from notes import StudyManager

COLOR_RGB = {
    "yellow": (1.0, 0.88, 0.1),
    "green": (0.2, 0.88, 0.3),
    "blue": (0.2, 0.72, 1.0),
    "pink": (1.0, 0.35, 0.75),
}

def resolve_pdf_path(book: Dict[str, Any]) -> Optional[str]:
    """Finds the actual PDF file on disk."""
    path = book.get("file_path", "")
    if path and os.path.exists(path):
        return path
    
    # Check uploads directory
    uploads_dir = "./data/uploads"
    title = book.get("title", "")
    candidate = os.path.join(uploads_dir, f"{title}.pdf")
    if os.path.exists(candidate):
        return candidate
    
    # Check user Downloads
    home = os.path.expanduser("~")
    dl_candidate = os.path.join(home, "Downloads", f"{title}.pdf")
    if os.path.exists(dl_candidate):
        return dl_candidate
        
    return None

def render_pdf_viewer(
    book: Dict[str, Any],
    current_chapter: str,
    current_section: str,
    current_page: int,
    study_mgr: StudyManager,
    user_id: str
):
    """
    Renders interactive PDF viewer canvas with:
    - High-resolution page visualization
    - Prev / Next / Jump page controls & Zoom
    - Text highlighting with color selection (Yellow, Green, Blue, Pink)
    - Margin note annotations
    - Save & Download annotated PDF
    """
    pdf_path = resolve_pdf_path(book)
    if not pdf_path:
        st.warning(f"⚠️ Original PDF for '{book.get('title')}' was not found on disk. Please upload it via the sidebar.")
        return

    book_id = book.get("id", "book")
    annotated_pdf_path = os.path.join("./data/uploads", f"annotated_{book_id}.pdf")
    active_path = annotated_pdf_path if os.path.exists(annotated_pdf_path) else pdf_path

    try:
        doc = pymupdf.open(active_path)
    except Exception as e:
        st.error(f"Error opening PDF: {e}")
        return

    total_pages = len(doc)
    if total_pages == 0:
        st.error("PDF contains 0 pages.")
        return

    # Session state for active viewing page
    page_state_key = f"pdf_viewer_page_{book_id}"
    if page_state_key not in st.session_state:
        st.session_state[page_state_key] = max(1, min(current_page, total_pages))

    view_page = st.session_state[page_state_key]

    # --- Top Viewer Toolbar ---
    st.markdown("#### 📄 Interactive PDF Reader & Annotator")
    
    tb_col1, tb_col2, tb_col3, tb_col4, tb_col5 = st.columns([1.5, 1.5, 3, 2, 2])
    with tb_col1:
        if st.button("◀️ Prev", use_container_width=True, disabled=(view_page <= 1)):
            st.session_state[page_state_key] = max(1, view_page - 1)
            st.rerun()
    with tb_col2:
        if st.button("Next ▶️", use_container_width=True, disabled=(view_page >= total_pages)):
            st.session_state[page_state_key] = min(total_pages, view_page + 1)
            st.rerun()
    with tb_col3:
        target_p = st.number_input(
            f"Page (1 - {total_pages}):",
            min_value=1,
            max_value=total_pages,
            value=view_page,
            key=f"num_page_{book_id}"
        )
        if target_p != view_page:
            st.session_state[page_state_key] = target_p
            st.rerun()
    with tb_col4:
        zoom_choice = st.selectbox("Zoom:", ["100% (Crisp)", "130% (Large)", "160% (HD)"], index=0, key=f"zoom_{book_id}")
        dpi_map = {"100% (Crisp)": 115, "130% (Large)": 150, "160% (HD)": 185}
        active_dpi = dpi_map.get(zoom_choice, 115)
    with tb_col5:
        if current_page and current_page != view_page:
            if st.button(f"🎯 Chapter p.{current_page}", use_container_width=True, help="Jump to current chapter starting page"):
                st.session_state[page_state_key] = current_page
                st.rerun()

    # --- Annotation Controls Expander ---
    with st.expander("🖍️ **Highlight & Add Notes to this PDF Page**", expanded=False):
        c_an1, c_an2 = st.columns([1, 1])
        with c_an1:
            st.markdown("##### 🖍️ Text Highlighter")
            hl_input = st.text_input("Exact text to highlight on this page:", placeholder="e.g. system calls, virtual memory...", key=f"pdf_hl_{book_id}_{view_page}")
            hl_color_sel = st.selectbox(
                "Highlight Color:",
                ["🟡 Yellow", "🟢 Green", "🔵 Blue", "🌸 Pink"],
                key=f"pdf_hl_col_{book_id}"
            )
            raw_color = hl_color_sel.split()[-1].lower()

            if st.button("✨ Apply Highlight to Page", key=f"btn_apply_hl_{book_id}", use_container_width=True):
                if hl_input.strip():
                    search_term = hl_input.strip()
                    page = doc[view_page - 1]
                    rects = page.search_for(search_term)
                    if rects:
                        rgb = COLOR_RGB.get(raw_color, (1.0, 0.88, 0.1))
                        for r in rects:
                            annot = page.add_highlight_annot(r)
                            annot.set_colors(stroke=rgb)
                            annot.update()
                        
                        # Save modified document
                        doc.save(annotated_pdf_path, deflate=True)
                        doc.close()
                        
                        # Also register in study manager
                        study_mgr.add_highlight(user_id, book_id, current_chapter, current_section, view_page, search_term, raw_color)
                        st.success(f"Highlighted {len(rects)} occurrence(s) in {raw_color.capitalize()}!")
                        st.rerun()
                    else:
                        st.warning(f"Could not find exact text '{search_term}' on page {view_page}. Try checking spelling or capitalization.")

        with c_an2:
            st.markdown("##### 📝 Add Sticky Note")
            note_input = st.text_input("Sticky note comment:", placeholder="e.g. Important formula for midterm...", key=f"pdf_note_{book_id}_{view_page}")
            if st.button("📌 Insert Note on Page", key=f"btn_apply_note_{book_id}", use_container_width=True):
                if note_input.strip():
                    page = doc[view_page - 1]
                    point = pymupdf.Point(50, 50 + (view_page % 5) * 40)
                    annot = page.add_text_annot(point, note_input.strip())
                    annot.set_info(content=note_input.strip(), title=user_id)
                    annot.update()
                    
                    doc.save(annotated_pdf_path, deflate=True)
                    doc.close()
                    study_mgr.add_note(user_id, book_id, current_chapter, current_section, view_page, note_input.strip())
                    st.success("Sticky note added to PDF!")
                    st.rerun()

        # Save & Download Button
        st.divider()
        col_dl1, col_dl2 = st.columns([1, 1])
        with col_dl1:
            # Provide download of annotated PDF
            if os.path.exists(annotated_pdf_path):
                with open(annotated_pdf_path, "rb") as f_pdf:
                    pdf_bytes = f_pdf.read()
                st.download_button(
                    label="💾 Download Highlighted PDF",
                    data=pdf_bytes,
                    file_name=f"{book.get('title', 'Textbook')}_Annotated.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
            else:
                with open(pdf_path, "rb") as f_pdf:
                    pdf_bytes = f_pdf.read()
                st.download_button(
                    label="💾 Download Original PDF",
                    data=pdf_bytes,
                    file_name=f"{book.get('title', 'Textbook')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
        with col_dl2:
            if os.path.exists(annotated_pdf_path):
                if st.button("🗑️ Reset Annotations (Revert to Original)", key=f"btn_revert_{book_id}", use_container_width=True):
                    try:
                        doc.close()
                        os.remove(annotated_pdf_path)
                        st.info("Reverted to clean original PDF.")
                        st.rerun()
                    except Exception as ex:
                        st.error(f"Error resetting annotations: {ex}")

    # --- Render High-Resolution Page Canvas ---
    try:
        page = doc[view_page - 1]
        pix = page.get_pixmap(dpi=active_dpi)
        img_bytes = pix.tobytes("png")
        
        st.markdown(f"""
        <div style="background: #0B1120; border: 1px solid #1E293B; border-radius: 10px; padding: 12px; text-align: center; margin-top: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.5);">
            <div style="font-size: 0.8rem; color: #94A3B8; margin-bottom: 8px;">Page {view_page} of {total_pages} &bull; {book.get('title')}</div>
        </div>
        """, unsafe_allow_html=True)
        st.image(img_bytes, use_container_width=True)
    except Exception as ex:
        st.error(f"Error rendering page: {ex}")
    finally:
        if not doc.is_closed:
            doc.close()
