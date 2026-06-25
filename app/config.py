import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Load workspace environment variables
load_dotenv()

# Force standard Gemini API via Google AI Studio (avoid Vertex AI)
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "False")

@dataclass
class AgentConfig:
    model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    mcp_server_port: int = 8090
    max_iterations: int = 3
    pii_redaction_enabled: bool = True
    injection_detection_enabled: bool = True
    burnout_risk_threshold: float = 0.75   # tune during eval; keep visible

config = AgentConfig()
