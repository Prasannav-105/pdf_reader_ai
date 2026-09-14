"""
auth.py: User Authentication & Salted Password Hashing.
Stores registered users securely in SQLite.
"""
import os
import sqlite3
import hashlib
import uuid
from typing import Optional, Dict, Tuple, Any

class AuthManager:
    """Manages user registration, login, and salted SHA-256 authentication."""

    def __init__(self, db_path: str = "./data/study_data.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT UNIQUE NOT NULL,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT DEFAULT '',
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            try:
                conn.execute("ALTER TABLE users ADD COLUMN email TEXT DEFAULT ''")
            except Exception:
                pass
            conn.commit()

    @staticmethod
    def _hash_password(password: str, salt: str) -> str:
        return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()

    def register_user(self, username: str, password: str, email: str = "") -> Tuple[bool, str]:
        """Registers a new user account with salted password hashing."""
        # Handle parameter permutation if email was passed as second argument
        if "@" in password and "@" not in email:
            email, password = password, email

        clean_user = username.strip()
        clean_email = email.strip()
        if len(clean_user) < 3:
            return False, "Username must be at least 3 characters long."
        if len(password) < 4:
            return False, "Password must be at least 4 characters long."

        salt = uuid.uuid4().hex
        pwd_hash = self._hash_password(password, salt)
        user_id = f"user_{uuid.uuid4().hex[:10]}"

        try:
            with self._get_conn() as conn:
                conn.execute("""
                    INSERT INTO users (user_id, username, email, password_hash, salt)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, clean_user, clean_email, pwd_hash, salt))
                conn.commit()
            return True, "Account created successfully! Please log in."
        except sqlite3.IntegrityError:
            return False, "Username already exists. Please choose a different username."
        except Exception as e:
            return False, f"Registration error: {e}"

    def authenticate_user(self, identifier: str, password: str) -> Optional[Dict[str, Any]]:
        """Authenticates a user by username or email. Returns user dict on success, None on failure."""
        clean_id = identifier.strip()
        if not clean_id or not password:
            return None

        with self._get_conn() as conn:
            cur = conn.execute("SELECT * FROM users WHERE username = ? OR email = ?", (clean_id, clean_id))
            row = cur.fetchone()
            if not row:
                return None

            expected_hash = row["password_hash"]
            salt = row["salt"]
            computed_hash = self._hash_password(password, salt)

            if computed_hash == expected_hash:
                return {
                    "user_id": row["user_id"],
                    "username": row["username"],
                    "email": row["email"] if "email" in row.keys() else "",
                    "created_at": row["created_at"]
                }
            return None

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Finds user by username."""
        with self._get_conn() as conn:
            cur = conn.execute("SELECT * FROM users WHERE username = ?", (username.strip(),))
            row = cur.fetchone()
            if row:
                return {
                    "user_id": row["user_id"],
                    "username": row["username"],
                    "email": row["email"] if "email" in row.keys() else "",
                    "created_at": row["created_at"]
                }
            return None
