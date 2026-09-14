"""
chat_drawer.py: Bottom 'Ask from Book' Grounded Chat Interface.
Strictly queries ChromaDB vector store and prevents hallucination.
"""
import streamlit as st
from typing import Dict, Any, List
from teacher import TeacherEngine
from vectordb import VectorDBManager
from embeddings import OllamaEmbedder

def render_chat_drawer(
    teacher: TeacherEngine,
    vectordb: VectorDBManager,
    embedder: OllamaEmbedder,
    book_id: str,
    book_title: str
):
    """Renders bottom dockable Q&A chat with strict textbook grounding."""
    with st.expander("💬 **Ask from Book** (Strict Anti-Hallucination Q&A)", expanded=False):
        st.caption("💡 *Ask anything about the textbook. The AI will answer ONLY from verified book excerpts with page numbers.*")

        if "book_chat_history" not in st.session_state:
            st.session_state["book_chat_history"] = []

        # Display chat messages
        for msg in st.session_state["book_chat_history"]:
            if msg["role"] == "user":
                st.markdown(f"<div class='chat-bubble-user'>🧑‍🎓 <b>You:</b><br>{msg['content']}</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div class='chat-bubble-ai'>📖 <b>Textbook Tutor:</b><br>{msg['content']}</div>", unsafe_allow_html=True)

        # Question input form
        with st.form("ask_book_form", clear_on_submit=True):
            user_query = st.text_input("Ask a question from this book:", placeholder="e.g. What is the difference between sem_wait() and sem_post()?")
            col_sub1, col_sub2 = st.columns([4, 1])
            with col_sub2:
                submitted = st.form_submit_button("Search & Ask 🔍", use_container_width=True)

        if submitted and user_query.strip():
            # 1. Add user query to history
            st.session_state["book_chat_history"].append({"role": "user", "content": user_query.strip()})

            # 2. Retrieve top-3 chunks from ChromaDB
            with st.spinner("Searching textbook pages..."):
                retrieved = vectordb.query_similar(book_id, user_query.strip(), embedder, n_results=3)

            # 3. Stream strict answer
            placeholder = st.empty()
            full_response = ""
            for delta in teacher.ask_from_book(book_title, user_query.strip(), retrieved, st.session_state["book_chat_history"]):
                full_response += delta
                placeholder.markdown(f"<div class='chat-bubble-ai'>📖 <b>Textbook Tutor:</b><br>{full_response}▌</div>", unsafe_allow_html=True)

            placeholder.markdown(f"<div class='chat-bubble-ai'>📖 <b>Textbook Tutor:</b><br>{full_response}</div>", unsafe_allow_html=True)
            st.session_state["book_chat_history"].append({"role": "assistant", "content": full_response})
            st.rerun()
