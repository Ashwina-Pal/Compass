import os
import sys
import asyncio
import sqlite3
from pathlib import Path

# Add the project root to sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

# Force standard Gemini API
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "False"

from tests.fixtures.seed_demo_data import seed_data
from app.db import get_db_connection
from app.agent import root_agent
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.events import RequestInput
from google.genai import types

async def main():
    print("Step 1: Seeding database with all personas...")
    seed_data()
    
    session_service = InMemorySessionService()
    runner = Runner(agent=root_agent, session_service=session_service, app_name="compass")
    user_id = "diego"
    
    print("\nStep 2: Starting workflow run for Diego...")
    session = await session_service.create_session(user_id=user_id, app_name="compass")
    message = types.Content(
        role="user",
        parts=[types.Part.from_text(text="I'm feeling very overwhelmed with my classes and I can't keep up.")]
    )
    
    # Run the workflow. Since Diego's score is 0.77, it should yield an escalation pause.
    events = list(runner.run(
        new_message=message,
        user_id=user_id,
        session_id=session.id,
        run_config=RunConfig(streaming_mode=StreamingMode.NONE)
    ))
    
    print(f"Workflow run yielded {len(events)} events.")
    
    pause_func_call = None
    for idx, event in enumerate(events):
        print(f"Event {idx+1}: type={type(event).__name__}")
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    print(f"  Text: {part.text[:100]}...")
                if part.function_call:
                    print(f"  Function Call: {part.function_call.name}")
                    if part.function_call.name == "adk_request_input":
                        pause_func_call = part.function_call
                        
    if not pause_func_call:
        print("Error: Safety gate did not pause for Diego as expected!")
        return
        
    print("\n>>> Safety Gate Interrupted and Paused successfully! <<<")
    message_arg = pause_func_call.args.get("message")
    print(f"Escalation message from Safety Gate:\n{message_arg}")
    
    print("\nStep 3: Resuming workflow run (simulating counselor intervention)...")
    # Resume the workflow by supplying the resume input via a FunctionResponse part
    resume_message = types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    name="adk_request_input",
                    id="safety_gate_hitl",
                    response={"response": "Approved. Connect Diego with counselor."}
                )
            )
        ]
    )
    
    resume_events = list(runner.run(
        new_message=resume_message,
        user_id=user_id,
        session_id=session.id,
        run_config=RunConfig(streaming_mode=StreamingMode.NONE)
    ))
    
    print(f"Workflow resumed. Yielded {len(resume_events)} events.")
    for idx, event in enumerate(resume_events):
        print(f"Resume Event {idx+1}: type={type(event).__name__}")
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    print(f"  Text: {part.text[:150]}...")
    
    print("\nStep 4: Querying database to fetch the generated monthly rollup summary...")
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT start_date, end_date, summary FROM archive_rollups WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,)
        ).fetchone()
        
        if row:
            print(f"\n=======================================================")
            print(f"Monthly Rollup Summary for {user_id.upper()}")
            print(f"Period: {row['start_date']} to {row['end_date']}")
            print(f"=======================================================")
            print(row['summary'])
            print(f"=======================================================")
        else:
            print("Error: No archive rollup found in the database!")
    finally:
        conn.close()

if __name__ == "__main__":
    asyncio.run(main())
