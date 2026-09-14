"""
app.py: Main Entry Point for AI Textbook Reader & Desktop Tutor.
Modular, offline architecture using Ollama, PyMuPDF, ChromaDB, and Streamlit.
"""
import os
import json
import re
import uuid
import streamlit as st

# Set page configuration
st.set_page_config(
    page_title="AI Textbook Reader & Tutor",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Core imports
from models.schema import SectionMetadata, TextbookChunk, BookHierarchy, HierarchicalNode
from pdf_processor import PDFProcessor
from chapter_parser import ChapterParser
from embeddings import OllamaEmbedder
from vectordb import VectorDBManager
from teacher import TeacherEngine
from quiz_generator import QuizEngine
from notes import StudyManager
from ui.styles import DARK_THEME_CSS
from ui.sidebar import render_sidebar
from ui.teaching_view import render_teaching_view
from ui.notes_panel import render_notes_panel
from ui.chat_drawer import render_chat_drawer
from ui.quiz_view import render_chapter_quiz_view, render_revision_view

# Apply dark theme styling
st.markdown(DARK_THEME_CSS, unsafe_allow_html=True)

# Data directories
DATA_DIR = "./data"
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
CHROMA_DIR = os.path.join(DATA_DIR, "chroma_db")
BOOKS_META_PATH = os.path.join(DATA_DIR, "books.json")
STUDY_DB_PATH = os.path.join(DATA_DIR, "study_data.db")

os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(CHROMA_DIR, exist_ok=True)

# Single-instance service caching
@st.cache_resource
def get_services():
    embedder = OllamaEmbedder(model_name="nomic-embed-text")
    vectordb = VectorDBManager(persist_dir=CHROMA_DIR)
    teacher = TeacherEngine(model_name="llama3.2")
    quiz_engine = QuizEngine(model_name="llama3.2")
    study_mgr = StudyManager(db_path=STUDY_DB_PATH)
    parser = ChapterParser(data_dir=DATA_DIR)
    return embedder, vectordb, teacher, quiz_engine, study_mgr, parser

embedder, vectordb, teacher, quiz_engine, study_mgr, parser = get_services()

# Session State Initialization
if "user_id" not in st.session_state:
    st.session_state["user_id"] = "student_user"

# Helper for book metadata
def load_books() -> list:
    if os.path.exists(BOOKS_META_PATH):
        try:
            with open(BOOKS_META_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_books(books: list):
    with open(BOOKS_META_PATH, "w", encoding="utf-8") as f:
        json.dump(books, f, indent=2)

books = load_books()

# Auto-migration of existing books from scratch tutor.db if books.json is empty
if not books:
    old_db_path = "C:/Users/SOC Test PC 2/.gemini/antigravity/scratch/os-ai-tutor/tutor.db"
    if os.path.exists(old_db_path):
        try:
            import sqlite3
            conn = sqlite3.connect(old_db_path)
            cur = conn.execute("SELECT id, title, total_pages FROM books")
            migrated = []
            for b_id, b_title, t_pages in cur.fetchall():
                if "Test" not in b_title and "User 1" not in b_title:
                    safe_id = f"book_{re.sub(r'[^a-zA-Z0-9_-]', '_', b_title)}"
                    # Check if chapters exist
                    ch_cur = conn.execute("SELECT chapter_title, subtopic_title, start_page, end_page, content FROM chapters WHERE book_id=? ORDER BY id ASC", (b_id,))
                    ch_rows = ch_cur.fetchall()
                    if ch_rows:
                        # Build BookHierarchy
                        root_nodes = []
                        chunks = []
                        seen_chaps = {}
                        for c_idx, (ch_title, sub_title, s_p, e_p, c_text) in enumerate(ch_rows):
                            sec_title = sub_title or ch_title
                            if ch_title not in seen_chaps:
                                chap_node = HierarchicalNode(
                                    node_id=f"{safe_id}_ch_{len(root_nodes)}",
                                    title=ch_title,
                                    level="chapter",
                                    start_page=s_p,
                                    end_page=e_p,
                                    children=[]
                                )
                                root_nodes.append(chap_node)
                                seen_chaps[ch_title] = chap_node

                            meta = SectionMetadata(
                                book_id=safe_id,
                                book_name=b_title,
                                unit="Textbook",
                                chapter=ch_title,
                                section=sec_title,
                                topic_title=sec_title,
                                start_page=s_p,
                                end_page=e_p,
                                chunk_index=c_idx + 1
                            )
                            chunk_id = f"{safe_id}_chunk_{c_idx+1:04d}"
                            chunks.append(TextbookChunk(
                                chunk_id=chunk_id,
                                metadata=meta,
                                original_text=c_text
                            ))

                        hierarchy = BookHierarchy(
                            book_id=safe_id,
                            book_name=b_title,
                            total_pages=t_pages or 100,
                            root_nodes=root_nodes,
                            total_sections=len(chunks)
                        )
                        # Cache tree and chunks
                        with open(os.path.join(DATA_DIR, f"{safe_id}_tree.json"), "w", encoding="utf-8") as f:
                            json.dump(hierarchy.to_dict(), f, indent=2)
                        with open(os.path.join(DATA_DIR, f"{safe_id}_chunks.json"), "w", encoding="utf-8") as f:
                            json.dump([c.to_dict() for c in chunks], f, indent=2)

                        migrated.append({
                            "id": safe_id,
                            "title": b_title,
                            "pages": t_pages,
                            "file_path": ""
                        })
            if migrated:
                save_books(migrated)
                books = migrated
        except Exception as ex:
            print(f"Migration note: {ex}")

# Check active book
active_book_id = st.session_state.get("active_book_id")
if not active_book_id and books:
    active_book_id = books[0]["id"]
    st.session_state["active_book_id"] = active_book_id

active_book = next((b for b in books if b["id"] == active_book_id), None) if active_book_id else None

# Load hierarchy for active book
hierarchy = None
active_chunks = []
if active_book:
    tree_path = os.path.join(DATA_DIR, f"{active_book['id']}_tree.json")
    chunks_path = os.path.join(DATA_DIR, f"{active_book['id']}_chunks.json")
    if os.path.exists(tree_path) and os.path.exists(chunks_path):
        try:
            with open(tree_path, "r", encoding="utf-8") as f:
                hierarchy = BookHierarchy.from_dict(json.load(f))
            with open(chunks_path, "r", encoding="utf-8") as f:
                c_data = json.load(f)
                for item in c_data:
                    active_chunks.append(TextbookChunk(
                        chunk_id=item["chunk_id"],
                        metadata=SectionMetadata.from_dict(item["metadata"]),
                        original_text=item["original_text"]
                    ))
        except Exception:
            pass

# Sidebar Rendering
sidebar_state = render_sidebar(
    books=books,
    active_book_id=active_book_id,
    hierarchy=hierarchy,
    study_mgr=study_mgr,
    user_id=st.session_state["user_id"]
)

# Handle Active Book Switch
if sidebar_state["selected_book_id"] and sidebar_state["selected_book_id"] != active_book_id:
    st.session_state["active_book_id"] = sidebar_state["selected_book_id"]
    st.rerun()

# Handle New PDF Uploads
if sidebar_state["uploaded_files"]:
    for up_file in sidebar_state["uploaded_files"]:
        save_path = os.path.join(UPLOADS_DIR, up_file.name)
        with open(save_path, "wb") as f:
            f.write(up_file.getbuffer())

        with st.status(f"Processing '{up_file.name}'...", expanded=True) as status:
            st.write("📖 Extracting headings, sections, and page tree...")
            b_hier, b_chunks = parser.parse_book(save_path, force_reparse=True)
            
            st.write(f"🔢 Generated {len(b_chunks)} semantic chunks. Indexing into ChromaDB...")
            vectordb.index_chunks(b_hier.book_id, b_chunks, embedder)

            # Register book
            new_book_entry = {
                "id": b_hier.book_id,
                "title": b_hier.book_name,
                "pages": b_hier.total_pages,
                "file_path": save_path
            }
            if not any(b["id"] == b_hier.book_id for b in books):
                books.append(new_book_entry)
                save_books(books)

            status.update(label=f"✅ '{up_file.name}' parsed and indexed successfully!", state="complete", expanded=False)

    st.session_state["active_book_id"] = books[-1]["id"]
    st.rerun()

# Ensure active book is indexed in ChromaDB (lazy index on first access)
if active_book and active_chunks:
    if not vectordb.is_book_indexed(active_book["id"]):
        with st.sidebar.status("⚡ Indexing textbook into ChromaDB...", expanded=True) as status:
            progress_bar = st.sidebar.progress(0.0)
            def on_prog(curr, total, msg):
                progress_bar.progress(curr / total)
            vectordb.index_chunks(active_book["id"], active_chunks, embedder, on_prog)
            status.update(label="✅ ChromaDB vector indexing complete!", state="complete")
            st.rerun()

# --- Main Application Area ---
if not active_book or not hierarchy:
    st.markdown("""
    <div class='dark-card' style='text-align: center; padding: 60px 20px;'>
        <h2>📚 Welcome to AI Textbook Reader</h2>
        <p style='color: #94A3B8; font-size: 1.1rem; max-width: 600px; margin: 0 auto 24px auto;'>
            A pure textbook teaching system powered by offline Ollama, nomic-embed-text, and ChromaDB.
            Upload any PDF textbook in the sidebar to start interactive, chapter-wise masterclasses.
        </p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

study_mode = sidebar_state["study_mode"]
current_chapter = sidebar_state["chapter"] or (hierarchy.root_nodes[0].title if hierarchy.root_nodes else "Chapter 1")
current_section = sidebar_state["section"] or current_chapter

# Resolve context chunks for active chapter/section
matching_chunks = [
    {"chunk_id": c.chunk_id, "text": c.original_text, "metadata": c.metadata.to_dict()}
    for c in active_chunks
    if c.metadata.chapter == current_chapter or c.metadata.section == current_section
]

if not matching_chunks and active_chunks:
    matching_chunks = [
        {"chunk_id": active_chunks[0].chunk_id, "text": active_chunks[0].original_text, "metadata": active_chunks[0].metadata.to_dict()}
    ]

# Layout: 2 Columns (Center Content: 8 | Right Study Panel: 4)
col_center, col_right = st.columns([8, 4], gap="large")

with col_center:
    if study_mode == "📖 Teaching Mode":
        render_teaching_view(
            teacher=teacher,
            quiz_engine=quiz_engine,
            study_mgr=study_mgr,
            user_id=st.session_state["user_id"],
            book_id=active_book["id"],
            book_title=active_book["title"],
            chapter_title=current_chapter,
            section_title=current_section,
            context_chunks=matching_chunks
        )
    elif study_mode == "📝 Revision Mode":
        render_revision_view(
            book_id=active_book["id"],
            book_title=active_book["title"],
            study_mgr=study_mgr,
            user_id=st.session_state["user_id"]
        )
    elif study_mode == "🎯 Chapter Quiz":
        render_chapter_quiz_view(
            book_id=active_book["id"],
            chapter_title=current_chapter,
            study_mgr=study_mgr,
            user_id=st.session_state["user_id"]
        )
    elif study_mode == "🔍 Search by Topic":
        st.markdown(f"## 🔍 Semantic Topic Search: *{active_book['title']}*")
        search_query = st.text_input("Enter topic or keyword to search across the entire textbook:", placeholder="e.g. Memory virtualization, Multi-level page tables...")
        if search_query.strip():
            with st.spinner("Searching textbook via nomic-embed-text & ChromaDB..."):
                results = vectordb.query_similar(active_book["id"], search_query.strip(), embedder, n_results=6)
            if results:
                st.markdown(f"##### Found {len(results)} relevant sections:")
                for r in results:
                    meta = r["metadata"]
                    s_p = meta.get("start_page", 1)
                    e_p = meta.get("end_page", s_p)
                    ch = meta.get("chapter", "")
                    sec = meta.get("section", "")
                    rel = int(r.get("relevance_score", 0.9) * 100)
                    with st.expander(f"📖 {ch} — {sec} (Pages {s_p}–{e_p}) [Relevance: {rel}%]"):
                        st.markdown(f"> *{r['text'][:400]}...*")
                        if st.button(f"Jump to Section", key=f"jump_{r['chunk_id']}"):
                            st.session_state["nav_chapter"] = ch
                            st.session_state["nav_section"] = sec
                            st.session_state["radio_study_mode"] = "📖 Teaching Mode"
                            st.rerun()
            else:
                st.warning("No matching concepts found in this textbook.")

with col_right:
    current_page = matching_chunks[0]["metadata"].get("start_page", 1) if matching_chunks else 1
    total_sections_count = hierarchy.total_sections or len(active_chunks) or 1
    render_notes_panel(
        study_mgr=study_mgr,
        user_id=st.session_state["user_id"],
        book_id=active_book["id"],
        current_chapter=current_chapter,
        current_section=current_section,
        current_page=current_page,
        total_sections=total_sections_count
    )

# Bottom Docked Grounded Chat: 'Ask from Book'
render_chat_drawer(
    teacher=teacher,
    vectordb=vectordb,
    embedder=embedder,
    book_id=active_book["id"],
    book_title=active_book["title"]
)
