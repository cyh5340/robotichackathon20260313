import os
import io
import time
import wave
import threading
import pyaudio
from smallest import Smallest
from smallest.models import TTSModels, TTSLanguages


class AudioInterface:
    """Handles Speech-to-Text (STT) and Text-to-Speech (TTS) via Smallest.ai."""

    SAMPLE_RATE = 16000
    CHANNELS = 1
    FORMAT = pyaudio.paInt16
    CHUNK = 1024
    SILENCE_THRESHOLD = 500       # RMS amplitude below this = silence
    SILENCE_DURATION = 1.5        # seconds of silence before stopping recording
    MAX_RECORD_SECONDS = 15       # hard cap to avoid runaway recordings

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or os.environ["SMALLEST_API_KEY"]
        self._client = Smallest(api_key=self._api_key)
        self._audio = pyaudio.PyAudio()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def listen(self) -> str:
        """Record from the microphone until silence, then transcribe.

        Returns:
            The transcribed command as a plain string.
        """
        print("[Listener] Listening… (speak your command)")
        audio_bytes = self._record_until_silence()
        print("[Listener] Processing speech…")
        transcript = self._transcribe(audio_bytes)
        print(f"[Listener] Heard: {transcript!r}")
        return transcript

    def speak(self, text: str) -> None:
        """Synthesise *text* with Smallest.ai Waves and play it back.

        Args:
            text: The text to vocalise.
        """
        print(f"[Speaker] → {text!r}")
        audio_bytes = self._synthesise(text)
        self._play_audio(audio_bytes)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _record_until_silence(self) -> bytes:
        """Stream microphone input and stop after sustained silence."""
        stream = self._audio.open(
            format=self.FORMAT,
            channels=self.CHANNELS,
            rate=self.SAMPLE_RATE,
            input=True,
            frames_per_buffer=self.CHUNK,
        )
        frames: list[bytes] = []
        silent_chunks = 0
        silence_limit = int(self.SILENCE_DURATION * self.SAMPLE_RATE / self.CHUNK)
        max_chunks = int(self.MAX_RECORD_SECONDS * self.SAMPLE_RATE / self.CHUNK)

        try:
            for _ in range(max_chunks):
                chunk = stream.read(self.CHUNK, exception_on_overflow=False)
                frames.append(chunk)
                if self._is_silent(chunk):
                    silent_chunks += 1
                    if silent_chunks >= silence_limit and len(frames) > silence_limit:
                        break
                else:
                    silent_chunks = 0
        finally:
            stream.stop_stream()
            stream.close()

        return self._frames_to_wav(frames)

    def _is_silent(self, chunk: bytes) -> bool:
        """Return True when the RMS amplitude of *chunk* is below threshold."""
        import audioop  # stdlib; available wherever pyaudio is installed
        rms = audioop.rms(chunk, 2)  # 2 bytes per sample (paInt16)
        return rms < self.SILENCE_THRESHOLD

    def _frames_to_wav(self, frames: list[bytes]) -> bytes:
        """Encode raw PCM frames as an in-memory WAV file."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(self.CHANNELS)
            wf.setsampwidth(self._audio.get_sample_size(self.FORMAT))
            wf.setframerate(self.SAMPLE_RATE)
            wf.writeframes(b"".join(frames))
        return buf.getvalue()

    def _transcribe(self, wav_bytes: bytes) -> str:
        """Send WAV audio to Smallest.ai STT and return the transcript."""
        audio_file = io.BytesIO(wav_bytes)
        audio_file.name = "recording.wav"
        response = self._client.speech_to_text.transcribe(file=audio_file)
        return response.text.strip()

    def _synthesise(self, text: str) -> bytes:
        """Call Smallest.ai Waves TTS and return raw audio bytes."""
        response = self._client.tts.synthesize(
            text=text,
            model=TTSModels.LIGHTNING,   # Waves Lightning – lowest latency
            language=TTSLanguages.EN,
            voice_id="emily",            # adjust to preferred voice
            sample_rate=24000,
            speed=1.0,
        )
        # SDK returns bytes directly or an object with .audio / .content
        if isinstance(response, (bytes, bytearray)):
            return bytes(response)
        if hasattr(response, "audio"):
            return response.audio
        if hasattr(response, "content"):
            return response.content
        raise ValueError(f"Unexpected TTS response type: {type(response)}")

    def _play_audio(self, audio_bytes: bytes) -> None:
        """Play back audio bytes through the default output device."""
        buf = io.BytesIO(audio_bytes)
        try:
            with wave.open(buf, "rb") as wf:
                stream = self._audio.open(
                    format=self._audio.get_format_from_width(wf.getsampwidth()),
                    channels=wf.getnchannels(),
                    rate=wf.getframerate(),
                    output=True,
                )
                data = wf.readframes(self.CHUNK)
                while data:
                    stream.write(data)
                    data = wf.readframes(self.CHUNK)
                stream.stop_stream()
                stream.close()
        except wave.Error:
            # Fallback: treat as raw PCM at 24 kHz mono 16-bit
            stream = self._audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=24000,
                output=True,
            )
            stream.write(audio_bytes)
            stream.stop_stream()
            stream.close()

    def __del__(self):
        try:
            self._audio.terminate()
        except Exception:
            pass
