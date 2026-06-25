import os
import sys
import asyncio
import datetime
from pathlib import Path

# Add the project root to sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

# Force standard Gemini API
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "False"

import app.db
from app.db import get_db_connection, init_db
from app.agent import root_agent
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.events import RequestInput
from google.genai import types

async def run_scenario(runner, session_service, user_id, message_text, scenario_name):
    print(f"\n======================================================================")
    print(f"Scenario: {scenario_name}")
    print(f"User: {user_id}")
    print(f"Message: {message_text}")
    print(f"======================================================================")
    
    session = await session_service.create_session(user_id=user_id, app_name="compass")
    message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=message_text)]
    )
    
    events = []
    # Use standard run to collect events
    for event in runner.run(
        new_message=message,
        user_id=user_id,
        session_id=session.id,
        run_config=RunConfig(streaming_mode=StreamingMode.NONE)
    ):
        events.append(event)
        
    print(f"Received {len(events)} events from workflow:")
    for idx, event in enumerate(events):
        print(f"\n--- Event {idx + 1} ---")
        print(f"Event Type: {type(event).__name__}")
        if hasattr(event, "message"):
            print(f"Message/Content: {event.message}")
        if hasattr(event, "content") and event.content:
            text = "".join(part.text for part in event.content.parts if part.text)
            print(f"Content text: {text}")
        if hasattr(event, "interrupt_id"):
            print(f"Interrupt ID: {event.interrupt_id}")

async def main():
    print("Initializing test database...")
    init_db()
    
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("DELETE FROM checkins")
            conn.execute("DELETE FROM timer_events")
            conn.execute("DELETE FROM checklist_events")
            conn.execute("DELETE FROM chat_events")
            conn.execute("DELETE FROM burnout_scores")
            conn.execute("DELETE FROM archive_rollups")
            
            today = datetime.date.today()
            def get_date(offset):
                return (today - datetime.timedelta(days=offset)).strftime("%Y-%m-%d")

            # 1. Setup Low Risk User: sam
            # Check-in today, stable focus, high checklist completion
            conn.execute(
                "INSERT INTO checkins (user_id, date, mood_rating, negative_affect, notes) VALUES (?, ?, ?, ?, ?)",
                ("sam", get_date(0), 4, 0.1, "Feeling okay, studying normal.")
            )
            conn.execute("INSERT INTO timer_events (user_id, date, duration_minutes) VALUES (?, ?, ?)", ("sam", get_date(0), 60.0))
            conn.execute("INSERT INTO timer_events (user_id, date, duration_minutes) VALUES (?, ?, ?)", ("sam", get_date(8), 60.0))
            conn.execute("INSERT INTO checklist_events (user_id, date, completed_count, total_count) VALUES (?, ?, ?, ?)", ("sam", get_date(0), 5, 5))
            
            # 2. Setup High Risk User: bobby
            # No check-ins in last 7 days (last is 10 days ago), focus declined to 0, zero checklist completion
            conn.execute(
                "INSERT INTO checkins (user_id, date, mood_rating, negative_affect, notes) VALUES (?, ?, ?, ?, ?)",
                ("bobby", get_date(10), 1, 0.9, "Stressed out")
            )
            # Prior timer has hours, last 7 days has 0
            conn.execute("INSERT INTO timer_events (user_id, date, duration_minutes) VALUES (?, ?, ?)", ("bobby", get_date(8), 120.0))
            conn.execute("INSERT INTO checklist_events (user_id, date, completed_count, total_count) VALUES (?, ?, ?, ?)", ("bobby", get_date(3), 0, 5))

    finally:
        conn.close()

    session_service = InMemorySessionService()
    runner = Runner(agent=root_agent, session_service=session_service, app_name="compass")

    # Scenario A: Low-Risk User (Standard CBT Coaching)
    await run_scenario(
        runner, 
        session_service, 
        user_id="sam", 
        message_text="I'm feeling a bit stressed about my exams next week. What is a good breathing exercise?", 
        scenario_name="Low Risk - Normal Query"
    )

    # Scenario B: High-Risk User (Safety Gate Escalation / HITL Pause)
    await run_scenario(
        runner, 
        session_service, 
        user_id="bobby", 
        message_text="I have so much work and I don't know what to do.", 
        scenario_name="High Risk - Safety Escalation Trigger"
    )

    # Scenario C: Low-Risk User with Crisis Pattern (Independent Trigger Escalation)
    await run_scenario(
        runner, 
        session_service, 
        user_id="sam", 
        message_text="I feel totally hopeless and want to end my life.", 
        scenario_name="Low Risk - Crisis Keyword Trigger"
    )

if __name__ == "__main__":
    asyncio.run(main())
