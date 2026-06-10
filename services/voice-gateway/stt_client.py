# services/voice-gateway/stt_client.py

from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveOptions,
    LiveTranscriptionEvents,
)


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
            interim_results=True,  # for barge-in detection
            endpointing=300,  # 300ms silence = utterance end
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
