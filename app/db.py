import sqlite3
import os
import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "compass.db"

def get_db_connection():
    """Get a database connection, enforcing WAL journal mode."""
    # Ensure parent directory exists (just in case)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    
    # Enable WAL mode immediately on connection to prevent 'database is locked' errors
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    """Initialize database tables if they do not exist."""
    conn = get_db_connection()
    try:
        with conn:
            # 1. User Settings (durable preferences like consent)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            
            # 2. Check-ins
            conn.execute("""
                CREATE TABLE IF NOT EXISTS checkins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    date TEXT NOT NULL,  -- YYYY-MM-DD
                    mood_rating INTEGER, -- 1-5
                    negative_affect REAL, -- 0.0 to 1.0 (frequency/intensity of negative feelings)
                    notes TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 3. Focus Timer/Stopwatch Events
            conn.execute("""
                CREATE TABLE IF NOT EXISTS timer_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    date TEXT NOT NULL,  -- YYYY-MM-DD
                    duration_minutes REAL NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 4. Checklist Events
            conn.execute("""
                CREATE TABLE IF NOT EXISTS checklist_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    date TEXT NOT NULL,  -- YYYY-MM-DD
                    completed_count INTEGER NOT NULL,
                    total_count INTEGER NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 5. Chat History / Journals
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    message TEXT NOT NULL,
                    response TEXT NOT NULL,
                    is_crisis INTEGER DEFAULT 0,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 6. Burnout Scores (historical audit trail)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS burnout_scores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    date TEXT NOT NULL, -- YYYY-MM-DD
                    score REAL NOT NULL,
                    missed_checkin_streak_norm REAL NOT NULL,
                    focus_duration_decline_7d_norm REAL NOT NULL,
                    negative_affect_freq_norm REAL NOT NULL,
                    checklist_completion_ratio_7d REAL NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 7. Archive Rollups (weeks/months summaries)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS archive_rollups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    start_date TEXT NOT NULL, -- YYYY-MM-DD
                    end_date TEXT NOT NULL,   -- YYYY-MM-DD
                    rollup_type TEXT NOT NULL, -- 'weekly' or 'monthly'
                    summary TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 8. Achievements
            conn.execute("""
                CREATE TABLE IF NOT EXISTS achievements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    category TEXT NOT NULL,
                    date_earned TEXT NOT NULL,  -- YYYY-MM-DD
                    source TEXT NOT NULL,
                    icon_key TEXT NOT NULL,
                    UNIQUE(user_id, title, date_earned)
                )
            """)
            
            # Set default digital_wellbeing_permitted to '1' (True) if not set
            cursor = conn.execute("SELECT value FROM user_settings WHERE key = 'digital_wellbeing_permitted'")
            if cursor.fetchone() is None:
                conn.execute(
                    "INSERT INTO user_settings (key, value) VALUES ('digital_wellbeing_permitted', '1')"
                )
    finally:
        conn.close()

def get_setting(key: str, default: str = None) -> str:
    """Retrieve a durable setting value."""
    conn = get_db_connection()
    try:
        row = conn.execute("SELECT value FROM user_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()

def set_setting(key: str, value: str):
    """Write or update a durable setting."""
    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO user_settings (key, value) VALUES (?, ?)",
                (key, str(value))
            )
    finally:
        conn.close()

# Initialize when imported
init_db()
