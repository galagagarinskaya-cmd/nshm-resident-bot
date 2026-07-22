import sqlite3
from datetime import datetime
from config import DATABASE_PATH
from typing import Optional, Dict, List

class Database:
    def __init__(self, db_path=DATABASE_PATH):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        """Initialize database with required tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                rules_accepted BOOLEAN DEFAULT 0,
                rules_accepted_at TIMESTAMP,
                survey_sent BOOLEAN DEFAULT 0,
                survey_sent_at TIMESTAMP,
                survey_completed BOOLEAN DEFAULT 0,
                survey_completed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Survey responses table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS survey_responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                block_number INTEGER,
                question_index INTEGER,
                question TEXT,
                answer TEXT,
                answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        # User state (for wizard/flow tracking)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_state (
                user_id INTEGER PRIMARY KEY,
                current_state TEXT,
                current_block INTEGER DEFAULT 0,
                data TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        conn.commit()
        conn.close()

    def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user info"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return dict(result) if result else None

    def add_or_update_user(self, user_id: int, username: str = None, first_name: str = None, last_name: str = None):
        """Add or update user"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        existing = self.get_user(user_id)
        if existing:
            cursor.execute("""
                UPDATE users SET username = ?, first_name = ?, last_name = ?
                WHERE user_id = ?
            """, (username, first_name, last_name, user_id))
        else:
            cursor.execute("""
                INSERT INTO users (user_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
            """, (user_id, username, first_name, last_name))

        conn.commit()
        conn.close()

    def accept_rules(self, user_id: int):
        """Mark rules as accepted"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET rules_accepted = 1, rules_accepted_at = ?
            WHERE user_id = ?
        """, (datetime.now(), user_id))
        conn.commit()
        conn.close()

    def reset_rules(self, user_id: int):
        """Reset rules acceptance"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET rules_accepted = 0, rules_accepted_at = NULL
            WHERE user_id = ?
        """, (user_id,))
        conn.commit()
        conn.close()

    def mark_survey_sent(self, user_id: int):
        """Mark survey as sent"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET survey_sent = 1, survey_sent_at = ?
            WHERE user_id = ?
        """, (datetime.now(), user_id))
        conn.commit()
        conn.close()

    def mark_survey_completed(self, user_id: int):
        """Mark survey as completed"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET survey_completed = 1, survey_completed_at = ?
            WHERE user_id = ?
        """, (datetime.now(), user_id))
        conn.commit()
        conn.close()

    def save_survey_response(self, user_id: int, block_number: int, question_index: int, question: str, answer: str):
        """Save survey response"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO survey_responses (user_id, block_number, question_index, question, answer)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, block_number, question_index, question, answer))
        conn.commit()
        conn.close()

    def get_survey_responses(self, user_id: int) -> List[Dict]:
        """Get all survey responses for user"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM survey_responses WHERE user_id = ?
            ORDER BY block_number, answered_at
        """, (user_id,))
        results = cursor.fetchall()
        conn.close()
        return [dict(row) for row in results]

    def get_user_state(self, user_id: int) -> Optional[Dict]:
        """Get user state"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_state WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return dict(result) if result else None

    def set_user_state(self, user_id: int, state: str, block: int = 0, data: str = None):
        """Set user state"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        existing = self.get_user_state(user_id)
        if existing:
            cursor.execute("""
                UPDATE user_state SET current_state = ?, current_block = ?, data = ?, updated_at = ?
                WHERE user_id = ?
            """, (state, block, data, datetime.now(), user_id))
        else:
            cursor.execute("""
                INSERT INTO user_state (user_id, current_state, current_block, data)
                VALUES (?, ?, ?, ?)
            """, (user_id, state, block, data))

        conn.commit()
        conn.close()

    def get_users_for_survey(self) -> List[int]:
        """Get users who need to receive survey"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT user_id FROM users
            WHERE rules_accepted = 1 AND survey_sent = 0
        """)
        results = cursor.fetchall()
        conn.close()
        return [row[0] for row in results]
