import asyncio
import logging
import httpx
from google import genai
from google.genai import types
from config import settings

logger = logging.getLogger(__name__)

GEMINI_BATCH_LIMIT = 100


class EmbedProvider:
    """Embeds text with the configured provider only.

    There is deliberately no Gemini -> Ollama fallback here: vectors from two
    different models are not comparable, and mixing them in one Qdrant
    collection would make duplicate detection silently wrong. If you change
    EMBED_PROVIDER, re-ingest the ticket corpus.
    """

    def __init__(self):
        if settings.GEMINI_API_KEY:
            self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        else:
            self._client = None

    async def embed_one(self, text: str) -> list[float]:
        return (await self.embed_batch([text]))[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        texts = [t.strip() for t in texts]
        if settings.EMBED_PROVIDER == "gemini":
            if not self._client:
                raise RuntimeError("EMBED_PROVIDER is gemini but GEMINI_API_KEY is not set")
            vectors = []
            for i in range(0, len(texts), GEMINI_BATCH_LIMIT):
                vectors.extend(await self._gemini_embed(texts[i:i + GEMINI_BATCH_LIMIT]))
            return vectors
        return list(await asyncio.gather(*[self._ollama_embed(t) for t in texts]))

    async def _gemini_embed(self, texts: list[str]) -> list[list[float]]:
        result = await self._client.aio.models.embed_content(
            model=settings.EMBEDDING_MODEL,
            contents=texts,
            config=types.EmbedContentConfig(
                task_type="SEMANTIC_SIMILARITY",
                output_dimensionality=settings.EMBEDDING_SIZE,
            ),
        )
        return [e.values for e in result.embeddings]

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
