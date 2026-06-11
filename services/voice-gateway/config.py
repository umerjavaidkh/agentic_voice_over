from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Voice-gateway configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env.dev",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Twilio — SIP webhooks, status callbacks, dual-channel recording (section 2)
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""

    # Deepgram — Nova-3 streaming STT (section 4)
    deepgram_api_key: str = ""

    # ElevenLabs — Turbo v2.5 streaming TTS (section 6)
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"
    elevenlabs_model_id: str = "eleven_turbo_v2_5"

    # LiveKit — room API + SIP ingress (sections 2–3)
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    livekit_sip_domain: str = ""

    postgres_dsn: str = Field(
        default="postgresql://devuser:devpass@localhost:5432/voice_agent_dev",
        validation_alias="POSTGRES_DSN",
    )
    redis_url: str = Field(default="redis://localhost:6379", validation_alias="REDIS_URL")

    agent_brain_url: str = Field(
        default="http://agent-brain:8001",
        validation_alias="AGENT_BRAIN_URL",
    )
    business_name: str = Field(default="Your Home Services", validation_alias="BUSINESS_NAME")


settings = Settings()
