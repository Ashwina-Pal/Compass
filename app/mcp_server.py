import sqlite3
import datetime
import json
from mcp.server.fastmcp import FastMCP

from app.db import get_db_connection, get_setting

# Create FastMCP server instance
mcp = FastMCP("compass-mcp")

# Rich local database of evidence-based CBT techniques
CBT_TECHNIQUES = {
    "reframing": (
        "### Cognitive Reframing (CBT)\n"
        "1. Identify the negative automatic thought (e.g., 'I am going to fail this entire class').\n"
        "2. Examine the evidence for and against this thought.\n"
        "3. Reframe the thought into an objective, compassionate alternative (e.g., 'I did poorly on one assignment, "
        "but I have time to improve and seek help')."
    ),
    "breathing": (
        "### Box Breathing\n"
        "1. Inhale slowly through your nose for 4 seconds.\n"
        "2. Hold your breath for 4 seconds.\n"
        "3. Exhale completely through your mouth for 4 seconds.\n"
        "4. Hold empty for 4 seconds.\n"
        "Repeat this cycle 4 times to activate your parasympathetic nervous system."
    ),
    "grounding": (
        "### 5-4-3-2-1 Grounding Technique\n"
        "Anchor your mind to the present space by identifying:\n"
        "- 5 things you can see\n"
        "- 4 things you can touch (physical textures)\n"
        "- 3 things you can hear (distant sounds)\n"
        "- 2 things you can smell\n"
        "- 1 thing you can taste"
    ),
    "relaxation": (
        "### Progressive Muscle Relaxation (PMR)\n"
        "1. Tense a specific muscle group (e.g., shoulders or fists) tight for 5 seconds.\n"
        "2. Release the tension suddenly and feel the muscle relax for 10 seconds.\n"
        "3. Move to the next muscle group (shoulders, arms, jaw, legs).\n"
        "Focus entirely on the difference between tension and relaxation."
    )
}

@mcp.tool()
def log_checkin(mood_rating: int, negative_affect: float, notes: str, user_id: str = "default") -> str:
    """Log a daily check-in recording mood, negative affect levels, and notes.

    Args:
        mood_rating: Numeric mood rating from 1 (very negative) to 5 (very positive).
        negative_affect: Level of stress/negative feelings from 0.0 (none) to 1.0 (extreme).
        notes: Contextual notes or reflections about the day.
        user_id: Unique ID of the student.
    """
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                """INSERT OR REPLACE INTO checkins (user_id, date, mood_rating, negative_affect, notes)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, today_str, mood_rating, negative_affect, notes)
            )
        return f"Check-in successfully logged for {today_str}."
    except Exception as e:
        return f"Error logging check-in: {str(e)}"
    finally:
        conn.close()

@mcp.tool()
def get_burnout_trend(user_id: str = "default") -> str:
    """Retrieve historical burnout risk scores for charts and trend tracking.

    Args:
        user_id: Unique ID of the student.
    """
    # Enforce digital wellbeing consent check at tool layer
    consent = get_setting("digital_wellbeing_permitted", "1")
    if consent != "1":
        return "Access denied: Digital wellbeing tracking is disabled by the user."

    conn = get_db_connection()
    try:
        rows = conn.execute(
            """SELECT date, score, missed_checkin_streak_norm, focus_duration_decline_7d_norm, 
                      negative_affect_freq_norm, checklist_completion_ratio_7d 
               FROM burnout_scores 
               WHERE user_id = ? 
               ORDER BY date ASC""",
            (user_id,)
        ).fetchall()
        if not rows:
            return "No historical burnout data available."
        trend_data = [dict(r) for r in rows]
        return json.dumps(trend_data, indent=2)
    except Exception as e:
        return f"Error retrieving burnout trend: {str(e)}"
    finally:
        conn.close()

@mcp.tool()
def search_coping_technique(query: str) -> str:
    """Search for evidence-grounded CBT coping techniques.

    Args:
        query: Search term (e.g., 'breathing', 'stress', 'grounding', 'reframing').
    """
    query_lower = query.lower()
    
    # Try finding matches in local database
    matches = []
    for key, technique in CBT_TECHNIQUES.items():
        if key in query_lower or query_lower in key:
            matches.append(technique)
            
    if matches:
        return "\n\n".join(matches)
        
    # Return general CBT advice if no specific technique matches
    return (
        "### Cognitive Behavioral Therapy (CBT) Tips\n"
        "Academic stress is normal. When feeling overwhelmed, try to:\n"
        "1. Break large tasks into small, manageable items (checklists).\n"
        "2. Work in focused intervals (e.g., Pomodoro method, 25 minutes on, 5 minutes off).\n"
        "3. Challenge catastrophic thoughts (e.g., 'If I don't finish this tonight, my future is ruined').\n"
        "4. Practice box breathing (inhale 4s, hold 4s, exhale 4s, hold 4s)."
    )

@mcp.tool()
def get_weekly_digest(user_id: str = "default") -> str:
    """Retrieve the latest weekly or monthly summary rollups from memory.

    Args:
        user_id: Unique ID of the student.
    """
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT start_date, end_date, rollup_type, summary FROM archive_rollups WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1",
            (user_id,)
        ).fetchone()
        if not row:
            return "No weekly or monthly digest summary found."
        
        digest = (
            f"### Weekly/Monthly Rollup ({row['rollup_type'].capitalize()})\n"
            f"Period: {row['start_date']} to {row['end_date']}\n\n"
            f"{row['summary']}"
        )
        return digest
    except Exception as e:
        return f"Error retrieving digest: {str(e)}"
    finally:
        conn.close()

if __name__ == "__main__":
    mcp.run()
