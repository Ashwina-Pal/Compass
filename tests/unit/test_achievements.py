import datetime
import pytest
from unittest.mock import patch

from app.db import get_db_connection, init_db
from app.agent import generate_achievements, archivist_node

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

def test_generate_achievements_empty():
    ach = generate_achievements("test_user")
    assert len(ach) == 0

def test_focus_streak_earned_and_disqualified():
    today = datetime.date.today()
    conn = get_db_connection()
    
    # 1. Disqualified case: 300+ minutes of focus, but only 4 check-in days
    with conn:
        for i in range(4):
            date_str = (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
            conn.execute("INSERT INTO checkins (user_id, date, mood_rating) VALUES (?, ?, ?)",
                         ("test_user", date_str, 4))
            conn.execute("INSERT INTO timer_events (user_id, date, duration_minutes) VALUES (?, ?, ?)",
                         ("test_user", date_str, 80.0)) # 80 * 4 = 320 minutes (> 300)
    
    ach = generate_achievements("test_user")
    # Verify no achievements since check-ins are < 5 days
    assert not any(a["title"] == "Focus streak" for a in ach)
    
    # 2. Qualified case: add the 5th check-in day
    with conn:
        date_str = (today - datetime.timedelta(days=4)).strftime("%Y-%m-%d")
        conn.execute("INSERT INTO checkins (user_id, date, mood_rating) VALUES (?, ?, ?)",
                     ("test_user", date_str, 4))
                     
    ach = generate_achievements("test_user")
    # Verify "Focus streak" is now earned
    assert any(a["title"] == "Focus streak" for a in ach)

def test_consistency_badge_earned_and_disqualified():
    today = datetime.date.today()
    conn = get_db_connection()
    
    # 1. Disqualified case: completion ratio = 70% (< 80%)
    with conn:
        for i in range(7):
            date_str = (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
            conn.execute(
                "INSERT INTO checklist_events (user_id, date, completed_count, total_count) VALUES (?, ?, ?, ?)",
                ("test_user", date_str, 7, 10)
            )
            
    ach = generate_achievements("test_user")
    assert not any(a["title"] == "Consistency badge" for a in ach)
    
    # Clear checklist events to isolate the next test
    with conn:
        conn.execute("DELETE FROM checklist_events")
        
    # 2. Qualified case: completion ratio = 80%
    with conn:
        for i in range(7):
            date_str = (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
            conn.execute(
                "INSERT INTO checklist_events (user_id, date, completed_count, total_count) VALUES (?, ?, ?, ?)",
                ("test_user", date_str, 8, 10)
            )
            
    ach = generate_achievements("test_user")
    assert any(a["title"] == "Consistency badge" for a in ach)

def test_monthly_momentum_earned():
    today = datetime.date.today()
    conn = get_db_connection()
    
    # We want to satisfy either criteria in 3 distinct weeks
    # Let's use the checklist completion criteria in Week 1, Week 2, and Week 3
    # Week 1: [today-6, today]
    # Week 2: [today-13, today-7]
    # Week 3: [today-20, today-14]
    with conn:
        # Week 1 checklist data (8/10 completed per day)
        for i in range(7):
            date_str = (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
            conn.execute(
                "INSERT INTO checklist_events (user_id, date, completed_count, total_count) VALUES (?, ?, ?, ?)",
                ("test_user", date_str, 8, 10)
            )
        # Week 2 checklist data (8/10 completed per day)
        for i in range(7, 14):
            date_str = (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
            conn.execute(
                "INSERT INTO checklist_events (user_id, date, completed_count, total_count) VALUES (?, ?, ?, ?)",
                ("test_user", date_str, 8, 10)
            )
        # Week 3 checklist data (8/10 completed per day)
        for i in range(14, 21):
            date_str = (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
            conn.execute(
                "INSERT INTO checklist_events (user_id, date, completed_count, total_count) VALUES (?, ?, ?, ?)",
                ("test_user", date_str, 8, 10)
            )
            
    ach = generate_achievements("test_user")
    assert any(a["title"] == "Monthly momentum" for a in ach)

def test_achievements_unique_constraint():
    today = datetime.date.today()
    conn = get_db_connection()
    
    # Fill in checklist data for consistency badge
    with conn:
        for i in range(7):
            date_str = (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
            conn.execute(
                "INSERT INTO checklist_events (user_id, date, completed_count, total_count) VALUES (?, ?, ?, ?)",
                ("test_user", date_str, 9, 10)
            )
            
    # Run once
    ach1 = generate_achievements("test_user")
    assert len(ach1) > 0
    
    # Run again on the same day - duplicate rows should be avoided by UNIQUE / INSERT OR IGNORE
    ach2 = generate_achievements("test_user")
    
    # Check physical rows in database
    db_ach = conn.execute("SELECT title, date_earned FROM achievements WHERE user_id = 'test_user'").fetchall()
    pairs = [(row["title"], row["date_earned"]) for row in db_ach]
    
    # Ensure there are no duplicate entries for the same title/date
    assert len(pairs) == len(set(pairs))

@pytest.mark.asyncio
async def test_archivist_node_triggers_achievements():
    today = datetime.date.today()
    # Trigger a rollup by adding data that is 31 days old
    old_date_str = (today - datetime.timedelta(days=31)).strftime("%Y-%m-%d")
    
    conn = get_db_connection()
    with conn:
        # Check-in that makes the history older than 30 days
        conn.execute("INSERT INTO checkins (user_id, date, mood_rating) VALUES (?, ?, ?)",
                     ("test_user", old_date_str, 3))
                     
        # Add 7 days of checklist completions to trigger a "Consistency badge" and also "Monthly momentum"
        # We satisfy Week 1, 2, and 3 to ensure achievements are found
        for i in range(21):
            date_str = (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
            conn.execute(
                "INSERT INTO checklist_events (user_id, date, completed_count, total_count) VALUES (?, ?, ?, ?)",
                ("test_user", date_str, 9, 10)
            )
    
    ctx = MockContext()
    
    # Mock generate_rollup_summary to bypass standard LLM call
    with patch("app.agent.generate_rollup_summary", return_value="Rollup Summary"):
        await archivist_node(ctx, "Dummy response")
        
    # Check that achievements were generated and inserted
    ach_rows = conn.execute("SELECT * FROM achievements WHERE user_id = 'test_user'").fetchall()
    assert len(ach_rows) > 0
    assert any(row["source"] == "rollup" for row in ach_rows)

def test_streak_achievement_single_entry_consecutive_days():
    """Asserts that N consecutive days of qualifying data only produces 1 streak achievement, not N."""
    today = datetime.date.today()
    conn = get_db_connection()
    
    # Consistent for 15 days, which means a continuous focus streak
    with conn:
        for i in range(15):
            date_str = (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
            conn.execute("INSERT INTO checkins (user_id, date, mood_rating) VALUES (?, ?, ?)",
                         ("test_user", date_str, 4))
            conn.execute("INSERT INTO timer_events (user_id, date, duration_minutes) VALUES (?, ?, ?)",
                         ("test_user", date_str, 60.0))  # 60 mins/day * 7 days = 420 mins (> 300)
                         
    ach = generate_achievements("test_user")
    focus_streaks = [a for a in ach if a["title"] == "Focus streak"]
    
    # Under old logic, this would be 9 focus streak entries (from days 6 to 14).
    # Under new logic, this should be exactly 1 focus streak achievement at the start of the qualifying period.
    assert len(focus_streaks) == 1

def test_get_achievements_api_route():
    """Tests the GET /achievements/{user_id} endpoint, verifying generation and retrieval."""
    from fastapi.testclient import TestClient
    from app.fast_api_app import app
    
    today = datetime.date.today()
    conn = get_db_connection()
    
    # Seed data for api_test_user to earn a Focus streak achievement
    with conn:
        for i in range(7):
            date_str = (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
            conn.execute("INSERT INTO checkins (user_id, date, mood_rating) VALUES (?, ?, ?)",
                         ("api_test_user", date_str, 4))
            conn.execute("INSERT INTO timer_events (user_id, date, duration_minutes) VALUES (?, ?, ?)",
                         ("api_test_user", date_str, 60.0))
                         
    client = TestClient(app)
    response = client.get("/achievements/api_test_user")
    assert response.status_code == 200
    
    data = response.json()
    assert data["has_achievements"] is True
    assert len(data["achievements"]) > 0
    assert data["achievements"][0]["title"] == "Focus streak"
    assert data["achievements"][0]["user_id"] == "api_test_user"


