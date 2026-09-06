import asyncio
import logging
import httpx
from google import genai
from google.genai import types
from config import settings

logger = logging.getLogger(__name__)


class LLMProvider:
    def __init__(self):
        if settings.GEMINI_API_KEY:
            self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        else:
            self._client = None

    async def complete(
        self, system_prompt: str, user_prompt: str
    ) -> str:
        if settings.LLM_PROVIDER == "gemini" and self._client:
            try:
                return await self._gemini_complete(
                    system_prompt, user_prompt
                )
            except Exception as e:
                logger.warning(
                    f"Gemini failed ({e}), falling back to Ollama"
                )
        return await self._ollama_complete(system_prompt, user_prompt)

    async def _gemini_complete(
        self, system_prompt: str, user_prompt: str
    ) -> str:
        loop = asyncio.get_event_loop()
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        response = await loop.run_in_executor(
            None,
            lambda: self._client.models.generate_content(
                model=settings.LLM_MODEL,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                ),
            ),
        )
        return response.text

    async def _ollama_complete(
        self, system_prompt: str, user_prompt: str
    ) -> str:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": settings.OLLAMA_LLM_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "stream": False,
                    "format": "json",
                },
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]


llm_provider = LLMProvider()