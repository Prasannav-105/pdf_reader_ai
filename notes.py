"""
notes.py: Study Features Persistence Layer (SQLite).
Manages Notes, Highlights, Bookmarks, and Reading Progress.
"""
import os
import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional, Any
from models.schema import UserNote, UserHighlight, UserBookmark, ReadingProgress

class StudyManager:
    """Handles SQLite persistence for notes, highlights, bookmarks, and progress."""

    def __init__(self, db_path: str = "./data/study_data.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Creates the necessary tables if they do not exist."""
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    book_id TEXT NOT NULL,
                    chapter TEXT NOT NULL,
                    section TEXT NOT NULL,
                    page_number INTEGER NOT NULL,
                    note_text TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS highlights (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    book_id TEXT NOT NULL,
                    chapter TEXT NOT NULL,
                    section TEXT NOT NULL,
                    page_number INTEGER NOT NULL,
                    highlight_text TEXT NOT NULL,
                    color TEXT DEFAULT 'yellow',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bookmarks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    book_id TEXT NOT NULL,
                    chapter TEXT NOT NULL,
                    section TEXT NOT NULL,
                    page_number INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reading_progress (
                    user_id TEXT NOT NULL,
                    book_id TEXT NOT NULL,
                    last_chapter TEXT NOT NULL,
                    last_section TEXT NOT NULL,
                    last_page INTEGER NOT NULL,
                    completed_sections TEXT DEFAULT '[]',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, book_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS quiz_scores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    book_id TEXT NOT NULL,
                    chapter TEXT NOT NULL,
                    section TEXT NOT NULL,
                    score REAL NOT NULL,
                    details TEXT DEFAULT '{}',
                    taken_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    book_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    sources TEXT DEFAULT '[]',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    # --- Notes ---
    def add_note(self, user_id: str, book_id: str, chapter: str, section: str, page_number: int, note_text: str) -> int:
        with self._get_conn() as conn:
            cur = conn.execute("""
                INSERT INTO notes (user_id, book_id, chapter, section, page_number, note_text)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, book_id, chapter, section, page_number, note_text))
            conn.commit()
            return cur.lastrowid

    def get_notes(self, user_id: str, book_id: str, chapter: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            if chapter:
                cur = conn.execute("""
                    SELECT * FROM notes WHERE user_id = ? AND book_id = ? AND chapter = ?
                    ORDER BY id DESC
                """, (user_id, book_id, chapter))
            else:
                cur = conn.execute("""
                    SELECT * FROM notes WHERE user_id = ? AND book_id = ?
                    ORDER BY id DESC
                """, (user_id, book_id))
            return [dict(row) for row in cur.fetchall()]

    def delete_note(self, note_id: int):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            conn.commit()

    # --- Highlights ---
    def add_highlight(self, user_id: str, book_id: str, chapter: str, section: str, page_number: int, highlight_text: str, color: str = "yellow") -> int:
        with self._get_conn() as conn:
            cur = conn.execute("""
                INSERT INTO highlights (user_id, book_id, chapter, section, page_number, highlight_text, color)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_id, book_id, chapter, section, page_number, highlight_text, color))
            conn.commit()
            return cur.lastrowid

    def get_highlights(self, user_id: str, book_id: str) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cur = conn.execute("""
                SELECT * FROM highlights WHERE user_id = ? AND book_id = ?
                ORDER BY id DESC
            """, (user_id, book_id))
            return [dict(row) for row in cur.fetchall()]

    def delete_highlight(self, highlight_id: int):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM highlights WHERE id = ?", (highlight_id,))
            conn.commit()

    # --- Bookmarks ---
    def add_bookmark(self, user_id: str, book_id: str, chapter: str, section: str, page_number: int, title: str) -> int:
        with self._get_conn() as conn:
            cur = conn.execute("""
                INSERT INTO bookmarks (user_id, book_id, chapter, section, page_number, title)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, book_id, chapter, section, page_number, title))
            conn.commit()
            return cur.lastrowid

    def get_bookmarks(self, user_id: str, book_id: str) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cur = conn.execute("""
                SELECT * FROM bookmarks WHERE user_id = ? AND book_id = ?
                ORDER BY id DESC
            """, (user_id, book_id))
            return [dict(row) for row in cur.fetchall()]

    def delete_bookmark(self, bookmark_id: int):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM bookmarks WHERE id = ?", (bookmark_id,))
            conn.commit()

    # --- Reading Progress & Continue Reading ---
    def save_reading_position(self, user_id: str, book_id: str, chapter: str, section: str, page: int):
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO reading_progress (user_id, book_id, last_chapter, last_section, last_page, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id, book_id) DO UPDATE SET
                    last_chapter = excluded.last_chapter,
                    last_section = excluded.last_section,
                    last_page = excluded.last_page,
                    updated_at = CURRENT_TIMESTAMP
            """, (user_id, book_id, chapter, section, page))
            conn.commit()

    def get_reading_position(self, user_id: str, book_id: str) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            cur = conn.execute("""
                SELECT * FROM reading_progress WHERE user_id = ? AND book_id = ?
            """, (user_id, book_id))
            row = cur.fetchone()
            if row:
                d = dict(row)
                try:
                    d["completed_sections"] = json.loads(d.get("completed_sections") or "[]")
                except Exception:
                    d["completed_sections"] = []
                return d
            return None

    def mark_section_completed(self, user_id: str, book_id: str, section_key: str):
        pos = self.get_reading_position(user_id, book_id)
        completed = pos.get("completed_sections", []) if pos else []
        if section_key not in completed:
            completed.append(section_key)
            with self._get_conn() as conn:
                conn.execute("""
                    INSERT INTO reading_progress (user_id, book_id, last_chapter, last_section, last_page, completed_sections, updated_at)
                    VALUES (?, ?, '', '', 1, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(user_id, book_id) DO UPDATE SET
                        completed_sections = excluded.completed_sections,
                        updated_at = CURRENT_TIMESTAMP
                """, (user_id, book_id, json.dumps(completed)))
                conn.commit()

    # --- Quiz Scores ---
    def record_quiz_score(self, user_id: str, book_id: str, chapter: str, section: str, score: float, details: Optional[dict] = None):
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO quiz_scores (user_id, book_id, chapter, section, score, details)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, book_id, chapter, section, score, json.dumps(details or {})))
            conn.commit()

    def get_quiz_scores(self, user_id: str, book_id: str) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cur = conn.execute("""
                SELECT * FROM quiz_scores WHERE user_id = ? AND book_id = ?
                ORDER BY id DESC
            """, (user_id, book_id))
            return [dict(row) for row in cur.fetchall()]

    # --- Grounded Q&A Chat History ---
    def save_chat_message(self, user_id: str, book_id: str, role: str, content: str, sources: Optional[List[str]] = None) -> int:
        """Saves a grounded chat message to persistent SQLite database."""
        with self._get_conn() as conn:
            cur = conn.execute("""
                INSERT INTO chat_history (user_id, book_id, role, content, sources)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, book_id, role, content, json.dumps(sources or [])))
            conn.commit()
            return cur.lastrowid

    def get_chat_history(self, user_id: str, book_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves recent chat messages for a user and specific book."""
        with self._get_conn() as conn:
            cur = conn.execute("""
                SELECT role, content, sources, created_at FROM chat_history
                WHERE user_id = ? AND book_id = ?
                ORDER BY id ASC
                LIMIT ?
            """, (user_id, book_id, limit))
            res = []
            for row in cur.fetchall():
                d = dict(row)
                try:
                    d["sources"] = json.loads(d.get("sources") or "[]")
                except Exception:
                    d["sources"] = []
                res.append(d)
            return res

    def clear_chat_history(self, user_id: str, book_id: str):
        """Clears all chat history for a specific user and book."""
        with self._get_conn() as conn:
            conn.execute("""
                DELETE FROM chat_history WHERE user_id = ? AND book_id = ?
            """, (user_id, book_id))
            conn.commit()

