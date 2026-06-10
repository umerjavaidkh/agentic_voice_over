import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VOICE_GATEWAY_DIR = REPO_ROOT / "services" / "voice-gateway"
AGENT_BRAIN_DIR = REPO_ROOT / "services" / "agent-brain"
PRICING_SERVICE_DIR = REPO_ROOT / "services" / "pricing-service"
DISPATCH_ADAPTER_DIR = REPO_ROOT / "services" / "dispatch-adapter"

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(AGENT_BRAIN_DIR))
sys.path.insert(0, str(VOICE_GATEWAY_DIR))
sys.path.insert(0, str(PRICING_SERVICE_DIR))
sys.path.insert(0, str(DISPATCH_ADAPTER_DIR))
