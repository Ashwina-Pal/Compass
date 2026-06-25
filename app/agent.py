import os
import sys
import datetime
import json
import re
from typing import Any, AsyncGenerator

from google.adk import Agent, Context, Event, Workflow
from google.adk.apps import App
from google.adk.workflow import START, node
from google.adk.models import Gemini
from google.adk.tools import McpToolset
from google.adk.events import RequestInput
from google.genai import types
from mcp import StdioServerParameters

from app.config import config
from app.db import get_db_connection, get_setting

# ---------------------------------------------------------------------------
# Phase 4 - Security Checkpoint Utilities
# ---------------------------------------------------------------------------
def scrub_pii(text: str) -> str:
    """Scrub PII like emails, phone numbers, and student IDs from text."""
    # Email regex
    text = re.sub(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', '[REDACTED_EMAIL]', text)
    # Phone number regex (flexible national/international formats)
    text = re.sub(r'\+?\d{1,4}?[-.\s]?\(?\d{1,3}?\)?[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}', '[REDACTED_PHONE]', text)
    # Student ID regex (e.g. STU12345 or 8-10 digit numbers)
    text = re.sub(r'\bSTU\d{5,7}\b', '[REDACTED_ID]', text, flags=re.IGNORECASE)
    text = re.sub(r'\b\d{8,10}\b', '[REDACTED_ID]', text)
    return text

def detect_prompt_injection(text: str) -> bool:
    """Detect prompt injection patterns."""
    patterns = [
        r"ignore\s+(?:previous|all)\s+instructions",
        r"reveal\s+(?:your)?\s*system\s+prompt",
        r"you\s+are\s+now",
        r"ignore\s+the\s+rules",
        r"new\s+instruction"
    ]
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False

def write_audit_log(severity: str, event_type: str, details: dict):
    """Write structured JSON audit log to stdout."""
    log_entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "severity": severity,
        "event_type": event_type,
        "details": details
    }
    print(json.dumps(log_entry), flush=True)

# ---------------------------------------------------------------------------
# Node 1: security_checkpoint (Deterministic)
# ---------------------------------------------------------------------------
def security_checkpoint(ctx: Context, node_input: str) -> str:
    """First node. Scrubs PII, detects injections, and checks the consent gate."""
    # 1. PII Scrubbing
    scrubbed = scrub_pii(node_input)
    if scrubbed != node_input:
        write_audit_log("INFO", "pii_redacted", {"original_length": len(node_input), "scrubbed_length": len(scrubbed)})
    
    # 2. Prompt Injection Detection
    if detect_prompt_injection(node_input):
        write_audit_log("CRITICAL", "prompt_injection_detected", {"input": node_input})
        ctx.route = "security_refusal"
        return "I cannot process this request due to security policies."
    
    # 3. Consent Gate Check
    consent_val = get_setting("digital_wellbeing_permitted", "1")
    digital_wellbeing_permitted = (consent_val == "1")
    ctx.state["digital_wellbeing_permitted"] = digital_wellbeing_permitted
    
    write_audit_log("INFO", "security_check_passed", {"user_id": ctx.user_id})
    ctx.route = "normal"
    return scrubbed

# ---------------------------------------------------------------------------
# Node 2: registry_node (Deterministic)
# ---------------------------------------------------------------------------
def calculate_burnout_metrics(user_id: str) -> tuple[float, float, float, float]:
    """Calculate the four normalized metrics from the database."""
    conn = get_db_connection()
    try:
        today = datetime.date.today()
        
        # 1. Missed check-in streak normalization (0.35 weight)
        row = conn.execute(
            "SELECT date FROM checkins WHERE user_id = ? ORDER BY date DESC LIMIT 1",
            (user_id,)
        ).fetchone()
        if not row:
            missed_checkin_streak_norm = 1.0  # Max risk if no check-ins ever
        else:
            latest_checkin = datetime.datetime.strptime(row["date"], "%Y-%m-%d").date()
            # Calculate days since latest checkin, excluding today/yesterday checkin
            missed_days = max(0, (today - latest_checkin).days - 1)
            missed_checkin_streak_norm = min(missed_days / 7.0, 1.0)
            
        # 2. Focus duration decline normalization (0.30 weight)
        date_7d_ago = (today - datetime.timedelta(days=6)).strftime("%Y-%m-%d")
        date_14d_ago = (today - datetime.timedelta(days=13)).strftime("%Y-%m-%d")
        date_8d_ago = (today - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
        
        sum_7d = conn.execute(
            "SELECT SUM(duration_minutes) FROM timer_events WHERE user_id = ? AND date >= ?",
            (user_id, date_7d_ago)
        ).fetchone()[0] or 0.0
        
        sum_prior_7d = conn.execute(
            "SELECT SUM(duration_minutes) FROM timer_events WHERE user_id = ? AND date BETWEEN ? AND ?",
            (user_id, date_14d_ago, date_8d_ago)
        ).fetchone()[0] or 0.0
        
        if sum_prior_7d == 0.0:
            focus_duration_decline_7d_norm = 0.0
        else:
            decline = (sum_prior_7d - sum_7d) / sum_prior_7d
            focus_duration_decline_7d_norm = max(0.0, min(decline, 1.0))
            
        # 3. Negative affect frequency normalization (0.20 weight)
        neg_row = conn.execute(
            "SELECT AVG(negative_affect) FROM checkins WHERE user_id = ? AND date >= ?",
            (user_id, date_7d_ago)
        ).fetchone()
        negative_affect_freq_norm = neg_row[0] if neg_row[0] is not None else 0.0
        
        # 4. Checklist completion ratio 7d (0.15 weight)
        checklist_row = conn.execute(
            "SELECT SUM(completed_count), SUM(total_count) FROM checklist_events WHERE user_id = ? AND date >= ?",
            (user_id, date_7d_ago)
        ).fetchone()
        sum_completed = checklist_row[0] or 0
        sum_total = checklist_row[1] or 0
        if sum_total == 0:
            checklist_completion_ratio_7d = 1.0
        else:
            checklist_completion_ratio_7d = sum_completed / sum_total
            
        return (
            missed_checkin_streak_norm,
            focus_duration_decline_7d_norm,
            negative_affect_freq_norm,
            checklist_completion_ratio_7d
        )
    finally:
        conn.close()

def registry_node(ctx: Context, node_input: str) -> str:
    """Saves user message to db and computes burnout risk score deterministically."""
    # Write empty response placeholder for chat event, to update in archivist_node
    conn = get_db_connection()
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO chat_events (user_id, message, response) VALUES (?, ?, ?)",
                (ctx.user_id, node_input, "")
            )
            ctx.state["chat_event_id"] = cursor.lastrowid
    finally:
        conn.close()
        
    # Calculate burnout risk score
    m1, m2, m3, m4 = calculate_burnout_metrics(ctx.user_id)
    score = 0.35 * m1 + 0.30 * m2 + 0.20 * m3 + 0.15 * (1.0 - m4)
    # Clamp score between 0 and 1
    score = max(0.0, min(score, 1.0))
    
    ctx.state["burnout_risk_score"] = score
    ctx.state["score_inputs"] = {
        "missed_checkin_streak_norm": m1,
        "focus_duration_decline_7d_norm": m2,
        "negative_affect_freq_norm": m3,
        "checklist_completion_ratio_7d": m4
    }
    
    # Save computed score to DB audit trail
    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                """INSERT INTO burnout_scores 
                   (user_id, date, score, missed_checkin_streak_norm, focus_duration_decline_7d_norm, negative_affect_freq_norm, checklist_completion_ratio_7d) 
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (ctx.user_id, datetime.date.today().strftime("%Y-%m-%d"), score, m1, m2, m3, m4)
            )
    finally:
        conn.close()

    # Crisis keyword check (independent trigger)
    crisis_keywords = ["suicide", "end my life", "hopeless", "want to die", "pointless", "no way out", "give up on everything"]
    has_crisis = any(kw in node_input.lower() for kw in crisis_keywords)
    ctx.state["crisis_flag"] = 1 if has_crisis else 0
    
    return node_input

# ---------------------------------------------------------------------------
# Toolsets & MCP wiring
# ---------------------------------------------------------------------------
coaching_toolset = McpToolset(
    connection_params=StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.mcp_server"]
    ),
    tool_filter=["search_coping_technique", "get_weekly_digest"]
)

safety_toolset = McpToolset(
    connection_params=StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.mcp_server"]
    ),
    tool_filter=["get_burnout_trend"]
)

# ---------------------------------------------------------------------------
# Node 3: safety_gate (LlmAgent dynamic manager)
# ---------------------------------------------------------------------------
# Safety gate agent (phrases the warm escalation message)
safety_gate_agent = Agent(
    name="safety_gate_agent",
    model=Gemini(model=config.model),
    instruction=(
        "You are a compassionate student support assistant. A student is showing high levels of burnout "
        "or expressing distress. Your task is to phrase a warm, supportive message to invite them to connect "
        "with a professional counselor or human support. Keep it gentle, reassuring, and invite their response."
    )
)

@node(rerun_on_resume=True)
async def safety_gate(ctx: Context, node_input: str) -> str:
    """Checks the triggers and routes to HITL pause or directly to coaching."""
    score = ctx.state.get("burnout_risk_score", 0.0)
    crisis_flag = ctx.state.get("crisis_flag", 0)
    
    if score >= config.burnout_risk_threshold or crisis_flag:
        # High risk! Call safety agent dynamically to phrase warm escalation
        # Wire safety toolset so the agent has access to burnout trends
        safety_gate_agent.tools = [safety_toolset]
        
        response = await ctx.run_node(safety_gate_agent, node_input)
        # Store message to state for the pause node
        ctx.state["safety_gate_message"] = str(response)
        ctx.route = "hitl_pause"
        return str(response)
    else:
        ctx.route = "no_pause"
        return node_input

# ---------------------------------------------------------------------------
# Node 3.5: human_escalation_pause (HITL RequestInput pause)
# ---------------------------------------------------------------------------
def human_escalation_pause(ctx: Context) -> Any:
    """Deterministic HITL pause node. Yields RequestInput or reads resumed input."""
    interrupt_id = "safety_gate_hitl"
    if interrupt_id in ctx.resume_inputs:
        user_response = ctx.resume_inputs[interrupt_id]
        ctx.state["safety_gate_response"] = user_response
        return f"User response received: {user_response}"
        
    message = ctx.state.get(
        "safety_gate_message", 
        "Compass is concerned about your burnout level. Would you like us to connect you with a student support counselor?"
    )
    return RequestInput(
        interrupt_id=interrupt_id,
        message=message
    )

# ---------------------------------------------------------------------------
# Node 4: coaching_agent (LlmAgent CBT coaching)
# ---------------------------------------------------------------------------
coaching_agent = Agent(
    name="coaching_agent",
    model=Gemini(model=config.model),
    instruction=(
        "You are Compass, a warm student wellness coach specializing in evidence-based CBT coaching. "
        "Your goal is to help students reframe academic stress and practice self-care. Use the search_coping_technique tool "
        "to pull appropriate techniques (like box breathing or grounding) to suggest. Use get_weekly_digest to recall "
        "past summaries if requested. Keep your responses warm, structured, and focused on self-compassion. "
        "Limit clinical claims—you suggest coping strategies, never diagnose."
    ),
    tools=[coaching_toolset]
)

# ---------------------------------------------------------------------------
# Node 5: archivist_node (Deterministic)
# ---------------------------------------------------------------------------
# Helper for the archivist LLM monthly rollup
async def generate_rollup_summary(history_text: str) -> str:
    """Generate a monthly rollup summary using the standard GenAI Client."""
    from google.genai import Client
    client = Client()
    prompt = (
        f"Summarize the student's wellness check-ins over the past month. Highlight general patterns "
        f"and areas of growth or persistent stress. Keep the summary under 150 words.\n\n"
        f"Checkin details:\n{history_text}"
    )
    response = await client.aio.models.generate_content(
        model=config.model,
        contents=prompt
    )
    return str(response.text)

async def archivist_node(ctx: Context, node_input: str) -> str:
    """Updates chat logs, and handles SQLite database cleanup and monthly rollups."""
    # 1. Update the chat response in database
    chat_event_id = ctx.state.get("chat_event_id")
    if chat_event_id:
        conn = get_db_connection()
        try:
            with conn:
                conn.execute(
                    "UPDATE chat_events SET response = ?, is_crisis = ? WHERE id = ?",
                    (node_input, ctx.state.get("crisis_flag", 0), chat_event_id)
                )
        finally:
            conn.close()

    # 2. Database archive/rollup logic
    conn = get_db_connection()
    try:
        today = datetime.date.today()
        # Find oldest entry date
        cursor = conn.execute("SELECT MIN(date) FROM checkins WHERE user_id = ?", (ctx.user_id,))
        oldest_date_str = cursor.fetchone()[0]
        
        if oldest_date_str:
            oldest_date = datetime.datetime.strptime(oldest_date_str, "%Y-%m-%d").date()
            age_days = (today - oldest_date).days
            
            # Prune and rollup if oldest data is > 30 days
            if age_days > 30:
                limit_date = (today - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
                
                # --- FIX: Fetch ALL historical check-ins to provide full month context to the LLM ---
                all_rows = conn.execute(
                    "SELECT mood_rating, negative_affect, notes, date FROM checkins WHERE user_id = ? ORDER BY date ASC",
                    (ctx.user_id,)
                ).fetchall()
                
                if all_rows:
                    history_summary = []
                    for r in all_rows:
                        history_summary.append(f"Date: {r['date']}, Mood: {r['mood_rating']}/5, Notes: {r['notes']}")
                    history_text = "\n".join(history_summary)
                    
                    # Generate rollup summary via helper using the comprehensive history
                    rollup_text = await generate_rollup_summary(history_text)
                    
                    # Store rollup tracking the actual pruned window bounds
                    start_date = oldest_date_str
                    end_date = limit_date
                    with conn:
                        conn.execute(
                            """INSERT INTO archive_rollups (user_id, start_date, end_date, rollup_type, summary)
                               VALUES (?, ?, ?, ?, ?)""",
                            (ctx.user_id, start_date, end_date, "monthly", rollup_text)
                        )
                        # --- Keep Pruning Strict: Only delete details older than 30 days ---
                        conn.execute("DELETE FROM checkins WHERE user_id = ? AND date < ?", (ctx.user_id, limit_date))
                        conn.execute("DELETE FROM timer_events WHERE user_id = ? AND date < ?", (ctx.user_id, limit_date))
                        conn.execute("DELETE FROM checklist_events WHERE user_id = ? AND date < ?", (ctx.user_id, limit_date))
            
            # Pruning minor entries > 7 days
            limit_7d_date = (today - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
            with conn:
                conn.execute(
                    "DELETE FROM timer_events WHERE user_id = ? AND date < ? AND duration_minutes < 5.0",
                    (ctx.user_id, limit_7d_date)
                )
    finally:
        conn.close()

    return node_input

# ---------------------------------------------------------------------------
# Deterministic Security Refusal Node
# ---------------------------------------------------------------------------
def security_refusal_node(ctx: Context, node_input: str) -> str:
    """Refusal terminal node when prompt injection is flagged."""
    return "I cannot process this request due to security policies."

# Toolsets defined above

# ---------------------------------------------------------------------------
# Compile the Workflow Graph
# ---------------------------------------------------------------------------
workflow = Workflow(
    name="compass_workflow",
    edges=[
        (START, security_checkpoint),
        (security_checkpoint, {
            "normal": registry_node,
            "security_refusal": security_refusal_node
        }),
        (registry_node, safety_gate),
        (safety_gate, {
            "hitl_pause": human_escalation_pause,
            "no_pause": coaching_agent
        }),
        (human_escalation_pause, coaching_agent),
        (coaching_agent, archivist_node),
    ]
)

root_agent = workflow

app = App(
    name="compass-coach",
    root_agent=workflow
)
