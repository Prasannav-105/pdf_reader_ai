"""
chat_drawer.py: Bottom 'Ask from Book' Grounded Chat Interface.
Strictly queries ChromaDB vector store and prevents hallucination.
"""
import streamlit as st
from typing import Dict, Any, List, Optional
from teacher import TeacherEngine
from vectordb import VectorDBManager
from embeddings import OllamaEmbedder
from notes import StudyManager

def render_chat_drawer(
    teacher: TeacherEngine,
    vectordb: VectorDBManager,
    embedder: OllamaEmbedder,
    book_id: str,
    book_title: str,
    study_mgr: StudyManager,
    user_id: str,
    num_gpu: int = 0
):
    """Renders bottom dockable Q&A chat with persistent SQLite storage and strict textbook grounding."""
    with st.expander("💬 **Ask from Book** (Strict Anti-Hallucination Q&A)", expanded=False):
        top_col1, top_col2 = st.columns([6, 1])
        with top_col1:
            st.caption("💡 *Ask anything about this textbook. The AI will answer ONLY from verified book excerpts with page numbers.*")
        with top_col2:
            if st.button("🗑️ Clear", key=f"clear_chat_{book_id}", help="Clear chat history for this book"):
                study_mgr.clear_chat_history(user_id, book_id)
                st.rerun()

        # Load persisted messages from SQLite
        chat_messages = study_mgr.get_chat_history(user_id, book_id, limit=50)

        # Display chat messages
        for msg in chat_messages:
            if msg["role"] == "user":
                st.markdown(f"<div class='chat-bubble-user'>🧑‍🎓 <b>You:</b><br>{msg['content']}</div>", unsafe_allow_html=True)
            else:
                sources_html = ""
                if msg.get("sources"):
                    sources_str = ", ".join(msg["sources"][:3])
                    sources_html = f"<div style='font-size: 0.75rem; color: #38BDF8; margin-top: 6px;'>📖 Sources: {sources_str}</div>"
                st.markdown(f"<div class='chat-bubble-ai'>📖 <b>Textbook Tutor:</b><br>{msg['content']}{sources_html}</div>", unsafe_allow_html=True)

        # Question input form
        with st.form("ask_book_form", clear_on_submit=True):
            user_query = st.text_input("Ask a question from this book:", placeholder="e.g. How does cpu.c virtualize the CPU? Or what is sem_wait()?")
            col_sub1, col_sub2 = st.columns([4, 1])
            with col_sub2:
                submitted = st.form_submit_button("Search & Ask 🔍", use_container_width=True)

        if submitted and user_query.strip():
            query_clean = user_query.strip()
            # 1. Save user query to SQLite
            study_mgr.save_chat_message(user_id, book_id, "user", query_clean)

            # 2. Retrieve top-3 chunks from ChromaDB
            with st.spinner("Searching textbook pages..."):
                retrieved = vectordb.query_similar(book_id, query_clean, embedder, n_results=3)

            # Extract source page citations
            sources_list = []
            for c in retrieved:
                m = c.get("metadata", {})
                sp = m.get("start_page", 1)
                ep = m.get("end_page", sp)
                ch = m.get("chapter", "Textbook")
                sources_list.append(f"Pages {sp}-{ep} ({ch})")

            # 3. Stream strict answer
            placeholder = st.empty()
            full_response = ""
            # Prepare conversation history format for LLM
            history_tuples = [{"role": m["role"], "content": m["content"]} for m in chat_messages[-4:]]
            
            for delta in teacher.ask_from_book(book_title, query_clean, retrieved, history_tuples, num_gpu=num_gpu):
                full_response += delta
                placeholder.markdown(f"<div class='chat-bubble-ai'>📖 <b>Textbook Tutor:</b><br>{full_response}▌</div>", unsafe_allow_html=True)

            placeholder.markdown(f"<div class='chat-bubble-ai'>📖 <b>Textbook Tutor:</b><br>{full_response}</div>", unsafe_allow_html=True)
            # 4. Save assistant response to SQLite
            study_mgr.save_chat_message(user_id, book_id, "assistant", full_response, sources=sources_list)
            st.rerun()
