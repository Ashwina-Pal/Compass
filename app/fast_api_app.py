import os
import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Any

from google.adk.runners import InMemoryRunner
from google.genai import types

from app.agent import app as adk_app, generate_achievements
from app.db import get_db_connection, get_setting, set_setting

# Create FastAPI app
app = FastAPI(title="Compass Agent API")

# Phase 1: Custom CORS Middleware - restrict origin to local Vite dashboard (port 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared In-Memory Runner
runner = InMemoryRunner(app=adk_app)

# Request Models
class ChatRequest(BaseModel):
    message: str
    user_id: str = "default"
    session_id: str = "default_session"
    is_resume: bool = False
    interrupt_id: Optional[str] = None

class ChecklistRequest(BaseModel):
    completed_count: int
    total_count: int
    user_id: str = "default"
    date: Optional[str] = None  # YYYY-MM-DD

class TimerRequest(BaseModel):
    duration_minutes: float
    user_id: str = "default"
    date: Optional[str] = None  # YYYY-MM-DD

class SettingsRequest(BaseModel):
    digital_wellbeing_permitted: bool

# Chat Endpoints
@app.post("/chat")
async def chat(request: ChatRequest):
    """Chat endpoint to send messages or resume the workflow after a pause."""
    try:
        try:
            await runner.session_service.create_session(
                app_name=runner.app_name,
                user_id=request.user_id,
                session_id=request.session_id,
            )
        except Exception as e:
            print(f"Session creation note: {e}")
        
        if request.is_resume:
            if not request.interrupt_id:
                raise HTTPException(status_code=400, detail="Missing interrupt_id for resuming.")
            
            # Format message as a function response payload to resume the pause
            new_message = types.Content(
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=request.interrupt_id,
                            name="adk_request_input",
                            response={"result": request.message}
                        )
                    )
                ]
            )
        else:
            new_message = types.Content(parts=[types.Part(text=request.message)])
            
        interrupted = False
        interrupt_id = None
        interrupt_message = None
        final_response = ""
        
        # Run workflow asynchronously
        async for event in runner.run_async(
            user_id=request.user_id,
            session_id=request.session_id,
            new_message=new_message
        ):
            # Check for HITL pause / RequestInput event
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.function_call and part.function_call.name == "adk_request_input":
                        interrupted = True
                        interrupt_id = part.function_call.id
                        interrupt_message = part.function_call.args.get("message") if part.function_call.args else None
            
            # Capture output
            if event.output is not None:
                final_response = str(event.output)
            elif event.content and event.content.parts:
                # Fallback to concatenate text responses if output isn't explicitly set
                for part in event.content.parts:
                    if part.text:
                        final_response += part.text
                        
        return {
            "response": final_response,
            "interrupted": interrupted,
            "interrupt_id": interrupt_id,
            "interrupt_message": interrupt_message
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Checklist Logging
@app.post("/checklist")
async def log_checklist(request: ChecklistRequest):
    """Log a checklist progress tick."""
    date_str = request.date or datetime.date.today().strftime("%Y-%m-%d")
    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                """INSERT OR REPLACE INTO checklist_events (user_id, date, completed_count, total_count)
                   VALUES (?, ?, ?, ?)""",
                (request.user_id, date_str, request.completed_count, request.total_count)
            )
        return {"status": "ok", "message": f"Checklist progress logged for {date_str}."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

# Timer Logging
@app.post("/timer")
async def log_timer(request: TimerRequest):
    """Log focus duration stopwatch session."""
    date_str = request.date or datetime.date.today().strftime("%Y-%m-%d")
    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                """INSERT OR REPLACE INTO timer_events (user_id, date, duration_minutes)
                   VALUES (?, ?, ?)""",
                (request.user_id, date_str, request.duration_minutes)
            )
        return {"status": "ok", "message": f"Focus duration timer logged for {date_str}."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

# Onboarding / Settings Endpoints
@app.get("/settings")
async def get_settings():
    """Retrieve digital wellbeing tracking permission status."""
    val = get_setting("digital_wellbeing_permitted", "1")
    return {"digital_wellbeing_permitted": val == "1"}

@app.post("/settings")
async def update_settings(request: SettingsRequest):
    """Update digital wellbeing tracking permission status."""
    val_str = "1" if request.digital_wellbeing_permitted else "0"
    set_setting("digital_wellbeing_permitted", val_str)
    return {"status": "ok", "digital_wellbeing_permitted": request.digital_wellbeing_permitted}

@app.get("/achievements/{user_id}")
async def get_achievements(user_id: str):
    """Retrieve all achievements for a given user, generating new ones first."""
    try:
        generate_achievements(user_id, source="api")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    conn = get_db_connection()
    try:
        rows = conn.execute(
            """SELECT id, user_id, title, description, category, date_earned, source, icon_key 
               FROM achievements 
               WHERE user_id = ? 
               ORDER BY date_earned DESC""",
            (user_id,)
        ).fetchall()
        
        achievements_list = [dict(row) for row in rows]
        return {
            "has_achievements": len(achievements_list) > 0,
            "achievements": achievements_list
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
