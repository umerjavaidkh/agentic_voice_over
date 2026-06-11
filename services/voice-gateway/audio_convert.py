# services/voice-gateway/audio_convert.py

import audioop

TWILIO_MULAW_FRAME = 160  # 20ms @ 8kHz mu-law


def pcm16_16k_to_mulaw_8k(pcm: bytes) -> bytes:
    pcm8k, _ = audioop.ratecv(pcm, 2, 1, 16000, 8000, None)
    return audioop.lin2ulaw(pcm8k, 2)
