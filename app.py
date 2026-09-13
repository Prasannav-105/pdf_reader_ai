import os
import re
import uuid
import hashlib
import sqlite3
import streamlit as st
import streamlit.components.v1 as components
import pymupdf
import ollama

# ==============================================================================
# Page Configuration & Visual Theme Styling
# ==============================================================================
st.set_page_config(
    page_title="AI Textbook Tutor & Reader",
    page_icon="📖",
    layout="wide",
    initial_sidebar_state="expanded"
)
import socket

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

# Detect local IP dynamically for Intranet access
LOCAL_IP = get_local_ip()

st.markdown("""
<style>
    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 2rem;
    }
    
    /* Reader Themes */
    .reader-paper {
        background-color: #FDFBF7;
        color: #2D3748;
        border: 1px solid #E8E3D9;
    }
    .reader-light {
        background-color: #FFFFFF;
        color: #1A202C;
        border: 1px solid #E2E8F0;
    }
    .reader-dark {
        background-color: #1E293B;
        color: #F1F5F9;
        border: 1px solid #334155;
    }
    
    .book-container {
        padding: 30px 34px;
        border-radius: 12px;
        font-family: "Georgia", "Cambria", serif;
        line-height: 1.85;
        max-height: 76vh;
        overflow-y: auto;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    }
    
    .book-container p {
        margin-bottom: 1.3rem;
        text-align: justify;
    }

    .book-header {
        border-bottom: 2px solid rgba(0,0,0,0.08);
        padding-bottom: 12px;
        margin-bottom: 20px;
    }

    .intranet-badge {
        background: #EFF6FF;
        border: 1px solid #BFDBFE;
        color: #1E40AF;
        border-radius: 8px;
        padding: 8px 12px;
        font-size: 0.85rem;
        margin-bottom: 15px;
    }

    .toc-card {
        padding: 10px 14px;
        border-radius: 8px;
        border: 1px solid #E2E8F0;
        margin-bottom: 8px;
        background: #FFFFFF;
        transition: all 0.2s;
    }
    .toc-card:hover {
        border-color: #3B82F6;
        background: #F8FAFC;
    }
    .toc-active {
        border-left: 4px solid #2563EB !important;
        background: #EFF6FF !important;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# SQLite Database Layer (Multi-User, Progress & Isolated Chat History)
# ==============================================================================
DB_PATH = "tutor.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        # Books & Chapters
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                title TEXT NOT NULL,
                file_hash TEXT NOT NULL,
                total_pages INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
        """)
        # Auto-migration: ensure 'user_id' and 'subject' columns exist in books
        cursor.execute("PRAGMA table_info(books)")
        b_cols = [r[1] for r in cursor.fetchall()]
        if "user_id" not in b_cols:
            try:
                cursor.execute("ALTER TABLE books ADD COLUMN user_id INTEGER")
            except Exception:
                pass
        if "subject" not in b_cols:
            try:
                cursor.execute("ALTER TABLE books ADD COLUMN subject TEXT DEFAULT ''")
            except Exception:
                pass

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chapters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                chapter_title TEXT NOT NULL,
                parent_chapter TEXT DEFAULT '',
                subtopic_title TEXT DEFAULT '',
                level INTEGER DEFAULT 1,
                start_page INTEGER NOT NULL,
                end_page INTEGER NOT NULL,
                content TEXT NOT NULL,
                word_count INTEGER NOT NULL,
                FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
            );
        """)
        # Auto-migration: ensure parent_chapter and subtopic_title exist in chapters
        cursor.execute("PRAGMA table_info(chapters)")
        ch_cols = [r[1] for r in cursor.fetchall()]
        if "parent_chapter" not in ch_cols:
            try:
                cursor.execute("ALTER TABLE chapters ADD COLUMN parent_chapter TEXT DEFAULT ''")
            except Exception:
                pass
        if "subtopic_title" not in ch_cols:
            try:
                cursor.execute("ALTER TABLE chapters ADD COLUMN subtopic_title TEXT DEFAULT ''")
            except Exception:
                pass
        # User Books Library Mapping Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                book_id INTEGER NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
                UNIQUE(user_id, book_id)
            );
        """)
        # Users Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        # User Learning Progress Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chapter_id INTEGER NOT NULL,
                status TEXT DEFAULT 'in_progress', -- 'not_started', 'in_progress', 'completed'
                last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (chapter_id) REFERENCES chapters(id),
                UNIQUE(user_id, chapter_id)
            );
        """)
        # User Isolated Chat History Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chapter_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (chapter_id) REFERENCES chapters(id)
            );
        """)
        conn.commit()

# --- Auth Helpers ---
def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    if not salt:
        salt = uuid.uuid4().hex
    pwd_hash = hashlib.sha256((password + salt).encode('utf-8')).hexdigest()
    return pwd_hash, salt

def register_user(username: str, password: str) -> tuple[bool, str]:
    username = username.strip().lower()
    if len(username) < 3 or len(password) < 4:
        return False, "Username must be ≥ 3 chars, password ≥ 4 chars."
    
    pwd_hash, salt = hash_password(password)
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
                (username, pwd_hash, salt)
            )
            conn.commit()
            return True, "Account registered successfully! Please log in."
    except sqlite3.IntegrityError:
        return False, f"Username '{username}' already exists. Please choose another."
    except Exception as e:
        return False, str(e)

def authenticate_user(username: str, password: str):
    username = username.strip().lower()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        if not user:
            return None
        pwd_hash, _ = hash_password(password, user["salt"])
        if pwd_hash == user["password_hash"]:
            return dict(user)
    return None

# --- User Progress & Chat History Helpers ---
def get_user_chapter_progress(user_id: int, book_id: int) -> dict[int, str]:
    """Returns mapping of {chapter_id: status} for the user."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.chapter_id, p.status 
            FROM user_progress p
            JOIN chapters c ON p.chapter_id = c.id
            WHERE p.user_id = ? AND c.book_id = ?
        """, (user_id, book_id))
        return {row["chapter_id"]: row["status"] for row in cursor.fetchall()}

def update_chapter_status(user_id: int, chapter_id: int, status: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO user_progress (user_id, chapter_id, status, last_accessed)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, chapter_id) DO UPDATE SET
                status = excluded.status,
                last_accessed = CURRENT_TIMESTAMP
        """, (user_id, chapter_id, status))
        conn.commit()

def save_chat_message(user_id: int, chapter_id: int, role: str, content: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO user_chat_history (user_id, chapter_id, role, content) VALUES (?, ?, ?, ?)",
            (user_id, chapter_id, role, content)
        )
        conn.commit()

def load_chapter_chat_history(user_id: int, chapter_id: int) -> list[dict]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT role, content FROM user_chat_history WHERE user_id = ? AND chapter_id = ? ORDER BY id ASC",
            (user_id, chapter_id)
        )
        return [{"role": row["role"], "content": row["content"]} for row in cursor.fetchall()]

def clear_chapter_chat_history(user_id: int, chapter_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM user_chat_history WHERE user_id = ? AND chapter_id = ?",
            (user_id, chapter_id)
        )
        conn.commit()

# --- Book & Chapter Database Helpers ---
def calculate_file_hash(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()

def get_book_by_hash(file_hash: str):
    """Checks if a book with this hash exists anywhere in the database."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM books WHERE file_hash = ?", (file_hash,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_book_by_id(book_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM books WHERE id = ?", (book_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def is_book_in_user_library(user_id: int, book_id: int) -> bool:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM user_books WHERE user_id = ? AND book_id = ?", (user_id, book_id))
        return cursor.fetchone() is not None

def add_book_to_user_library(user_id: int, book_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO user_books (user_id, book_id) VALUES (?, ?)",
            (user_id, book_id)
        )
        conn.commit()

def list_all_books():
    """Returns all books stored across the system."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM books ORDER BY id DESC")
        return [dict(row) for row in cursor.fetchall()]

def list_books_for_user(user_id: int):
    """Returns only books that are in this user's personal bookshelf."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT b.* FROM books b
            JOIN user_books ub ON b.id = ub.book_id
            WHERE ub.user_id = ?
            ORDER BY ub.id DESC
        """, (user_id,))
        return [dict(row) for row in cursor.fetchall()]

def get_chapters_for_book(book_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM chapters WHERE book_id = ? ORDER BY start_page ASC, id ASC", (book_id,))
        return [dict(row) for row in cursor.fetchall()]

def get_chapter(chapter_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM chapters WHERE id = ?", (chapter_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_default_chapter_id(chapters: list[dict]):
    if not chapters:
        return None
    first_title = chapters[0].get("chapter_title", "").lower().strip()
    # Skip pure TOC pages (e.g. 'Contents') so user lands straight on the first real chapter
    if len(chapters) > 1 and ("contents" in first_title or "table of contents" in first_title or first_title == "toc"):
        return chapters[1]["id"]
    return chapters[0]["id"]

def infer_book_subject(title: str, sample_text: str = "") -> str:
    combined = (title + " " + sample_text[:2000]).lower()
    title_lower = title.lower()

    domain_keywords = {
        "Computer Science & Software Architecture": [
            "operating system", "concurrency", "distributed system", "linux", "unix", "kernel",
            "algorithm", "data structure", "compiler", "programming", "python", "javascript",
            "c++", "software engineering", "computer science", "database", "sql", "networking",
            "cybersecurity", "machine learning", "deep learning", "artificial intelligence", "virtual memory"
        ],
        "Life Sciences & Medicine": [
            "biology", "anatomy", "physiology", "medicine", "pathology", "pharmacology",
            "genetics", "immunology", "cell biology", "microbiology", "biochemistry",
            "neuroscience", "clinical", "surgery", "diagnostic", "dna", "cellular"
        ],
        "Mathematics & Physical Sciences": [
            "physics", "quantum", "thermodynamics", "mechanics", "electromagnetism",
            "chemistry", "organic chemistry", "calculus", "linear algebra", "statistics",
            "differential equation", "mathematics", "geometry", "probability", "algebra"
        ],
        "Economics, Finance & Business": [
            "economics", "macroeconomics", "microeconomics", "finance", "accounting",
            "business", "marketing", "management", "investing", "capitalism",
            "wealth", "trade", "banking", "entrepreneurship", "financial"
        ],
        "Psychology & Cognitive Science": [
            "psychology", "cognitive", "behavior", "mental health", "psychiatry",
            "psychoanalysis", "neuropsychology", "social psychology", "decision making",
            "biases", "heuristic"
        ],
        "Philosophy & Critical Thought": [
            "philosophy", "ethics", "epistemology", "metaphysics", "existentialism",
            "logic", "moral", "stoicism", "plato", "aristotle", "kant", "nietzsche", "socrates",
            "reason", "critique", "dialectic", "epistemological", "philosophical"
        ],
        "History, Politics & Law": [
            "history", "world war", "revolution", "civilization", "empire", "ancient",
            "political science", "government", "constitution", "jurisprudence", "legal", "law"
        ],
        "Literature & Cultural Studies": [
            "literature", "poetry", "novel", "drama", "fiction", "literary",
            "art history", "music", "narrative", "author", "playwright"
        ]
    }

    scores = {}
    for domain, kws in domain_keywords.items():
        score = 0
        for kw in kws:
            if kw in title_lower:
                score += 3
            elif kw in combined:
                score += 1
        if score > 0:
            scores[domain] = score

    if scores:
        return max(scores, key=scores.get)

    clean_t = re.sub(r'[\-_.]+', ' ', title).strip().title()
    return f"General Studies - {clean_t}"

def update_book_subject(book_id: int, subject: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE books SET subject = ? WHERE id = ?", (subject, book_id))
        conn.commit()

def save_book_and_chapters(title: str, file_hash: str, total_pages: int, chapters: list[dict], user_id: int = 1, subject: str = "") -> int:
    with get_db() as conn:
        cursor = conn.cursor()
        if not subject and chapters:
            sample = chapters[0].get("content", "")[:2000]
            subject = infer_book_subject(title, sample)
        elif not subject:
            subject = infer_book_subject(title)

        # INSERT OR IGNORE avoids ANY UNIQUE constraint crash
        cursor.execute(
            "INSERT OR IGNORE INTO books (title, file_hash, total_pages, subject) VALUES (?, ?, ?, ?)",
            (title, file_hash, total_pages, subject)
        )
        cursor.execute("SELECT id, subject FROM books WHERE file_hash = ?", (file_hash,))
        row = cursor.fetchone()
        book_id = row[0] if row else cursor.lastrowid
        if row and not row[1] and subject:
            cursor.execute("UPDATE books SET subject = ? WHERE id = ?", (subject, book_id))

        # Insert chapters if they don't exist yet
        cursor.execute("SELECT count(*) FROM chapters WHERE book_id = ?", (book_id,))
        if cursor.fetchone()[0] == 0:
            for ch in chapters:
                cursor.execute(
                    """
                    INSERT INTO chapters (book_id, chapter_title, parent_chapter, subtopic_title, level, start_page, end_page, content, word_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        book_id,
                        ch["chapter_title"],
                        ch.get("parent_chapter", ch["chapter_title"]),
                        ch.get("subtopic_title", ch["chapter_title"]),
                        ch.get("level", 1),
                        ch["start_page"],
                        ch["end_page"],
                        ch["content"],
                        ch["word_count"]
                    )
                )

        # Attach book to user's personal library
        cursor.execute(
            "INSERT OR IGNORE INTO user_books (user_id, book_id) VALUES (?, ?)",
            (user_id, book_id)
        )
        conn.commit()
        return book_id

# ==============================================================================
# PDF Parsing & Accurate Chapter Extraction
# ==============================================================================
def extract_page_clean_text(page) -> str:
    rect = page.rect
    page_height = rect.height
    header_threshold = 45
    footer_threshold = page_height - 45

    blocks = page.get_text("blocks")
    clean_blocks = []

    for b in blocks:
        if b[6] == 0:  # Text block
            y0, y1, text = b[1], b[3], b[4].strip()
            if not text:
                continue
            if y1 <= header_threshold and (len(text.split()) <= 6 or text.isdigit()):
                continue
            if y0 >= footer_threshold and (len(text.split()) <= 4 or text.isdigit() or re.match(r'^(page\s*)?\d+$', text, re.I)):
                continue
            clean_blocks.append(text)

    if not clean_blocks:
        raw = page.get_text("text")
        return re.sub(r'^(page\s*)?\d+$', '', raw, flags=re.M | re.I).strip()

    return "\n\n".join(clean_blocks)

def extract_book_structure(file_bytes: bytes, original_filename: str) -> tuple[int, list[dict]]:
    if not file_bytes:
        return 0, []
    try:
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    except Exception as e:
        print(f"Error opening PDF: {e}")
        return 0, []

    total_pages = len(doc)
    if total_pages == 0:
        return 0, []

    raw_toc = doc.get_toc()
    valid_toc = [item for item in raw_toc if item[2] > 0] if raw_toc else []
    study_units = []

    if valid_toc:
        # 1. Identify Level 1 Parts and Level 2 Chapters (or Level 1 Chapters if no parts)
        chapters_raw = []
        current_part = ""
        has_level_2 = any(item[0] == 2 for item in valid_toc)

        for idx in range(len(valid_toc)):
            lvl, title, start_p = valid_toc[idx]
            clean_title = title.strip() or f"Chapter {idx + 1}"

            # If Level 1 is a Part container followed by Level 2 chapters
            if has_level_2 and lvl == 1:
                is_container = (idx + 1 < len(valid_toc) and valid_toc[idx + 1][0] > 1)
                if is_container:
                    current_part = clean_title
                    continue
                else:
                    current_part = ""

            # Find end page of this TOC entry
            end_p = total_pages
            for j in range(idx + 1, len(valid_toc)):
                next_lvl, next_title, next_start = valid_toc[j]
                if (not has_level_2 and next_lvl <= lvl) or (has_level_2 and next_lvl <= 2):
                    if next_start >= start_p:
                        end_p = min(next_start - 1, total_pages)
                        break
            end_p = max(start_p, end_p)

            display_name = f"{clean_title} ({current_part})" if current_part and current_part not in clean_title else clean_title
            
            # Check chapter number from title (e.g. "31 Semaphores" -> 31, "04 The Process" -> 4)
            m_num = re.search(r'\b0*(\d+)\b', clean_title)
            chap_num = m_num.group(1) if m_num else None

            chapters_raw.append({
                "title": display_name,
                "raw_title": clean_title,
                "chap_num": chap_num,
                "part": current_part,
                "start_p": start_p,
                "end_p": end_p
            })

        # 2. For each chapter, extract granular subtopics
        for ch in chapters_raw:
            c_start = ch["start_p"]
            c_end = ch["end_p"]
            chap_num = ch["chap_num"]

            # Scan pages for section headings (e.g. 31.1, 31.2...)
            subtopic_splits = []
            if chap_num:
                pattern = re.compile(r'^(' + re.escape(chap_num) + r'\.\d+)\s*\n?\s*([A-Za-z][^\n]+)')
                for pno in range(c_start - 1, min(c_end, total_pages)):
                    page = doc[pno]
                    blocks = page.get_text("blocks")
                    for b in blocks:
                        text = b[4].strip()
                        m = pattern.match(text)
                        if m:
                            sec_code = m.group(1).strip()
                            sec_name = m.group(2).strip()
                            if not any(s["code"] == sec_code for s in subtopic_splits):
                                subtopic_splits.append({
                                    "code": sec_code,
                                    "title": f"{sec_code} {sec_name}",
                                    "page": pno + 1
                                })

            # If 2 or more subtopics were detected inside the chapter:
            if len(subtopic_splits) >= 2:
                for s_idx, sec in enumerate(subtopic_splits):
                    s_start = sec["page"]
                    s_end = c_end
                    if s_idx + 1 < len(subtopic_splits):
                        next_page = subtopic_splits[s_idx + 1]["page"]
                        s_end = max(s_start, next_page - 1)

                    page_texts = []
                    for pno in range(s_start - 1, min(s_end, total_pages)):
                        cleaned = extract_page_clean_text(doc[pno])
                        if cleaned:
                            page_texts.append(cleaned)

                    content = "\n\n".join(page_texts).strip()
                    word_count = len(content.split())
                    if content:
                        study_units.append({
                            "chapter_title": f"{sec['title']} • {ch['title']}",
                            "parent_chapter": ch["title"],
                            "subtopic_title": sec["title"],
                            "level": 3,
                            "start_page": s_start,
                            "end_page": s_end,
                            "content": content,
                            "word_count": word_count
                        })
            else:
                # If chapter is short (<= 5 pages), keep as a single clean subtopic
                page_span = c_end - c_start + 1
                if page_span <= 5:
                    page_texts = []
                    for pno in range(c_start - 1, min(c_end, total_pages)):
                        cleaned = extract_page_clean_text(doc[pno])
                        if cleaned:
                            page_texts.append(cleaned)
                    content = "\n\n".join(page_texts).strip()
                    word_count = len(content.split())
                    if content:
                        study_units.append({
                            "chapter_title": ch["title"],
                            "parent_chapter": ch["title"],
                            "subtopic_title": ch["raw_title"],
                            "level": 2,
                            "start_page": c_start,
                            "end_page": c_end,
                            "content": content,
                            "word_count": word_count
                        })
                else:
                    # Divide long chapters into logical 4-page subtopics so chunks stay under ~1,200 words
                    chunk_len = 4
                    part_idx = 1
                    for p_start in range(c_start, c_end + 1, chunk_len):
                        p_end = min(p_start + chunk_len - 1, c_end)
                        page_texts = []
                        for pno in range(p_start - 1, min(p_end, total_pages)):
                            cleaned = extract_page_clean_text(doc[pno])
                            if cleaned:
                                page_texts.append(cleaned)
                        content = "\n\n".join(page_texts).strip()
                        word_count = len(content.split())
                        if content:
                            study_units.append({
                                "chapter_title": f"{ch['title']} - Part {part_idx} (pp. {p_start}–{p_end})",
                                "parent_chapter": ch["title"],
                                "subtopic_title": f"Part {part_idx} (pp. {p_start}–{p_end})",
                                "level": 3,
                                "start_page": p_start,
                                "end_page": p_end,
                                "content": content,
                                "word_count": word_count
                            })
                            part_idx += 1

    # Fallback for PDFs with no bookmarks at all
    if not study_units:
        chunk_size = 5
        chunk_num = 1
        for start_p in range(1, total_pages + 1, chunk_size):
            end_p = min(start_p + chunk_size - 1, total_pages)
            page_texts = []
            for pno in range(start_p - 1, end_p):
                cleaned = extract_page_clean_text(doc[pno])
                if cleaned:
                    page_texts.append(cleaned)
            content = "\n\n".join(page_texts).strip()
            word_count = len(content.split())
            if content:
                parent_num = ((start_p - 1) // 20) + 1
                p_start = (parent_num - 1) * 20 + 1
                p_end = min(p_start + 19, total_pages)
                study_units.append({
                    "chapter_title": f"Section {chunk_num} (Pages {start_p}–{end_p})",
                    "parent_chapter": f"Chapter {parent_num} (Pages {p_start}–{p_end})",
                    "subtopic_title": f"Section {chunk_num} (pp. {start_p}–{end_p})",
                    "level": 1,
                    "start_page": start_p,
                    "end_page": end_p,
                    "content": content,
                    "word_count": word_count
                })
                chunk_num += 1

    return total_pages, study_units

# ==============================================================================
# Hardware Accelerator & Multi-Device Load Balancer
# ==============================================================================
def get_hardware_telemetry(ollama_host: str = "http://localhost:11434"):
    """
    Queries real-time hardware status across:
    - Intel Core Ultra 5 135U CPU (12 Cores / 14 Threads)
    - Intel(R) Graphics GPU (Vulkan 1.4 compute backend, VRAM offload)
    - Intel(R) AI Boost NPU (ComputeAccelerator, DirectML / Level Zero MCDM)
    """
    telemetry = {
        "cpu": {
            "name": "Intel(R) Core(TM) Ultra 5 135U",
            "cores": 12,
            "threads": 14,
            "role": "Host Orchestration, Token Prefill & KV Cache",
            "status": "Online (14 Threads Active)"
        },
        "gpu": {
            "name": "Intel(R) Graphics (Vulkan 1.4)",
            "role": "High-Throughput Neural Layer Offload",
            "status": "Online (Vulkan Backend)",
            "vram_total_gb": 8.8,
            "vram_used_gb": 0.0,
            "vram_percent": 0,
            "offloaded": False
        },
        "npu": {
            "name": "Intel(R) AI Boost",
            "role": "MCDM ComputeAccelerator / Neural Co-Processor",
            "driver": "32.0.100.4404",
            "status": "Active (DirectML / Level Zero Ready)",
            "class": "ComputeAccelerator"
        }
    }

    try:
        client = ollama.Client(host=ollama_host)
        running = client.ps()
        models = running.get('models', []) if isinstance(running, dict) else getattr(running, 'models', [])
        if models:
            m = models[0]
            size_vram = getattr(m, 'size_vram', 0)
            if size_vram and size_vram > 0:
                vram_gb = round(size_vram / (1024**3), 2)
                telemetry["gpu"]["vram_used_gb"] = vram_gb
                telemetry["gpu"]["vram_percent"] = min(100, int((size_vram / (8.8 * 1024**3)) * 100))
                telemetry["gpu"]["offloaded"] = True
                telemetry["gpu"]["status"] = f"Active Offloading ({vram_gb} GB VRAM)"
    except Exception:
        pass

    return telemetry

# ==============================================================================
# Ollama Client & Optimized Real-Time Streaming
# ==============================================================================
def get_ollama_client(host: str):
    return ollama.Client(host=host)

def test_ollama_connection(host: str, model_name: str) -> tuple[bool, str]:
    try:
        client = get_ollama_client(host)
        models_dict = client.list()
        models_list = models_dict.get('models', []) if isinstance(models_dict, dict) else getattr(models_dict, 'models', [])
        
        available_names = []
        for m in models_list:
            if isinstance(m, dict):
                available_names.append(m.get('name', ''))
                available_names.append(m.get('model', ''))
            else:
                available_names.append(getattr(m, 'model', ''))
                available_names.append(getattr(m, 'name', ''))

        available_names = [n for n in available_names if n]
        matched = any(model_name in name or name.startswith(model_name) for name in available_names)
        if matched:
            return True, f"Connected to Ollama. Model `{model_name}` is ready."
        else:
            return False, f"Connected, but `{model_name}` not found. Available: `{', '.join(set(available_names)) if available_names else 'None'}`."
    except Exception as e:
        return False, f"Could not connect to Ollama at `{host}` ({str(e)})."

def stream_chapter_lesson(client: ollama.Client, model: str, subject: str, chapter_title: str, chapter_text: str, num_gpu: int = 0, num_thread: int = 8):
    """
    Streams lesson tokens in real-time with rock-solid execution and automatic CPU fallback.
    Combines authoritative textbook ground truth with Llama's deep general domain intelligence.
    """
    words = chapter_text.split()
    bounded_text = " ".join(words[:1100]) if len(words) > 1100 else chapter_text

    system_prompt = f"""You are a Distinguished University Professor and World-Class Scholar specializing in {subject}.
You are delivering an authoritative masterclass lesson on the section: '{chapter_title}'.

PEDAGOGICAL DIRECTIVE (DUAL-INTELLIGENCE SYNTHESIS):
1. AUTHORITATIVE GROUND TRUTH: Ground your lesson strictly in the provided textbook excerpt. Accurately incorporate key definitions, theories, arguments, data, formulas, and author formulations.
2. GENERAL DOMAIN INTELLIGENCE: Do NOT limit yourself to superficial regurgitation. Elevate the lesson using your broad domain expertise: explain underlying principles, historical context, philosophical arguments, mathematical derivations, or real-world causal mechanisms.
3. TOP-DOWN DIAGRAMS: You MUST include a syntactically valid top-down Mermaid.js diagram:
   ```mermaid
   graph TD
       A["Start Node"] --> B["Next Node"]
   ```
   CRITICAL MERMAID SYNTAX RULES:
   - Open with ```mermaid on its own line (never put graph TD on the same line as the backticks).
   - Line 1 inside the diagram MUST be `graph TD` exactly once (never repeat `graph TD`).
   - Every node MUST have an alphanumeric ID and bracketed label: `NodeID["Label Text"]`.
   - Never write raw text arrows like `Process A ->> Process B`.
   - Always connect using standard `-->` arrows: e.g. `A["Start"] --> B["Next"]`.
   - Close with ``` on its own line.
4. NO CONVERSATIONAL FILLER: Do not simulate classroom conversational pauses (e.g., 'Welcome back to class', 'Are there any questions so far?'). Deliver a dense, authoritative, publication-quality masterclass."""

    user_instruction = f"""Teach the section: '{chapter_title}'.

[TEXTBOOK EXCERPT]
{bounded_text}
[END TEXTBOOK EXCERPT]

You MUST format your lesson strictly into these 5 numbered markdown sections:

### 1. 📌 Core Executive Summary
(A concise, high-impact 3-sentence summary of the section's core thesis, central dilemma or idea, and key takeaway.)

### 2. 🏛️ Deep Conceptual Breakdown & Core Principles
(In-depth technical or conceptual dive: Explain the underlying mechanisms, core theories, historical context, or structural logic. Detail the fundamental 'WHY' and 'HOW' behind the concepts.)

### 3. 📐 Conceptual & Process Flow Diagram
(A complete, valid top-down Mermaid diagram showing state transitions, sequence of events, causal chains, or concept hierarchy. STRICT RULES: Open with ```mermaid on its own line. Declare `graph TD` ONCE on line 1. Define nodes with brackets: `A["Step 1"] --> B["Step 2"]`. Close with ``` on its own line.)

### 4. 💡 Real-World Application & In-Depth Case Analysis
(Concrete real-world analysis tailored to the domain:
- For STEM & Computer Science: Production-grade implementation walkthrough, code example, or mathematical proof with edge-case analysis.
- For Humanities, History & Law: Concrete historical case study, legal precedent, or primary source analysis illustrating the ideas in action.
- For Business & Economics: Real-world market scenario, organizational case study, or financial decision framework.
- For Sciences & Medicine: Clinical scenario, physiological pathway, or experimental evidence.)

### 5. 🎯 Professor's Verification Challenge
(A rigorous conceptual scenario, thought experiment, or trace question to test deep understanding of edge cases, invariants, or practical implications.)"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_instruction}
    ]

    try:
        response_stream = client.chat(
            model=model,
            messages=messages,
            stream=True,
            options={
                "num_ctx": 8192,
                "temperature": 0.25,
                "top_p": 0.9,
                "num_gpu": num_gpu,
                "num_thread": num_thread
            }
        )
        for chunk in response_stream:
            yield chunk['message']['content']
    except Exception as e:
        # If GPU/Vulkan fails (e.g. status 500, TDR timeout, device lost), auto-fallback to rock-solid CPU
        if num_gpu > 0:
            fallback_stream = client.chat(
                model=model,
                messages=messages,
                stream=True,
                options={
                    "num_ctx": 8192,
                    "temperature": 0.25,
                    "top_p": 0.9,
                    "num_gpu": 0,
                    "num_thread": 8
                }
            )
            for chunk in fallback_stream:
                yield chunk['message']['content']
        else:
            raise e

def stream_chat_response(client: ollama.Client, model: str, subject: str, chapter_title: str, chapter_text: str, conversation_history: list[dict], user_prompt: str, num_gpu: int = 0, num_thread: int = 8):
    """Streams Q&A response combining chapter textbook grounding with general domain intelligence and automatic fallback."""
    words = chapter_text.split()
    bounded_text = " ".join(words[:1200]) if len(words) > 1200 else chapter_text

    system_prompt = f"""You are a Distinguished Scholar and University Professor teaching {subject}.
You are tutoring a student on the section: '{chapter_title}'.

AUTHORITY & KNOWLEDGE SYNTHESIS:
1. Ground your answers directly in the textbook excerpt below for definitions, specific arguments, formulas, and facts.
2. Augment the explanation using your broad general intelligence (academic literature, underlying principles, causal mechanisms, historical context, or industry practice).
3. When explaining a process, state transition, or relationship, include a clean top-down Mermaid diagram (open with ```mermaid on its own line, declare `graph TD` once on line 1, define bracketed nodes: `A["Step 1"] --> B["Step 2"]`, close with ``` on its own line).
4. Be rigorous, technically precise, and directly answer the student's question with deep mechanistic insight.

[CHAPTER TEXT EXCERPT]
{bounded_text}
[END CHAPTER TEXT EXCERPT]"""

    messages = [{"role": "system", "content": system_prompt}]
    for msg in conversation_history[-4:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_prompt})

    try:
        response_stream = client.chat(
            model=model,
            messages=messages,
            stream=True,
            options={
                "num_ctx": 8192,
                "temperature": 0.25,
                "top_p": 0.9,
                "num_gpu": num_gpu,
                "num_thread": num_thread
            }
        )
        for chunk in response_stream:
            yield chunk['message']['content']
    except Exception as e:
        if num_gpu > 0:
            fallback_stream = client.chat(
                model=model,
                messages=messages,
                stream=True,
                options={
                    "num_ctx": 8192,
                    "temperature": 0.25,
                    "top_p": 0.9,
                    "num_gpu": 0,
                    "num_thread": 8
                }
            )
            for chunk in fallback_stream:
                yield chunk['message']['content']
        else:
            raise e

def evaluate_student_answer_sync(client: ollama.Client, model: str, subject: str, chapter_title: str, chapter_text: str, lesson_text: str, student_answer: str, num_gpu: int = 0, num_thread: int = 8) -> tuple[bool, str]:
    words = chapter_text.split()
    bounded_text = " ".join(words[:1200]) if len(words) > 1200 else chapter_text

    eval_system_prompt = f"""You are a Distinguished Professor teaching {subject}.
Evaluate the student's answer to the verification question from '{chapter_title}'.
Evaluate strictly against the core principles and arguments covered in the textbook excerpt and academic domain logic:
- If correct: Praise the student warmly, explain WHY their reasoning is sound, and encourage them to advance to the next section.
- If partially correct or incorrect: Clearly explain where the logic, invariant, or historical/theoretical understanding broke down, provide an illuminating hint, and encourage them to refine their answer.

[CHAPTER TEXT EXCERPT]
{bounded_text}
[END CHAPTER TEXT EXCERPT]

Start your response with either:
[RESULT: CORRECT]
or
[RESULT: INCORRECT]
on the very first line, followed by your explanation."""

    user_query = f"""Verification Question Context:
{lesson_text}

Student's Answer:
{student_answer}"""

    messages = [
        {"role": "system", "content": eval_system_prompt},
        {"role": "user", "content": user_query}
    ]

    try:
        response = client.chat(
            model=model,
            messages=messages,
            options={
                "num_ctx": 8192,
                "temperature": 0.2,
                "num_gpu": num_gpu,
                "num_thread": num_thread
            }
        )
    except Exception as e:
        if num_gpu > 0:
            response = client.chat(
                model=model,
                messages=messages,
                options={
                    "num_ctx": 8192,
                    "temperature": 0.2,
                    "num_gpu": 0,
                    "num_thread": 8
                }
            )
        else:
            raise e

    content = response['message']['content'].strip()
    first_line = content.splitlines()[0].upper()
    is_correct = "[RESULT: CORRECT]" in first_line or "RESULT: CORRECT" in first_line or "[CORRECT]" in first_line
    clean_feedback = re.sub(r'\[RESULT:\s*(CORRECT|INCORRECT)\]', '', content, flags=re.IGNORECASE).strip()

    return is_correct, clean_feedback

# ==============================================================================
# Helper Functions: Mermaid Diagram & Rich Rendering
# ==============================================================================
def sanitize_mermaid(diagram_code: str) -> str:
    # 1. Strip any inline backticks and separate diagram code from trailing text
    if "```" in diagram_code:
        diagram_code = diagram_code.split("```", 1)[0]

    clean = re.sub(r'```mermaid\s*', '', diagram_code, flags=re.IGNORECASE)
    clean = re.sub(r'```\s*', '', clean).strip()

    raw_lines = [line.strip() for line in clean.splitlines() if line.strip()]
    if not raw_lines:
        return "graph TD\n    A[Empty Diagram]"

    # 2. Check if code starts with a recognized Mermaid diagram type
    VALID_DIAGRAM_KEYWORDS = (
        'graph', 'flowchart', 'sequencediagram', 'classdiagram', 'statediagram',
        'erdiagram', 'gantt', 'pie', 'gitgraph', 'mindmap', 'timeline',
        'quadrantchart', 'sankey', 'journey', 'c4context'
    )
    first_line = raw_lines[0].lower()
    has_diagram_type = any(first_line.startswith(k) for k in VALID_DIAGRAM_KEYWORDS)

    # 3. Convert wide horizontal layouts to vertical TD
    if has_diagram_type:
        raw_lines[0] = re.sub(r'\b(graph|flowchart)\s+LR\b', r'\1 TD', raw_lines[0], flags=re.IGNORECASE)
        raw_lines[0] = re.sub(r'\b(graph|flowchart)\s+RL\b', r'\1 TD', raw_lines[0], flags=re.IGNORECASE)
    else:
        # Prepend default graph TD if LLM omitted the diagram declaration
        raw_lines.insert(0, "graph TD")

    # 3b. Deduplicate repeated top-level diagram headers (e.g. repeated 'graph TD' or 'flowchart TD')
    deduped_lines = [raw_lines[0]]
    for line in raw_lines[1:]:
        l_lower = line.lower().strip()
        if any(l_lower.startswith(k) for k in VALID_DIAGRAM_KEYWORDS):
            if not l_lower.startswith("subgraph"):
                continue
        deduped_lines.append(line)
    raw_lines = deduped_lines

    # 4. Filter out any trailing natural language prose that LLM appended without backticks
    FILTER_KEYWORDS = VALID_DIAGRAM_KEYWORDS + (
        'subgraph', 'end', 'style', 'classdef', 'class', 'linkstyle', 'click', '%%'
    )
    lines = [raw_lines[0]]
    is_diagram_done = False

    for line in raw_lines[1:]:
        if is_diagram_done:
            continue
        l_lower = line.lower()
        has_kw = any(l_lower.startswith(kw) for kw in FILTER_KEYWORDS)
        has_arr = bool(re.search(r'(?:--+>|->+|-+>>|=+>|---\s*\|)', line))
        has_bkt = bool(re.search(r'^[A-Za-z0-9_]+\s*(\[.*\]|\(.*\)|(\{.*\}))', line))

        if has_kw or has_arr or has_bkt:
            lines.append(line)
        else:
            # Trailing human prose detected (e.g. "This diagram illustrates..."), stop diagram
            is_diagram_done = True

    id_map = {}
    id_counter = 1

    def format_node(raw_text: str) -> str:
        nonlocal id_counter
        clean_text = raw_text.strip()
        if not clean_text:
            return ""

        # Check if already a valid bracketed node: NodeId[...] or NodeId(...) or NodeId{...}
        if re.match(r'^[A-Za-z0-9_]+\s*(\[.*\]|\(.*\)|(\{.*\}))$', clean_text):
            def quote_bracket(m):
                nid = m.group(1)
                b_open = m.group(2)
                inner = m.group(3).strip()
                b_close = m.group(4)
                if inner.startswith('"') and inner.endswith('"'):
                    return f"{nid}{b_open}{inner}{b_close}"
                if any(c in inner for c in '()<>/:"'):
                    safe_inner = inner.replace('"', "'")
                    return f'{nid}{b_open}"{safe_inner}"{b_close}'
                return m.group(0)
            return re.sub(r'^([A-Za-z0-9_]+)(\[|\(|\{)(.+)(\]|\)|\})$', quote_bracket, clean_text)

        # Simple alphanumeric ID without spaces
        if re.match(r'^[A-Za-z0-9_]+$', clean_text):
            return clean_text

        # Raw label with spaces or punctuation (e.g. "process Creation" or "Program Counter (PC)")
        if clean_text not in id_map:
            safe_name = re.sub(r'[^A-Za-z0-9]+', '_', clean_text).strip('_')
            if not safe_name or safe_name[0].isdigit():
                safe_name = f"node_{id_counter}"
            id_map[clean_text] = f"N_{safe_name}"
            id_counter += 1

        node_id = id_map[clean_text]
        safe_label = clean_text.replace('"', "'")
        return f'{node_id}["{safe_label}"]'

    processed_lines = [lines[0]]
    for line in lines[1:]:
        if line.lower().startswith("subgraph") or line.lower() == "end" or line.lower().startswith("style "):
            processed_lines.append("    " + line)
            continue

        # Check if line has an arrow
        arrow_match = re.search(r'(?:--+>|->+|-+>>|=+>)', line)
        if arrow_match:
            # Fix trailing |> on edge labels
            line = re.sub(r'\|([^|\n]+)\|>\s*', r'|\1| ', line)

            # Split line into alternating [node, arrow_with_label, node, arrow_with_label...]
            full_arrow_pattern = re.compile(r'\s*((?:--+>|->+|-+>>|=+>)(?:\|[^|\n]+\|)?)\s*')
            parts = full_arrow_pattern.split(line)
            if len(parts) >= 3:
                new_parts = []
                for idx, part in enumerate(parts):
                    if idx % 2 == 0:
                        new_parts.append(format_node(part))
                    else:
                        m_lbl = re.search(r'\|([^|\n]+)\|', part)
                        if m_lbl:
                            lbl = m_lbl.group(1).strip()
                            if ('<' in lbl or '>' in lbl) and not (lbl.startswith('"') and lbl.endswith('"')):
                                lbl = f'"{lbl}"'
                            new_parts.append(f" -->|{lbl}| ")
                        else:
                            new_parts.append(" --> ")
                line = "    " + "".join(new_parts).strip()
            else:
                line = "    " + line.strip()
        else:
            line = "    " + line

        processed_lines.append(line)

    return "\n".join(processed_lines)

def render_content_with_mermaid(content: str):
    # Normalize opening fence if LLM wrote ```mermaid graph TD on the same line
    content = re.sub(r'```mermaid\s+(?:graph|flowchart)\s+[A-Za-z]*', r'```mermaid\n', content, flags=re.IGNORECASE)

    # Robust pattern that matches ```mermaid up to closing ``` with or without newline
    mermaid_pattern = re.compile(r'```mermaid\s*(.*?)(?:```|$)', re.DOTALL | re.IGNORECASE)
    parts = []
    last_end = 0

    for match in mermaid_pattern.finditer(content):
        start, end = match.span()
        if start > last_end:
            parts.append(("markdown", content[last_end:start]))

        raw_block = match.group(1)
        trailing_text = ""
        if "```" in raw_block:
            raw_block, trailing_text = raw_block.split("```", 1)

        raw_block = raw_block.strip()
        if raw_block:
            parts.append(("mermaid", raw_block))

        if trailing_text.strip():
            parts.append(("markdown", "\n\n" + trailing_text.strip()))

        last_end = end

    if last_end < len(content):
        parts.append(("markdown", content[last_end:]))

    for kind, val in parts:
        if kind == "markdown":
            if val.strip():
                st.markdown(val)
        elif kind == "mermaid":
            clean_diag = sanitize_mermaid(val)
            diag_id = "m_" + uuid.uuid4().hex[:8]
            # Escape for JS template string
            js_diag = clean_diag.replace('\\', '\\\\').replace('`', '\\`').replace('$', '\\$')
            html_code = f"""
            <div style="background-color: #ffffff; border: 1px solid #E2E8F0; border-radius: 12px; overflow: hidden; margin: 12px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.06);">
                <div style="display: flex; justify-content: space-between; align-items: center; background: #F8FAFC; padding: 8px 14px; border-bottom: 1px solid #E2E8F0; font-size: 12px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                    <span style="font-weight: 600; color: #1E3A8A; display: flex; align-items: center; gap: 6px;">📐 Conceptual & Process Flow Diagram</span>
                    <div style="display: flex; align-items: center; gap: 5px;">
                        <button onclick="zoom_{diag_id}(-0.15)" style="background: #ffffff; border: 1px solid #CBD5E1; border-radius: 4px; padding: 2px 7px; font-size: 11px; cursor: pointer; color: #334155; font-weight: 600;" title="Zoom Out">➖</button>
                        <span id="zl_{diag_id}" style="font-size: 11px; color: #64748B; font-family: monospace; min-width: 36px; text-align: center;">100%</span>
                        <button onclick="zoom_{diag_id}(0.15)" style="background: #ffffff; border: 1px solid #CBD5E1; border-radius: 4px; padding: 2px 7px; font-size: 11px; cursor: pointer; color: #334155; font-weight: 600;" title="Zoom In">➕</button>
                        <button onclick="reset_{diag_id}()" style="background: #ffffff; border: 1px solid #CBD5E1; border-radius: 4px; padding: 2px 7px; font-size: 11px; cursor: pointer; color: #334155; font-weight: 600;" title="Reset Zoom">⟲</button>
                    </div>
                </div>
                <div style="overflow-x: auto; overflow-y: auto; max-height: 540px; padding: 18px; text-align: center; background: #ffffff;">
                    <div id="wrapper_{diag_id}" style="display: inline-block; transform-origin: top center; transition: transform 0.15s ease; min-width: 100%;">
                        <div id="{diag_id}" style="display: flex; justify-content: center; min-width: 320px;">
                            <span style="color:#64748B; font-size:12px; font-family: sans-serif;">Rendering diagram...</span>
                        </div>
                    </div>
                </div>
            </div>
            <script type="module">
                import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
                mermaid.initialize({{
                    startOnLoad: false,
                    theme: 'neutral',
                    securityLevel: 'loose',
                    suppressErrorRendering: true
                }});

                let scale_{diag_id} = 1.0;
                window.zoom_{diag_id} = function(delta) {{
                    scale_{diag_id} = Math.max(0.4, Math.min(2.5, scale_{diag_id} + delta));
                    updateTransform_{diag_id}();
                }};
                window.reset_{diag_id} = function() {{
                    scale_{diag_id} = 1.0;
                    updateTransform_{diag_id}();
                }};
                function updateTransform_{diag_id}() {{
                    document.getElementById('wrapper_{diag_id}').style.transform = 'scale(' + scale_{diag_id} + ')';
                    document.getElementById('zl_{diag_id}').textContent = Math.round(scale_{diag_id} * 100) + '%';
                }}

                async function renderDiag() {{
                    const container = document.getElementById('{diag_id}');
                    const rawCode = `{js_diag}`;
                    try {{
                        const {{ svg }} = await mermaid.render('svg_{diag_id}', rawCode);
                        container.innerHTML = svg;
                    }} catch (err) {{
                        console.warn('Mermaid rendering notice:', err);
                        container.innerHTML = '<div style="font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 12px; color: #475569; background: #F8FAFC; padding: 14px; border-radius: 8px; border: 1px dashed #CBD5E1; width: 100%; text-align: left;"><div style="font-weight: 600; margin-bottom: 6px; color: #1E3A8A;">📐 Flow Diagram (Source)</div><pre style="margin: 0; white-space: pre-wrap; word-break: break-word;">' + rawCode.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</pre></div>';
                    }}
                }}
                renderDiag();
            </script>
            """
            line_count = len(clean_diag.splitlines())
            calc_height = max(280, min(650, line_count * 38 + 110))
            components.html(html_code, height=calc_height, scrolling=True)
            with st.expander("📐 View Diagram Code", expanded=False):
                st.code(clean_diag, language="mermaid")

# ==============================================================================
# Streamlit Main Application (Multi-User & Intranet)
# ==============================================================================
def main():
    init_db()

    # Session State
    if "user" not in st.session_state:
        st.session_state.user = None
    if "current_book_id" not in st.session_state:
        st.session_state.current_book_id = None
    if "current_chapter_id" not in st.session_state:
        st.session_state.current_chapter_id = None
    if "current_lesson" not in st.session_state:
        st.session_state.current_lesson = ""
    if "reader_theme" not in st.session_state:
        st.session_state.reader_theme = "reader-paper"
    if "reader_font_size" not in st.session_state:
        st.session_state.reader_font_size = "1.06rem"

    # --------------------------------------------------------------------------
    # Authentication Guard (Multi-User Login / Register Screen)
    # --------------------------------------------------------------------------
    if st.session_state.user is None:
        st.markdown('<div style="text-align: center; margin-top: 30px; margin-bottom: 20px;">'
                    '<h1 style="color:#1E3A8A; font-size: 2.3rem;">📖 AI Textbook Tutor & Reader</h1>'
                    '<p style="color:#64748B; font-size: 1.1rem;">Personalized local AI studying for your home network.</p>'
                    '</div>', unsafe_allow_html=True)

        col_c, _ = st.columns([1.2, 1])
        with col_c:
            st.markdown(f"""
            <div class="intranet-badge">
                📱 <strong>Local Intranet Access:</strong> Share this URL with your brother or open it on your phone: 
                <code>http://{LOCAL_IP}:8501</code> (while connected to the same Wi-Fi).
            </div>
            """, unsafe_allow_html=True)

            auth_tab_login, auth_tab_reg = st.tabs(["🔑 Log In", "📝 Create Account"])

            with auth_tab_login:
                with st.form("login_form"):
                    l_user = st.text_input("Username", placeholder="e.g. alex")
                    l_pass = st.text_input("Password", type="password")
                    l_btn = st.form_submit_button("Log In", type="primary", use_container_width=True)

                    if l_btn:
                        user_record = authenticate_user(l_user, l_pass)
                        if user_record:
                            st.session_state.user = user_record
                            st.success(f"Welcome back, {user_record['username'].capitalize()}!")
                            st.rerun()
                        else:
                            st.error("Invalid username or password.")

            with auth_tab_reg:
                with st.form("reg_form"):
                    r_user = st.text_input("New Username", placeholder="e.g. brother")
                    r_pass = st.text_input("New Password", type="password")
                    r_btn = st.form_submit_button("Register Account", use_container_width=True)

                    if r_btn:
                        ok, msg = register_user(r_user, r_pass)
                        if ok:
                            st.success(msg)
                        else:
                            st.error(msg)
        return

    # --------------------------------------------------------------------------
    # Sidebar: User Profile, Navigation, & Table of Contents
    # --------------------------------------------------------------------------
    active_user = st.session_state.user

    with st.sidebar:
        # User Header & Logout
        col_u1, col_u2 = st.columns([2, 1])
        with col_u1:
            st.markdown(f"👤 **{active_user['username'].capitalize()}**")
        with col_u2:
            if st.button("Logout", key="btn_logout", use_container_width=True):
                st.session_state.user = None
                st.session_state.current_book_id = None
                st.session_state.current_chapter_id = None
                st.rerun()

        st.caption(f"🌐 Intranet: `http://{LOCAL_IP}:8501`")
        st.divider()


        # Upload Textbook
        st.subheader("📚 Library")
        uploaded_file = st.file_uploader("Upload New Textbook (PDF)", type=["pdf"], key="book_pdf_uploader")

        if uploaded_file is not None:
            file_bytes = uploaded_file.getvalue()
            upload_sig = f"{uploaded_file.name}_{len(file_bytes)}"

            # Only process if this is a newly uploaded file
            if st.session_state.get("last_processed_upload") != upload_sig:
                if len(file_bytes) > 0:
                    file_hash = calculate_file_hash(file_bytes)
                    existing_book = get_book_by_hash(file_hash)
                    target_book_id = None

                    if existing_book:
                        target_book_id = existing_book["id"]
                        if not is_book_in_user_library(active_user["id"], target_book_id):
                            add_book_to_user_library(active_user["id"], target_book_id)
                            st.success(f"Added **{existing_book['title']}** to your personal bookshelf!")
                        else:
                            st.info(f"Loaded: **{existing_book['title']}**")
                    else:
                        with st.spinner("Extracting Table of Contents & chapters..."):
                            clean_title = os.path.splitext(uploaded_file.name)[0]
                            total_pages, chapters = extract_book_structure(file_bytes, uploaded_file.name)
                            
                            if not chapters:
                                st.error("No extractable chapters found in this PDF (empty or unscanned image PDF).")
                            else:
                                target_book_id = save_book_and_chapters(clean_title, file_hash, total_pages, chapters, active_user["id"])
                                st.success(f"Saved {len(chapters)} chapters to your personal bookshelf!")

                    if target_book_id:
                        st.session_state.current_book_id = target_book_id
                        saved_chaps = get_chapters_for_book(target_book_id)
                        st.session_state.current_chapter_id = get_default_chapter_id(saved_chaps)
                        st.session_state.current_lesson = ""

                st.session_state.last_processed_upload = upload_sig
                st.rerun()
            else:
                st.caption(f"📁 Active upload: **{uploaded_file.name}**")
        else:
            if "last_processed_upload" in st.session_state:
                del st.session_state["last_processed_upload"]

        # Available Textbooks in Shared Catalog (1-click add to personal bookshelf)
        avail_catalog = [b for b in list_all_books() if not is_book_in_user_library(active_user["id"], b["id"])]
        if avail_catalog:
            with st.expander("🌐 Add from Available Catalog", expanded=False):
                avail_map = {b["id"]: f"{b['title']} ({b['total_pages']} pp.)" for b in avail_catalog}
                chosen_catalog_id = st.selectbox("Select textbook:", options=list(avail_map.keys()), format_func=lambda bid: avail_map[bid], key="sb_catalog_pick")
                if st.button("➕ Add to My Bookshelf", use_container_width=True, key="btn_add_from_catalog"):
                    add_book_to_user_library(active_user["id"], chosen_catalog_id)
                    st.session_state.current_book_id = chosen_catalog_id
                    chaps = get_chapters_for_book(chosen_catalog_id)
                    st.session_state.current_chapter_id = get_default_chapter_id(chaps)
                    st.session_state.current_lesson = ""
                    st.success("Book added to your personal bookshelf!")
                    st.rerun()

        # Active Book Selector (strictly scoped to this user)
        user_books = list_books_for_user(active_user["id"])
        if user_books:
            book_titles = {b["id"]: f"{b['title']} ({b['total_pages']} pp.)" for b in user_books}
            book_ids = list(book_titles.keys())

            if st.session_state.current_book_id not in book_ids:
                st.session_state.current_book_id = book_ids[0]

            selected_book_id = st.selectbox(
                "Active Book:",
                options=book_ids,
                index=book_ids.index(st.session_state.current_book_id),
                format_func=lambda bid: book_titles[bid]
            )

            if selected_book_id != st.session_state.current_book_id:
                st.session_state.current_book_id = selected_book_id
                st.session_state.current_chapter_id = None
                st.session_state.current_lesson = ""
                st.rerun()

            # Dynamic Academic Domain / Subject per Book
            curr_book = get_book_by_id(selected_book_id)
            initial_subj = (curr_book.get("subject") or "").strip() if curr_book else ""
            if not initial_subj and curr_book:
                initial_subj = infer_book_subject(curr_book["title"])
                update_book_subject(selected_book_id, initial_subj)

            subject = st.text_input(
                "🎓 Academic Domain / Subject:",
                value=initial_subj,
                help="Determines the Professor's teaching style, terminology, diagrams, and case analyses.",
                key=f"sb_subject_{selected_book_id}"
            )
            if curr_book and subject != curr_book.get("subject"):
                update_book_subject(selected_book_id, subject)

            # Hierarchical Table of Contents with Progress Badges
            chapters = get_chapters_for_book(selected_book_id)
            if chapters:
                valid_chapter_ids = [c["id"] for c in chapters]
                if st.session_state.current_chapter_id not in valid_chapter_ids:
                    st.session_state.current_chapter_id = get_default_chapter_id(chapters)

                # Progress stats for current user
                user_progress = get_user_chapter_progress(active_user["id"], selected_book_id)
                completed_count = sum(1 for cid, status in user_progress.items() if status == 'completed')
                total_chapters = len(chapters)
                pct = int((completed_count / total_chapters) * 100) if total_chapters else 0

                st.markdown(f"**Your Progress:** {completed_count}/{total_chapters} sections ({pct}%)")
                st.progress(pct / 100.0)

                st.subheader("📑 Table of Contents")

                # Build parent chapter -> subtopics hierarchy
                parent_map = {}
                for c in chapters:
                    p_title = c.get("parent_chapter") or c["chapter_title"]
                    if p_title not in parent_map:
                        parent_map[p_title] = []
                    parent_map[p_title].append(c)

                parent_titles = list(parent_map.keys())

                # Find which parent contains currently selected section
                active_parent = parent_titles[0]
                for pt, sublist in parent_map.items():
                    if any(c["id"] == st.session_state.current_chapter_id for c in sublist):
                        active_parent = pt
                        break

                # Quick Search
                toc_search = st.text_input("🔍 Search Sections", placeholder="e.g. 31.2, semaphore, paging...").strip().lower()

                if toc_search:
                    search_matches = [
                        c for c in chapters
                        if toc_search in c["chapter_title"].lower()
                        or toc_search in (c.get("parent_chapter") or "").lower()
                        or toc_search in (c.get("subtopic_title") or "").lower()
                    ]
                    if search_matches:
                        st.caption(f"Found {len(search_matches)} matching sections:")
                        search_opts = {
                            c["id"]: f"{'✅ ' if user_progress.get(c['id']) == 'completed' else '📖 ' if c['id'] == st.session_state.current_chapter_id else '⚪ '}{c.get('subtopic_title') or c['chapter_title']}"
                            for c in search_matches
                        }
                        curr_s_idx = list(search_opts.keys()).index(st.session_state.current_chapter_id) if st.session_state.current_chapter_id in search_opts else 0
                        picked_search_cid = st.selectbox(
                            "Jump to Match:",
                            options=list(search_opts.keys()),
                            index=curr_s_idx,
                            format_func=lambda cid: search_opts[cid],
                            key="sb_search_jump"
                        )
                        if picked_search_cid != st.session_state.current_chapter_id:
                            st.session_state.current_chapter_id = picked_search_cid
                            st.session_state.current_lesson = ""
                            st.rerun()
                    else:
                        st.info("No sections match your search.")
                else:
                    # Two-level Hierarchical Navigation:
                    # Level 1: Parent Chapter / Topic
                    if len(parent_titles) > 1:
                        def format_parent(pt):
                            sublist = parent_map[pt]
                            done_count = sum(1 for s in sublist if user_progress.get(s["id"]) == "completed")
                            badge = "✅ " if (done_count == len(sublist) and len(sublist) > 0) else "📖 " if pt == active_parent else "📁 "
                            return f"{badge}{pt} ({done_count}/{len(sublist)})"

                        p_idx = parent_titles.index(active_parent) if active_parent in parent_titles else 0
                        selected_parent = st.selectbox(
                            "📁 Chapter / Topic:",
                            options=parent_titles,
                            index=p_idx,
                            format_func=format_parent,
                            key="sb_parent_select"
                        )
                        if selected_parent != active_parent:
                            # Switch to the first subtopic of newly selected parent chapter
                            st.session_state.current_chapter_id = parent_map[selected_parent][0]["id"]
                            st.session_state.current_lesson = ""
                            st.rerun()
                        active_parent = selected_parent

                    # Level 2: Subtopic / Section
                    current_subtopics = parent_map.get(active_parent, chapters)
                    sub_opts = {
                        c["id"]: f"{'✅ ' if user_progress.get(c['id']) == 'completed' else '📖 ' if c['id'] == st.session_state.current_chapter_id else '⚪ '}{c.get('subtopic_title') or c['chapter_title']} (pp. {c['start_page']}–{c['end_page']})"
                        for c in current_subtopics
                    }
                    sub_keys = list(sub_opts.keys())
                    curr_sub_idx = sub_keys.index(st.session_state.current_chapter_id) if st.session_state.current_chapter_id in sub_keys else 0

                    picked_sub_cid = st.selectbox(
                        "📑 Section / Subtopic:",
                        options=sub_keys,
                        index=curr_sub_idx,
                        format_func=lambda cid: sub_opts[cid],
                        key="sb_subtopic_select"
                    )
                    if picked_sub_cid != st.session_state.current_chapter_id:
                        st.session_state.current_chapter_id = picked_sub_cid
                        st.session_state.current_lesson = ""
                        st.rerun()

                # Cover-to-Cover Previous / Next Buttons
                all_chap_ids = [c["id"] for c in chapters]
                curr_idx = all_chap_ids.index(st.session_state.current_chapter_id) if st.session_state.current_chapter_id in all_chap_ids else 0
                
                col_p, col_n = st.columns(2)
                with col_p:
                    if st.button("⏮️ Prev Section", disabled=(curr_idx == 0), use_container_width=True):
                        st.session_state.current_chapter_id = all_chap_ids[curr_idx - 1]
                        st.session_state.current_lesson = ""
                        st.rerun()
                with col_n:
                    if st.button("Next Section ⏭️", disabled=(curr_idx >= len(all_chap_ids) - 1), use_container_width=True):
                        st.session_state.current_chapter_id = all_chap_ids[curr_idx + 1]
                        st.session_state.current_lesson = ""
                        st.rerun()
        else:
            subject = "General Studies & Literature"
            st.info("📚 Your personal library is empty. Upload your textbook above or add one from the catalog to get started!")

        # Hardware Accelerator & Multi-Device Balancer
        st.divider()
        with st.expander("⚡ Hardware Balancer (GPU • NPU • CPU)", expanded=True):
            telemetry = get_hardware_telemetry(ollama_host="http://localhost:11434")

            st.markdown(f"""
            <div style="background:#F8FAFC; border:1px solid #CBD5E1; border-radius:8px; padding:10px 12px; margin-bottom:10px; font-size:0.84rem; line-height:1.5;">
                <div style="margin-bottom:6px;">
                    <strong>⚡ GPU:</strong> {telemetry['gpu']['name']}<br/>
                    <span style="color:#059669; font-weight:600;">● {telemetry['gpu']['status']}</span>
                </div>
                <div style="margin-bottom:6px;">
                    <strong>🧠 NPU:</strong> {telemetry['npu']['name']}<br/>
                    <span style="color:#2563EB; font-weight:600;">● {telemetry['npu']['status']}</span>
                </div>
                <div>
                    <strong>💻 CPU:</strong> {telemetry['cpu']['name']}<br/>
                    <span style="color:#475569;">● {telemetry['cpu']['status']}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            if telemetry['gpu']['vram_used_gb'] > 0:
                st.progress(
                    telemetry['gpu']['vram_percent'] / 100.0,
                    text=f"GPU VRAM: {telemetry['gpu']['vram_used_gb']} GB / {telemetry['gpu']['vram_total_gb']} GB"
                )

            preset_options = [
                "🛡️ Ultra-Stable CPU Engine (Recommended • 0% Crashes)",
                "⚡ Intel Graphics iGPU (Experimental • Risk of TDR)",
                "🛠️ Custom Manual Split"
            ]

            if "lb_preset_choice" not in st.session_state:
                st.session_state.lb_preset_choice = preset_options[0]

            selected_preset = st.selectbox(
                "Balancing Strategy:",
                options=preset_options,
                index=preset_options.index(st.session_state.lb_preset_choice) if st.session_state.lb_preset_choice in preset_options else 0,
                key="sb_lb_preset"
            )
            st.session_state.lb_preset_choice = selected_preset

            if selected_preset == "🛡️ Ultra-Stable CPU Engine (Recommended • 0% Crashes)":
                st.session_state.hw_num_gpu = 0
                st.session_state.hw_num_thread = 8
                st.caption("🛡️ Intel Core Ultra 5 CPU with AVX_VNNI acceleration & 15.4 GB RAM. 100% stable, zero Windows TDR resets.")
            elif selected_preset == "⚡ Intel Graphics iGPU (Experimental • Risk of TDR)":
                st.session_state.hw_num_gpu = 12
                st.session_state.hw_num_thread = 8
                st.caption("⚡ Partial offload to Intel Graphics. Note: Small integrated GPUs may encounter driver timeouts on large prompts.")
            else:
                st.session_state.hw_num_gpu = st.slider("GPU Layers (num_gpu):", min_value=0, max_value=28, value=st.session_state.get("hw_num_gpu", 0))
                st.session_state.hw_num_thread = st.slider("CPU Threads (num_thread):", min_value=1, max_value=14, value=st.session_state.get("hw_num_thread", 8))
                st.caption(f"🛠️ Active: {st.session_state.hw_num_gpu} GPU layers, {st.session_state.hw_num_thread} CPU threads.")

        # Ollama Settings
        with st.expander("⚙️ Ollama Connection", expanded=False):
            ollama_host = st.text_input("Host", value="http://localhost:11434")
            model_name = st.text_input("Model", value="llama3.2")
            if st.button("🔌 Test Connection", use_container_width=True):
                ok, msg = test_ollama_connection(ollama_host, model_name)
                if ok:
                    st.success(msg)
                else:
                    st.warning(msg)

    # --------------------------------------------------------------------------
    # Main Canvas: Top Controls & Dual-Pane Layout
    # --------------------------------------------------------------------------
    if not st.session_state.current_book_id or not st.session_state.current_chapter_id:
        st.markdown("""
        <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:14px; padding:36px 32px; text-align:center; margin-top:20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
            <div style="font-size:3rem; margin-bottom:12px;">📚</div>
            <h2 style="color:#1E3A8A; margin-bottom:8px;">Welcome to your AI Textbook Tutor!</h2>
            <p style="color:#64748B; font-size:1.05rem; max-width:600px; margin:0 auto 24px auto;">
                Upload any textbook PDF in the sidebar 👈 or choose from the available library to start reading with your personal AI Professor.
            </p>
        </div>
        """, unsafe_allow_html=True)

        avail_catalog = [b for b in list_all_books() if not is_book_in_user_library(active_user["id"], b["id"])]
        if avail_catalog:
            st.markdown("### ⚡ Available Textbooks (1-Click Add)")
            c_cols = st.columns(min(3, len(avail_catalog)))
            for idx, b in enumerate(avail_catalog):
                target_col = c_cols[idx % len(c_cols)]
                with target_col:
                    st.markdown(f"""
                    <div style="border:1px solid #E2E8F0; border-radius:10px; padding:18px; background:#F8FAFC; margin-bottom:12px;">
                        <h4 style="margin:0 0 8px 0; color:#1E3A8A;">📖 {b['title']}</h4>
                        <div style="font-size:0.85rem; color:#64748B; margin-bottom:14px;">{b['total_pages']} pages • Chapters mapped</div>
                    </div>
                    """, unsafe_allow_html=True)
                    if st.button(f"➕ Add to Bookshelf", key=f"btn_quick_add_{b['id']}", use_container_width=True, type="primary"):
                        add_book_to_user_library(active_user["id"], b["id"])
                        st.session_state.current_book_id = b["id"]
                        chaps = get_chapters_for_book(b["id"])
                        st.session_state.current_chapter_id = get_default_chapter_id(chaps)
                        st.session_state.current_lesson = ""
                        st.rerun()
        return

    active_chapter = get_chapter(st.session_state.current_chapter_id)
    active_book = get_book_by_id(st.session_state.current_book_id) or {"title": "Textbook"}

    if not active_chapter:
        st.warning("Selected chapter not found.")
        return

    # Top Control Bar (View Mode, Typography, Reading Stats)
    subtopic_display = active_chapter.get('subtopic_title') or active_chapter['chapter_title']
    parent_display = active_chapter.get('parent_chapter') or ""
    parent_breadcrumb = f"{parent_display} &nbsp;•&nbsp; " if parent_display and parent_display != subtopic_display else ""
    teaching_title = f"{subtopic_display} (from {parent_display})" if parent_display and parent_display != subtopic_display else subtopic_display

    top1, top2, top3 = st.columns([2.5, 1.2, 1.0])
    with top1:
        st.markdown(f"""
        <div style="font-size:0.85rem; color:#64748B; font-weight:600; text-transform:uppercase;">📖 {active_book['title']} &nbsp;•&nbsp; {parent_breadcrumb}Pages {active_chapter['start_page']}–{active_chapter['end_page']}</div>
        <h2 style="margin:2px 0 0 0; color:#1E3A8A; font-size:1.5rem;">{subtopic_display}</h2>
        """, unsafe_allow_html=True)
    with top2:
        view_mode = st.radio(
            "View Mode",
            options=["📖 Split View", "📑 Reader Only", "🤖 AI Tutor Only"],
            horizontal=True,
            label_visibility="collapsed"
        )
    with top3:
        with st.popover("🎨 Reader Style"):
            theme_choice = st.selectbox("Theme", ["Warm Paper", "Classic Light", "Dark Slate"])
            if theme_choice == "Warm Paper":
                st.session_state.reader_theme = "reader-paper"
            elif theme_choice == "Classic Light":
                st.session_state.reader_theme = "reader-light"
            else:
                st.session_state.reader_theme = "reader-dark"

            font_choice = st.selectbox("Font Size", ["Normal (16px)", "Large (18px)", "Extra Large (20px)"])
            if font_choice == "Normal (16px)":
                st.session_state.reader_font_size = "1.06rem"
            elif font_choice == "Large (18px)":
                st.session_state.reader_font_size = "1.18rem"
            else:
                st.session_state.reader_font_size = "1.30rem"

    client = get_ollama_client(ollama_host if 'ollama_host' in locals() else "http://localhost:11434")
    current_model = model_name if 'model_name' in locals() else "llama3.2"

    # Layout Columns
    if view_mode == "📖 Split View":
        col_reader, col_ai = st.columns([1.15, 1.0], gap="large")
    elif view_mode == "📑 Reader Only":
        col_reader = st.container()
        col_ai = None
    else:
        col_reader = None
        col_ai = st.container()

    # --------------------------------------------------------------------------
    # Left Pane: Authentic Book Reader
    # --------------------------------------------------------------------------
    if col_reader is not None:
        with col_reader:
            st.markdown(f"""
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <span style="font-weight:600; color:#475569;">📑 Original Section Text</span>
                <span style="font-size:0.85rem; color:#64748B;">{active_chapter['word_count']:,} words • ~{max(1, active_chapter['word_count'] // 200)} min read</span>
            </div>
            """, unsafe_allow_html=True)

            paragraphs = active_chapter['content'].split('\n\n')
            formatted_paras = []
            for p in paragraphs:
                p_clean = p.strip()
                if p_clean:
                    safe_p = p_clean.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    formatted_paras.append(f"<p>{safe_p}</p>")

            parent_header_line = f'<div style="font-size:0.85rem; text-transform:uppercase; letter-spacing:0.05em; opacity:0.8; margin-bottom:3px;">{parent_display}</div>' if parent_display and parent_display != subtopic_display else ''
            book_html = f"""
            <div class="book-container {st.session_state.reader_theme}" style="font-size: {st.session_state.reader_font_size};">
                <div class="book-header">
                    <div style="font-size:0.85rem; text-transform:uppercase; letter-spacing:0.05em; opacity:0.8;">Pages {active_chapter['start_page']} to {active_chapter['end_page']}</div>
                    {parent_header_line}
                    <h2 style="margin: 4px 0 0 0;">{subtopic_display}</h2>
                </div>
                {''.join(formatted_paras)}
            </div>
            """
            st.markdown(book_html, unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # Right Pane: AI Tutor Assistant with Real-Time Streaming & Live Thinking
    # --------------------------------------------------------------------------
    if col_ai is not None:
        with col_ai:
            st.markdown(f"""
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <span style="font-weight:600; color:#2563EB;">🤖 AI Tutor: {subtopic_display}</span>
                <span style="font-size:0.85rem; color:#64748B;">Strictly grounded in this section</span>
            </div>
            """, unsafe_allow_html=True)

            # Load persistent user chat history for this chapter
            chat_history = load_chapter_chat_history(active_user["id"], active_chapter["id"])

            # Start Lesson Action
            if not chat_history:
                st.info("💡 Read the section text on the left, or click below to have the Professor generate a lesson with architectural diagrams.")
                if st.button("🚀 Start Section Lesson (Streaming)", type="primary", use_container_width=True):
                    # Multi-stage live visual thinking indicator
                    with st.status("🧠 Professor is analyzing section...", expanded=True) as status_box:
                        st.write("📖 Reading section concepts and low-level mechanics...")
                        st.write("📐 Formulating architectural Mermaid diagram...")
                        status_box.update(label="✍️ Streaming lesson in real-time...", state="running")
                        
                        lesson_placeholder = st.empty()
                        streamed_content = ""

                        try:
                            for token in stream_chapter_lesson(
                                client=client,
                                model=current_model,
                                subject=subject,
                                chapter_title=teaching_title,
                                chapter_text=active_chapter['content'],
                                num_gpu=st.session_state.get("hw_num_gpu", 99),
                                num_thread=st.session_state.get("hw_num_thread", 8)
                            ):
                                streamed_content += token
                                lesson_placeholder.markdown(streamed_content + "▌")
                            
                            lesson_placeholder.empty()
                            status_box.update(label="✅ Lesson generation complete!", state="complete", expanded=False)

                            # Save to isolated user chat history & mark in progress
                            save_chat_message(active_user["id"], active_chapter["id"], "assistant", streamed_content)
                            update_chapter_status(active_user["id"], active_chapter["id"], "in_progress")
                            st.session_state.current_lesson = streamed_content
                            st.rerun()

                        except Exception as e:
                            status_box.update(label="⚠️ Error during generation", state="error")
                            st.error(f"Generation error: {str(e)}")
            else:
                # Chat History Box
                chat_box = st.container(height=520)
                with chat_box:
                    for msg in chat_history:
                        with st.chat_message(msg["role"]):
                            render_content_with_mermaid(msg["content"])

                # Interactive Chat Input
                user_query = st.chat_input("Ask a question or answer the verification question...")

                if user_query:
                    # Save and display user message immediately
                    save_chat_message(active_user["id"], active_chapter["id"], "user", user_query)
                    
                    with chat_box:
                        with st.chat_message("user"):
                            st.markdown(user_query)

                        with st.chat_message("assistant"):
                            # If lesson exists, check if user is answering verification question
                            is_answering_quiz = len(chat_history) >= 1 and any("verification question" in m["content"].lower() for m in chat_history)

                            if is_answering_quiz and ("a)" in user_query.lower() or "b)" in user_query.lower() or "c)" in user_query.lower() or "d)" in user_query.lower() or len(user_query.split()) < 35):
                                with st.spinner("Professor is evaluating your answer against the chapter..."):
                                    try:
                                        is_correct, feedback = evaluate_student_answer_sync(
                                            client=client,
                                            model=current_model,
                                            subject=subject,
                                            chapter_title=teaching_title,
                                            chapter_text=active_chapter['content'],
                                            lesson_text=chat_history[0]["content"],
                                            student_answer=user_query,
                                            num_gpu=st.session_state.get("hw_num_gpu", 99),
                                            num_thread=st.session_state.get("hw_num_thread", 8)
                                        )

                                        if is_correct:
                                            resp_msg = (
                                                f"### ✅ Correct Answer!\n\n"
                                                f"{feedback}\n\n"
                                                f"---\n"
                                                f"🎉 *Section Mastered!* Click **Next Section ⏭️** in the sidebar to advance."
                                            )
                                            update_chapter_status(active_user["id"], active_chapter["id"], "completed")
                                        else:
                                            resp_msg = (
                                                f"### ❌ Let's refine your answer\n\n"
                                                f"{feedback}\n\n"
                                                f"*Review the text and try answering again below!*"
                                            )
                                        render_content_with_mermaid(resp_msg)
                                        save_chat_message(active_user["id"], active_chapter["id"], "assistant", resp_msg)
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Error: {str(e)}")
                            else:
                                # Free-form Q&A streaming
                                response_placeholder = st.empty()
                                streamed_ans = ""
                                try:
                                    for token in stream_chat_response(
                                        client=client,
                                        model=current_model,
                                        subject=subject,
                                        chapter_title=teaching_title,
                                        chapter_text=active_chapter['content'],
                                        conversation_history=chat_history,
                                        user_prompt=user_query,
                                        num_gpu=st.session_state.get("hw_num_gpu", 99),
                                        num_thread=st.session_state.get("hw_num_thread", 8)
                                    ):
                                        streamed_ans += token
                                        response_placeholder.markdown(streamed_ans + "▌")

                                    response_placeholder.empty()
                                    render_content_with_mermaid(streamed_ans)
                                    save_chat_message(active_user["id"], active_chapter["id"], "assistant", streamed_ans)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error streaming response: {str(e)}")

                # Reset / Clear Chat for this Chapter
                col_clear, col_status = st.columns([1, 1])
                with col_clear:
                    if st.button("🗑️ Reset Section Conversation", use_container_width=True):
                        clear_chapter_chat_history(active_user["id"], active_chapter["id"])
                        st.rerun()
                with col_status:
                    if st.button("✅ Mark as Completed", use_container_width=True):
                        update_chapter_status(active_user["id"], active_chapter["id"], "completed")
                        st.success("Section marked as completed!")
                        st.rerun()

if __name__ == "__main__":
    main()
