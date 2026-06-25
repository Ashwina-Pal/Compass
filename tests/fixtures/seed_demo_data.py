import sqlite3
import datetime
from pathlib import Path
import sys

# Add the project root to sys.path so we can import app modules
sys.path.append(str(Path(__file__).parent.parent.parent))

from app.db import get_db_connection, init_db

def seed_data():
    print("Initializing database schema...")
    init_db()
    
    conn = get_db_connection()
    try:
        with conn:
            # Clear existing data to ensure a fresh, clean run
            print("Clearing existing tables...")
            conn.execute("DELETE FROM checkins")
            conn.execute("DELETE FROM timer_events")
            conn.execute("DELETE FROM checklist_events")
            conn.execute("DELETE FROM chat_events")
            conn.execute("DELETE FROM burnout_scores")
            conn.execute("DELETE FROM archive_rollups")
            
            today = datetime.date.today()
            def get_date(offset):
                return (today - datetime.timedelta(days=offset)).strftime("%Y-%m-%d")

            print("Seeding Persona: Sam (Steady)...")
            # Sam: 45 days of consistent daily check-ins, stable low risk
            for i in range(45):
                date_str = get_date(i)
                # Check-in
                conn.execute(
                    "INSERT INTO checkins (user_id, date, mood_rating, negative_affect, notes) VALUES (?, ?, ?, ?, ?)",
                    ("sam", date_str, 4, 0.1, "Steady progress. Focused on homework.")
                )
                # Timer
                conn.execute(
                    "INSERT INTO timer_events (user_id, date, duration_minutes) VALUES (?, ?, ?)",
                    ("sam", date_str, 60.0)
                )
                # Checklist
                conn.execute(
                    "INSERT INTO checklist_events (user_id, date, completed_count, total_count) VALUES (?, ?, ?, ?)",
                    ("sam", date_str, 5, 5)
                )

            print("Seeding Persona: Bex (Boundary)...")
            # Bex: 10 days of data carefully tuned to land the burnout risk score at exactly 0.75
            # m1 = 1.0 (latest check-in at today-8)
            # m2 = 1.0 (prior 7d focus 100m, last 7d focus 0m)
            # m3 = 0.0 (no check-ins in last 7 days)
            # m4 = 1/3 (checklist completed 1, total 3)
            # Score: 0.35 * 1.0 + 0.30 * 1.0 + 0.20 * 0.0 + 0.15 * (2/3) = 0.75
            
            # Check-ins at offset 8 and 9
            conn.execute(
                "INSERT INTO checkins (user_id, date, mood_rating, negative_affect, notes) VALUES (?, ?, ?, ?, ?)",
                ("bex", get_date(8), 3, 0.2, "Bex checkin 8 days ago.")
            )
            conn.execute(
                "INSERT INTO checkins (user_id, date, mood_rating, negative_affect, notes) VALUES (?, ?, ?, ?, ?)",
                ("bex", get_date(9), 3, 0.2, "Bex checkin 9 days ago.")
            )
            
            # Timer events in prior 7 days (offset 8, 9, 10 summing to 100m)
            conn.execute("INSERT INTO timer_events (user_id, date, duration_minutes) VALUES (?, ?, ?)", ("bex", get_date(8), 30.0))
            conn.execute("INSERT INTO timer_events (user_id, date, duration_minutes) VALUES (?, ?, ?)", ("bex", get_date(9), 40.0))
            conn.execute("INSERT INTO timer_events (user_id, date, duration_minutes) VALUES (?, ?, ?)", ("bex", get_date(10), 30.0))
            # No timer events in last 7 days (offset 0 to 6)
            
            # Checklist events in last 7 days (offset 3)
            conn.execute(
                "INSERT INTO checklist_events (user_id, date, completed_count, total_count) VALUES (?, ?, ?, ?)",
                ("bex", get_date(3), 1, 3)
            )
            # Checklist events in prior 7 days
            conn.execute(
                "INSERT INTO checklist_events (user_id, date, completed_count, total_count) VALUES (?, ?, ?, ?)",
                ("bex", get_date(8), 5, 5)
            )

            print("Seeding Persona: Diego (Decline)...")
            # Diego: 35 days of data, gradual decline crossing 0.75 threshold
            # m1 (streak) = latest check-in at offset 5. missed_days = 4. m1 = 4/7 = 0.5714
            # m2 (decline) = prior 7d focus 315m, last 7d focus 35m. Decline = 280/315 = 0.8888
            # m3 (neg affect) = check-in at offset 5 has neg affect 0.8. m3 = 0.8
            # m4 (checklist) = last 7d checklist 0 completed, 10 total. m4 = 0.0. (1-m4) = 1.0
            # Score: 0.35*0.5714 + 0.30*0.8888 + 0.20*0.8 + 0.15*1.0 = 0.7766 (>0.75)
            
            # Seed Diego's check-ins:
            # Last 7 days check-in (at offset 5)
            conn.execute(
                "INSERT INTO checkins (user_id, date, mood_rating, negative_affect, notes) VALUES (?, ?, ?, ?, ?)",
                ("diego", get_date(5), 2, 0.8, "Extremely overwhelmed, cannot focus at all.")
            )
            # Prior check-ins: daily/every other day from offset 7 to 34
            for i in range(7, 35):
                # Gradually rising negative affect
                neg = 0.1 + (i - 7) * 0.02
                mood = max(1, int(5 - (i - 7) * 0.1))
                conn.execute(
                    "INSERT INTO checkins (user_id, date, mood_rating, negative_affect, notes) VALUES (?, ?, ?, ?, ?)",
                    ("diego", get_date(i), mood, min(neg, 0.7), f"Diego log day {i}")
                )
                
            # Diego's timer events:
            # Last 7 days: 35 minutes at offset 1
            conn.execute("INSERT INTO timer_events (user_id, date, duration_minutes) VALUES (?, ?, ?)", ("diego", get_date(1), 35.0))
            # Prior 7 days (offset 7 to 13): 45m daily (total 315m)
            for i in range(7, 14):
                conn.execute("INSERT INTO timer_events (user_id, date, duration_minutes) VALUES (?, ?, ?)", ("diego", get_date(i), 45.0))
            # Older days (offset 14 to 34): 50m daily
            for i in range(14, 35):
                conn.execute("INSERT INTO timer_events (user_id, date, duration_minutes) VALUES (?, ?, ?)", ("diego", get_date(i), 50.0))
                
            # Diego's checklist events:
            # Last 7 days: 0/10 completed (at offset 2)
            conn.execute(
                "INSERT INTO checklist_events (user_id, date, completed_count, total_count) VALUES (?, ?, ?, ?)",
                ("diego", get_date(2), 0, 10)
            )
            # Prior checklist events
            for i in range(7, 35):
                conn.execute(
                    "INSERT INTO checklist_events (user_id, date, completed_count, total_count) VALUES (?, ?, ?, ?)",
                    ("diego", get_date(i), 4, 4)
                )

            print("Seeding Persona: Casey (Crisis-Independent)...")
            # Casey: 6 days of low-risk indicators, but a single chat message triggers safety gate
            for i in range(6):
                date_str = get_date(i)
                conn.execute(
                    "INSERT INTO checkins (user_id, date, mood_rating, negative_affect, notes) VALUES (?, ?, ?, ?, ?)",
                    ("casey", date_str, 4, 0.1, "Things are fine.")
                )
                conn.execute(
                    "INSERT INTO timer_events (user_id, date, duration_minutes) VALUES (?, ?, ?)",
                    ("casey", date_str, 60.0)
                )
                conn.execute(
                    "INSERT INTO checklist_events (user_id, date, completed_count, total_count) VALUES (?, ?, ?, ?)",
                    ("casey", date_str, 5, 5)
                )
            
            print("Successfully seeded all 4 personas!")
    except Exception as e:
        print(f"Error seeding database: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    seed_data()
