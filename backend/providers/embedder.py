import asyncio
import logging
import httpx
from google import genai
from config import settings

logger = logging.getLogger(__name__)


class EmbedProvider:
    def __init__(self):
        if settings.GEMINI_API_KEY:
            self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        else:
            self._client = None

    async def embed_one(self, text: str) -> list[float]:
        if settings.EMBED_PROVIDER == "gemini" and self._client:
            try:
                return await self._gemini_embed(text.strip())
            except Exception as e:
                logger.warning(
                    f"Gemini embed failed ({e}), falling back to Ollama"
                )
        return await self._ollama_embed(text.strip())

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        results = await asyncio.gather(
            *[self.embed_one(t) for t in texts],
            return_exceptions=True,
        )
        vectors = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                logger.error(f"Embedding failed for text[{i}]: {r}")
                vectors.append([0.0] * settings.EMBEDDING_SIZE)
            else:
                vectors.append(r)
        return vectors

    async def _gemini_embed(self, text: str) -> list[float]:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self._client.models.embed_content(
                model=settings.EMBEDDING_MODEL,
                contents=text,
            ),
        )
        return result.embeddings[0].values

    async def _ollama_embed(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/embeddings",
                json={
                    "model": settings.OLLAMA_EMBED_MODEL,
                    "prompt": text,
                },
            )
            resp.raise_for_status()
            return resp.json()["embedding"]


embedder = EmbedProvider()