# services/voice-gateway/barge_in.py


class CallSession:
    def __init__(self, livekit_track=None):
        self.tts_stream = None  # Current TTS audio stream
        self.is_speaking = False  # Agent currently speaking
        self.livekit_track = livekit_track

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
            if self.livekit_track is not None:
                await self.livekit_track.send_silence()

    async def send_to_agent(self, text: str):
        """Forward final transcript to agent brain. Wired in call flow."""
