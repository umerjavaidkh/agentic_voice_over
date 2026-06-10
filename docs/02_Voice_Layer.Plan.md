# 02 — Voice Layer Plan

**Service:** `voice-gateway`  
**Stack:** LiveKit · Deepgram Nova-3 · ElevenLabs Turbo v2.5 · Twilio SIP  
**Critical Metric:** TTFB (time to first audio byte back to caller) < 800ms  

---

## 1. Latency Budget

Every millisecond here is felt by the caller. Budget is strict:

```
Caller speech ends
        │
        ├── Deepgram final transcript emission:     ~200ms
        ├── WebSocket transit to agent brain:        ~20ms
        ├── LangGraph node processing + LLM call:  ~300ms  (streaming)
        ├── First token → ElevenLabs TTS request:   ~50ms
        ├── ElevenLabs first chunk (audio):        ~180ms
        └── Audio delivered to caller:              ~30ms
                                               ─────────
                        TOTAL p50 target:          ~780ms
                        TOTAL p95 target:         <1,200ms
```

**Rules:**
- No synchronous HTTP calls inside the audio path
- All tool calls (pricing, geo) must complete < 100ms or run in parallel
- If LLM streamed response → pipe first sentence to TTS immediately, don't wait for full response

---

## 2. Twilio SIP Configuration

```python
# Twilio TwiML response on incoming call
from twilio.twiml.voice_response import VoiceResponse, Dial, Sip

def handle_incoming(call_sid: str, tenant_id: str) -> str:
    response = VoiceResponse()
    dial = Dial()
    # Route to LiveKit SIP URI
    sip_uri = f"sip:{tenant_id}_{call_sid}@{LIVEKIT_SIP_DOMAIN}"
    dial.sip(sip_uri)
    response.append(dial)
    return str(response)
```

**Twilio webhook endpoints on `voice-gateway`:**
- `POST /call/incoming` — new inbound call, spawn LiveKit room, return TwiML
- `POST /call/status` — call status updates (completed, failed)
- `POST /call/recording` — recording ready webhook

**Twilio config:**
- Phone number → Webhook: `https://api.yourdomain.com/call/incoming`
- Status Callback: `https://api.yourdomain.com/call/status`
- Voice recording: dual-channel (caller + agent separate tracks)

---

## 3. LiveKit Room Management

```python
# services/voice-gateway/room_manager.py

from livekit import api as livekit_api
from livekit.protocol import room as room_proto

class RoomManager:
    def __init__(self, lk_url: str, api_key: str, api_secret: str):
        self.client = livekit_api.LiveKitAPI(lk_url, api_key, api_secret)

    async def create_call_room(self, call_sid: str, tenant_id: str) -> str:
        """Create a LiveKit room for this call. Returns room name."""
        room_name = f"{tenant_id}_{call_sid}"
        await self.client.room.create_room(
            room_proto.CreateRoomRequest(
                name=room_name,
                empty_timeout=300,       # 5 min max call silence
                max_participants=2,      # caller + agent bot
            )
        )
        return room_name

    async def close_room(self, room_name: str):
        await self.client.room.delete_room(
            room_proto.DeleteRoomRequest(name=room_name)
        )
```

**LiveKit SIP participant flow:**
1. `create_call_room()` on Twilio webhook
2. LiveKit SIP trunk accepts Twilio INVITE, adds caller as participant
3. Agent bot joins room as a second participant (publishes TTS audio, subscribes to caller audio)

---

## 4. Deepgram STT Integration

```python
# services/voice-gateway/stt_client.py

import asyncio
import websockets
import json
from deepgram import DeepgramClient, DeepgramClientOptions, LiveOptions

class DeepgramSTT:
    def __init__(self, api_key: str):
        config = DeepgramClientOptions(options={"keepalive": "true"})
        self.client = DeepgramClient(api_key, config)

    async def stream(self, audio_track, on_transcript):
        """
        audio_track: LiveKit audio track from caller
        on_transcript: async callback(text: str, is_final: bool)
        """
        options = LiveOptions(
            model="nova-3",
            language="en-US",
            smart_format=True,
            interim_results=True,          # for barge-in detection
            endpointing=300,               # 300ms silence = utterance end
            utterance_end_ms=1000,
            vad_events=True,
            encoding="linear16",
            sample_rate=16000,
            channels=1,
        )
        connection = self.client.listen.asynclive.v("1")

        async def on_message(self_, result, **kwargs):
            sentence = result.channel.alternatives[0].transcript
            is_final = result.is_final
            if sentence:
                await on_transcript(sentence, is_final)

        connection.on(LiveTranscriptionEvents.Transcript, on_message)
        await connection.start(options)

        # Pipe audio from LiveKit track → Deepgram WebSocket
        async for chunk in audio_track:
            await connection.send(chunk.data)
```

**Deepgram model selection:**
- `nova-3` — best accuracy for conversational, noisy environments
- Enable `smart_format` for number/address normalization ("123 Main" not "one two three main")
- Set `endpointing=300` — 300ms silence triggers end of utterance

---

## 5. Barge-In Handling

Barge-in = caller speaks while agent is talking. Critical for natural conversation.

```python
# services/voice-gateway/call_session.py

class CallSession:
    def __init__(self):
        self.tts_stream = None      # Current TTS audio stream
        self.is_speaking = False    # Agent currently speaking

    async def handle_transcript(self, text: str, is_final: bool):
        # If caller speaks while agent is talking → cancel TTS immediately
        if self.is_speaking and not is_final:
            await self.cancel_tts()

        if is_final and text.strip():
            await self.send_to_agent(text)

    async def cancel_tts(self):
        if self.tts_stream:
            await self.tts_stream.aclose()
            self.tts_stream = None
            self.is_speaking = False
            # Send silence frame to LiveKit to stop audio
            await self.livekit_track.send_silence()
```

---

## 6. ElevenLabs TTS Integration

```python
# services/voice-gateway/tts_client.py

import httpx
from elevenlabs import ElevenLabs, VoiceSettings

class ElevenLabsTTS:
    VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Professional, warm male voice
    MODEL_ID = "eleven_turbo_v2_5"      # Lowest latency model

    def __init__(self, api_key: str):
        self.client = ElevenLabs(api_key=api_key)

    async def stream_to_livekit(self, text: str, lk_audio_track):
        """Stream TTS audio chunks directly into LiveKit track."""
        audio_stream = self.client.text_to_speech.convert_as_stream(
            voice_id=self.VOICE_ID,
            text=text,
            model_id=self.MODEL_ID,
            voice_settings=VoiceSettings(
                stability=0.6,
                similarity_boost=0.85,
                style=0.2,
                use_speaker_boost=True,
            ),
            output_format="pcm_16000",   # Raw PCM, no decode overhead
        )

        async for chunk in audio_stream:
            if chunk:
                await lk_audio_track.write_sample(chunk)
```

**Voice selection criteria:**
- Warm, professional, authoritative — not robotic
- Test with: water heater, HVAC, roofing scripts
- Recommended voices: `Rachel` (female), `Adam` (male), or custom cloned voice for the business

---

## 7. Greeting & Script Templates

```python
# services/voice-gateway/scripts.py

GREETING_TEMPLATE = (
    "Hi! You've reached {business_name}. "
    "I'm an AI assistant and I can help schedule service or get you a quick estimate. "
    "What's the issue you're dealing with today?"
)

CLARIFY_ADDRESS = "Got it. What's the address where you need the service?"

CLARIFY_PROBLEM = "Can you tell me a bit more about what's happening?"

ESTIMATE_RESPONSE = (
    "Based on what you've described, the estimate for {service_type} is typically "
    "between ${min_price} and ${max_price}. "
    "I can get a technician out {time_window}. Does that work for you?"
)

EMERGENCY_RESPONSE = (
    "That sounds urgent. We can have someone at {address} within {eta}. "
    "The estimate is ${min_price}–${max_price}. Shall I book that now?"
)

CONFIRM_BOOKING = (
    "Perfect. I've booked {tech_name} to come to {address} {time_window}. "
    "You'll receive a text confirmation at {phone_number} shortly. "
    "Is there anything else you need?"
)

FALLBACK_CAPTURE = (
    "I'm having a little trouble on my end. "
    "Let me take your name and number and have someone call you right back."
)
```

---

## 8. Audio Pipeline Architecture

```
LiveKit Room
    │
    ├── Caller Track (subscribe) ──► PCM chunks ──► Deepgram WebSocket
    │                                                       │
    │                                             Transcript events
    │                                                       │
    │                                              Agent Brain WS
    │                                                       │
    │                                             Agent text response
    │                                                       │
    └── Bot Track (publish) ◄── PCM chunks ◄── ElevenLabs stream
```

All audio is **PCM 16kHz mono** throughout — no transcoding, no format conversion.

---

## 9. Service Structure

```
services/voice-gateway/
├── main.py               ← FastAPI app, Twilio webhooks
├── room_manager.py       ← LiveKit room lifecycle
├── call_session.py       ← Per-call state machine
├── stt_client.py         ← Deepgram streaming wrapper
├── tts_client.py         ← ElevenLabs streaming wrapper
├── barge_in.py           ← Interrupt detection logic
├── scripts.py            ← Prompt templates
├── config.py             ← Env vars, voice settings
└── requirements.txt
    ├── fastapi
    ├── livekit
    ├── deepgram-sdk
    ├── elevenlabs
    └── twilio
```

---

## 10. Testing Voice Layer

| Test | Method |
|------|--------|
| Latency (TTFB) | Inject test audio, measure time to first PCM output |
| STT accuracy | Run 50 real-world home service phrases through Deepgram |
| Barge-in | Play overlapping audio, confirm TTS cancels |
| Connection failure | Kill Deepgram WS mid-call, verify fallback fires |
| Long silence | Verify 30s silence → agent prompts "Are you still there?" |

---

## Next: [03_Agent_Pipeline.Plan.md](./03_Agent_Pipeline.Plan.md)
