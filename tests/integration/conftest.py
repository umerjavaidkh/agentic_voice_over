import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_BRAIN_DIR = REPO_ROOT / "services" / "agent-brain"
VOICE_GATEWAY_DIR = REPO_ROOT / "services" / "voice-gateway"

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(AGENT_BRAIN_DIR))
sys.path.insert(0, str(VOICE_GATEWAY_DIR))
