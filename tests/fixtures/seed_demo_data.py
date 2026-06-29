import datetime
from app.db import get_db_connection, init_db

def seed_data():
    # Make sure schema is initialized
    init_db()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Clear all tables completely for a fresh clean state
    cursor.execute("DELETE FROM checkins")
    cursor.execute("DELETE FROM timer_events")
    cursor.execute("DELETE FROM checklist_events")
    cursor.execute("DELETE FROM chat_events")
    cursor.execute("DELETE FROM burnout_scores")
    cursor.execute("DELETE FROM archive_rollups")
    
    today = datetime.date.today()
    
    # 1. Seed sam (45 checkins)
    for i in range(45, 0, -1):
        date = (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        cursor.execute(
            "INSERT INTO checkins (user_id, date, mood_rating, negative_affect, notes) VALUES (?, ?, ?, ?, ?)",
            ('sam', date, 4, 0.1, 'Feeling good and balanced.')
        )
        # Also seed some timer and checklist events for sam
        cursor.execute(
            "INSERT INTO timer_events (user_id, date, duration_minutes) VALUES (?, ?, ?)",
            ('sam', date, 60.0)
        )
        cursor.execute(
            "INSERT INTO checklist_events (user_id, date, completed_count, total_count) VALUES (?, ?, ?, ?)",
            ('sam', date, 4, 5)
        )

    # 2. Seed bex (10 checkins)
    # Checked in days 19 to 10 ago (so missed last 9 days) -> m1 = 1.0 (streak >= 7)
    # Prior 7 days had focus time, last 7 days had 0 focus time -> m2 = 1.0 (100% decline)
    # Average negative affect in last 7 days is 0.0 (no checkins in last 7 days) -> m3 = 0.0
    # Checklist completion ratio is 1/3 (completed 1, total 3) -> 1 - m4 = 2/3
    # score = 0.35 * 1.0 + 0.30 * 1.0 + 0.20 * 0.0 + 0.15 * (2/3) = 0.75.
    for i in range(10, 0, -1):
        date = (today - datetime.timedelta(days=i+9)).strftime("%Y-%m-%d")
        cursor.execute(
            "INSERT INTO checkins (user_id, date, mood_rating, negative_affect, notes) VALUES (?, ?, ?, ?, ?)",
            ('bex', date, 3, 0.5, 'Tired but managing.')
        )
        cursor.execute(
            "INSERT INTO timer_events (user_id, date, duration_minutes) VALUES (?, ?, ?)",
            ('bex', date, 60.0)
        )
    # Checklist completion today: completed 1, total 3 (m4 = 1/3)
    cursor.execute(
        "INSERT INTO checklist_events (user_id, date, completed_count, total_count) VALUES (?, ?, ?, ?)",
        ('bex', today.strftime("%Y-%m-%d"), 1, 3)
    )

    # 3. Seed diego (48 checkins)
    for i in range(48, 0, -1):
        date = (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        # Diego is declining: negative affect increases, mood rating decreases
        neg_affect = min(1.0, 0.3 + (48 - i) * 0.015)
        mood = max(1, 4 - (48 - i) // 12)
        # Exclude check-ins in the most recent 4 days to increase missed-checkin streak (m1)
        if i >= 5:
            cursor.execute(
                "INSERT INTO checkins (user_id, date, mood_rating, negative_affect, notes) VALUES (?, ?, ?, ?, ?)",
                ('diego', date, mood, neg_affect, 'Feeling overwhelmed and slipping behind.')
            )
        # Decline in focus hours (95% decline)
        duration = 100.0 if i > 7 else 5.0
        cursor.execute(
            "INSERT INTO timer_events (user_id, date, duration_minutes) VALUES (?, ?, ?)",
            ('diego', date, duration)
        )
        # Low checklist completion in last 7 days (actual logged attempts with 0 completion)
        cursor.execute(
            "INSERT INTO checklist_events (user_id, date, completed_count, total_count) VALUES (?, ?, ?, ?)",
            ('diego', date, 1 if i > 7 else 0, 5)
        )

    # 4. Seed casey (6 checkins)
    for i in range(6, 0, -1):
        date = (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        cursor.execute(
            "INSERT INTO checkins (user_id, date, mood_rating, negative_affect, notes) VALUES (?, ?, ?, ?, ?)",
            ('casey', date, 4, 0.2, 'Doing okay.')
        )
        cursor.execute(
            "INSERT INTO timer_events (user_id, date, duration_minutes) VALUES (?, ?, ?)",
            ('casey', date, 45.0)
        )
        cursor.execute(
            "INSERT INTO checklist_events (user_id, date, completed_count, total_count) VALUES (?, ?, ?, ?)",
            ('casey', date, 4, 5)
        )
        
    conn.commit()
    
    # Print status counts to stdout to verify seeding results
    cursor.execute("SELECT user_id, COUNT(*) FROM checkins GROUP BY user_id")
    rows = cursor.fetchall()
    print("Seed complete. Row counts in checkins table:")
    for row in rows:
        print(f"  {row[0]}: {row[1]} records")
        
    conn.close()

if __name__ == "__main__":
    seed_data()