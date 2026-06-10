import sys
from pathlib import Path

VOICE_GATEWAY_DIR = Path(__file__).resolve().parents[2] / "services" / "voice-gateway"
sys.path.insert(0, str(VOICE_GATEWAY_DIR))
