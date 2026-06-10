from config import Settings


def test_settings_instantiates_with_defaults():
    settings = Settings(_env_file=None)
    assert settings.elevenlabs_model_id == "eleven_turbo_v2_5"
    assert settings.elevenlabs_voice_id == "21m00Tcm4TlvDq8ikWAM"
    assert settings.livekit_sip_domain == ""


def test_settings_reads_env_vars(monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACtest")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token-test")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-test")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-test")
    monkeypatch.setenv("LIVEKIT_URL", "wss://lk.example.com")
    monkeypatch.setenv("LIVEKIT_API_KEY", "lk-key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "lk-secret")
    monkeypatch.setenv("LIVEKIT_SIP_DOMAIN", "sip.example.com")

    settings = Settings(_env_file=None)

    assert settings.twilio_account_sid == "ACtest"
    assert settings.twilio_auth_token == "token-test"
    assert settings.deepgram_api_key == "dg-test"
    assert settings.elevenlabs_api_key == "el-test"
    assert settings.livekit_url == "wss://lk.example.com"
    assert settings.livekit_api_key == "lk-key"
    assert settings.livekit_api_secret == "lk-secret"
    assert settings.livekit_sip_domain == "sip.example.com"
