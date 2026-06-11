import importlib.util
import sys
from pathlib import Path

VOICE_GATEWAY_DIR = Path(__file__).resolve().parents[3] / "services" / "voice-gateway"


def load_voice_gateway_main():
    vg_path = str(VOICE_GATEWAY_DIR)
    if vg_path not in sys.path:
        sys.path.insert(0, vg_path)

    for mod in ("config", "voice_gateway_config", "voice_gateway_main"):
        sys.modules.pop(mod, None)

    config_spec = importlib.util.spec_from_file_location(
        "voice_gateway_config",
        VOICE_GATEWAY_DIR / "config.py",
    )
    config = importlib.util.module_from_spec(config_spec)
    assert config_spec.loader is not None
    sys.modules["voice_gateway_config"] = config
    sys.modules["config"] = config
    config_spec.loader.exec_module(config)

    main_spec = importlib.util.spec_from_file_location(
        "voice_gateway_main",
        VOICE_GATEWAY_DIR / "main.py",
    )
    main = importlib.util.module_from_spec(main_spec)
    assert main_spec.loader is not None
    sys.modules["voice_gateway_main"] = main
    main_spec.loader.exec_module(main)
    return main
