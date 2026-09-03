import whisper
import asyncio
import logging
from pathlib import Path
from config import settings
from models.schemas import TranscriptSegment

logger = logging.getLogger(__name__)


class Transcriber:
    _model = None  # lazy load — do not load at import time

    def _load_model(self):
        if self._model is None:
            logger.info(f"Loading Whisper model: {settings.WHISPER_MODEL}")
            self._model = whisper.load_model(settings.WHISPER_MODEL)
        return self._model

    def _transcribe_sync(self, file_path: str) -> dict:
        model = self._load_model()
        return model.transcribe(file_path)

    async def transcribe(self, file_path: str) -> tuple[str, list[TranscriptSegment]]:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._transcribe_sync, file_path)

        full_text = result["text"].strip()

        segments = [
            TranscriptSegment(
                start=seg["start"],
                end=seg["end"],
                text=seg["text"],
            )
            for seg in result["segments"]
        ]

        logger.info(f"Transcribed {len(full_text)} chars, {len(segments)} segments")
        return (full_text, segments)


transcriber = Transcriber()
