import os
import sqlite3
import datetime
import pytest
from unittest.mock import patch, MagicMock

import app.db
from app.db import get_db_connection, init_db
from app.agent import archivist_node

class MockContext:
    def __init__(self, user_id="test_user"):
        self.user_id = user_id
        self.state = {"chat_event_id": 1}
        self.route = None

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path):
    """Fixture to mock DB_PATH to a temporary database file for each test."""
    test_db = tmp_path / "test_compass.db"
    with patch("app.db.DB_PATH", test_db):
        init_db()
        yield test_db

# ---------------------------------------------------------------------------
# Archivist Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_archivist_chat_update():
    # Insert a placeholder chat event
    conn = get_db_connection()
    with conn:
        conn.execute("INSERT INTO chat_events (id, user_id, message, response) VALUES (?, ?, ?, ?)",
                     (1, "test_user", "Help", ""))
    conn.close()
    
    ctx = MockContext()
    ctx.state["crisis_flag"] = 0
    await archivist_node(ctx, "Coaching response")
    
    # Verify the response is updated in the database
    conn = get_db_connection()
    row = conn.execute("SELECT response, is_crisis FROM chat_events WHERE id = 1").fetchone()
    conn.close()
    
    assert row["response"] == "Coaching response"
    assert row["is_crisis"] == 0

@pytest.mark.asyncio
async def test_archivist_no_archive_needed():
    # Data is 3 days old (<= 7 days)
    today = datetime.date.today()
    three_days_ago = (today - datetime.timedelta(days=3)).strftime("%Y-%m-%d")
    
    conn = get_db_connection()
    with conn:
        conn.execute("INSERT INTO checkins (user_id, date, mood_rating, negative_affect, notes) VALUES (?, ?, ?, ?, ?)",
                     ("test_user", three_days_ago, 4, 0.2, "Checked in"))
        conn.execute("INSERT INTO timer_events (user_id, date, duration_minutes) VALUES (?, ?, ?)",
                     ("test_user", three_days_ago, 3.0))  # Minor entry
    conn.close()
    
    ctx = MockContext()
    await archivist_node(ctx, "Response")
    
    # Verify no details were deleted (both check-in and minor timer remain)
    conn = get_db_connection()
    checkin_count = conn.execute("SELECT COUNT(*) FROM checkins WHERE user_id = 'test_user'").fetchone()[0]
    timer_count = conn.execute("SELECT COUNT(*) FROM timer_events WHERE user_id = 'test_user'").fetchone()[0]
    conn.close()
    
    assert checkin_count == 1
    assert timer_count == 1

@pytest.mark.asyncio
async def test_archivist_prune_minor_entries_gt_7d():
    # Data is 8 days old (> 7 days)
    today = datetime.date.today()
    eight_days_ago = (today - datetime.timedelta(days=8)).strftime("%Y-%m-%d")
    
    conn = get_db_connection()
    with conn:
        # Check-in: should be kept
        conn.execute("INSERT INTO checkins (user_id, date, mood_rating, negative_affect, notes) VALUES (?, ?, ?, ?, ?)",
                     ("test_user", eight_days_ago, 4, 0.2, "Checked in"))
        # Timer event 1: minor (< 5 mins), should be pruned
        conn.execute("INSERT INTO timer_events (user_id, date, duration_minutes) VALUES (?, ?, ?)",
                     ("test_user", eight_days_ago, 3.0))
        # Timer event 2: milestone (>= 5 mins), should be kept
        conn.execute("INSERT INTO timer_events (user_id, date, duration_minutes) VALUES (?, ?, ?)",
                     ("test_user", eight_days_ago, 45.0))
    conn.close()
    
    ctx = MockContext()
    await archivist_node(ctx, "Response")
    
    # Verify minor timer is pruned but others remain
    conn = get_db_connection()
    checkin_count = conn.execute("SELECT COUNT(*) FROM checkins WHERE user_id = 'test_user'").fetchone()[0]
    timer_count = conn.execute("SELECT COUNT(*) FROM timer_events WHERE user_id = 'test_user'").fetchone()[0]
    timer_duration = conn.execute("SELECT duration_minutes FROM timer_events WHERE user_id = 'test_user'").fetchone()[0]
    conn.close()
    
    assert checkin_count == 1
    assert timer_count == 1
    assert timer_duration == 45.0

@pytest.mark.asyncio
async def test_archivist_monthly_rollup_gt_30d():
    # Data is 35 days old (> 30 days)
    today = datetime.date.today()
    thirty_five_days_ago = (today - datetime.timedelta(days=35)).strftime("%Y-%m-%d")
    
    conn = get_db_connection()
    with conn:
        conn.execute("INSERT INTO checkins (user_id, date, mood_rating, negative_affect, notes) VALUES (?, ?, ?, ?, ?)",
                     ("test_user", thirty_five_days_ago, 3, 0.5, "Stressed"))
        conn.execute("INSERT INTO timer_events (user_id, date, duration_minutes) VALUES (?, ?, ?)",
                     ("test_user", thirty_five_days_ago, 30.0))
        conn.execute("INSERT INTO checklist_events (user_id, date, completed_count, total_count) VALUES (?, ?, ?, ?)",
                     ("test_user", thirty_five_days_ago, 2, 5))
    conn.close()
    
    # Mock LLM generation for monthly rollup
    mock_rollup_response = MagicMock()
    mock_rollup_response.text = "Mock rollup: The student felt stressed but maintained focus."
    
    ctx = MockContext()
    with patch("app.agent.generate_rollup_summary", return_value="Mock rollup: The student felt stressed but maintained focus."):
        await archivist_node(ctx, "Response")
        
    # Verify rollup was written to database
    conn = get_db_connection()
    rollup = conn.execute("SELECT summary, rollup_type FROM archive_rollups WHERE user_id = 'test_user'").fetchone()
    
    # Verify raw details older than 30 days were pruned
    checkin_count = conn.execute("SELECT COUNT(*) FROM checkins WHERE user_id = 'test_user'").fetchone()[0]
    timer_count = conn.execute("SELECT COUNT(*) FROM timer_events WHERE user_id = 'test_user'").fetchone()[0]
    checklist_count = conn.execute("SELECT COUNT(*) FROM checklist_events WHERE user_id = 'test_user'").fetchone()[0]
    conn.close()
    
    assert rollup is not None
    assert rollup["summary"] == "Mock rollup: The student felt stressed but maintained focus."
    assert rollup["rollup_type"] == "monthly"
    
    # Details older than 30 days should be deleted
    assert checkin_count == 0
    assert timer_count == 0
    assert checklist_count == 0

@pytest.mark.asyncio
async def test_archivist_partial_pruning():
    # Mix of old (> 30 days) and new (< 30 days) data
    today = datetime.date.today()
    thirty_five_days_ago = (today - datetime.timedelta(days=35)).strftime("%Y-%m-%d")
    two_days_ago = (today - datetime.timedelta(days=2)).strftime("%Y-%m-%d")
    
    conn = get_db_connection()
    with conn:
        # Old data
        conn.execute("INSERT INTO checkins (user_id, date, mood_rating, negative_affect, notes) VALUES (?, ?, ?, ?, ?)",
                     ("test_user", thirty_five_days_ago, 3, 0.5, "Old checkin"))
        # New data
        conn.execute("INSERT INTO checkins (user_id, date, mood_rating, negative_affect, notes) VALUES (?, ?, ?, ?, ?)",
                     ("test_user", two_days_ago, 5, 0.1, "New checkin"))
    conn.close()
    
    mock_rollup_response = MagicMock()
    mock_rollup_response.text = "Mock rollup summary."
    
    ctx = MockContext()
    with patch("app.agent.generate_rollup_summary", return_value="Mock rollup summary."):
        await archivist_node(ctx, "Response")
        
    # Verify old data is deleted, but new data is preserved
    conn = get_db_connection()
    checkins = conn.execute("SELECT notes, date FROM checkins WHERE user_id = 'test_user'").fetchall()
    conn.close()
    
    assert len(checkins) == 1
    assert checkins[0]["notes"] == "New checkin"
    assert checkins[0]["date"] == two_days_ago
