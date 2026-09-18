import asyncio
import logging
import random
import httpx
from google import genai
from google.genai import errors, types
from config import settings

logger = logging.getLogger(__name__)

# Gemini returns these when it is overloaded or rate limited; they usually pass.
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
MAX_ATTEMPTS = 2
BACKOFF_SECONDS = 2.0


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
            except Exception as gemini_error:
                logger.warning(
                    f"Gemini failed ({gemini_error}), falling back to Ollama"
                )
                try:
                    return await self._ollama_complete(system_prompt, user_prompt)
                except Exception as ollama_error:
                    raise RuntimeError(
                        f"Gemini failed: {gemini_error}. "
                        f"Ollama fallback also failed: {ollama_error}"
                    ) from ollama_error
        return await self._ollama_complete(system_prompt, user_prompt)

    async def _gemini_complete(
        self, system_prompt: str, user_prompt: str
    ) -> str:
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        last_error: Exception | None = None
        for model in self._model_candidates():
            try:
                return await self._generate(model, user_prompt, config)
            except errors.APIError as e:
                if getattr(e, "code", None) not in RETRYABLE_STATUS:
                    raise
                # Individual models go overloaded on their own, so try the next one.
                last_error = e
                logger.warning(
                    f"{model} is unavailable ({getattr(e, 'code', '?')}), trying the next model"
                )
        raise last_error  # type: ignore[misc]

    async def _generate(self, model: str, user_prompt: str, config) -> str:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = await self._client.aio.models.generate_content(
                    model=model,
                    contents=user_prompt,
                    config=config,
                )
                return response.text
            except errors.APIError as e:
                if getattr(e, "code", None) not in RETRYABLE_STATUS or attempt == MAX_ATTEMPTS:
                    raise
                # Jitter keeps parallel calls from retrying in lockstep.
                delay = BACKOFF_SECONDS * (2 ** (attempt - 1)) + random.uniform(0, 1)
                logger.warning(
                    f"{model} returned {getattr(e, 'code', '?')}, retrying in {delay:.1f}s"
                )
                await asyncio.sleep(delay)
        raise RuntimeError("unreachable")  # pragma: no cover

    @staticmethod
    def _model_candidates() -> list[str]:
        names = [settings.LLM_MODEL] + [
            name.strip() for name in settings.LLM_FALLBACK_MODELS.split(",")
        ]
        ordered: list[str] = []
        for name in names:
            if name and name not in ordered:
                ordered.append(name)
        return ordered

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
                    # Ollama defaults to a small context window and silently
                    # truncates long transcripts without this.
                    "options": {"num_ctx": settings.OLLAMA_NUM_CTX},
                },
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]


llm_provider = LLMProvider()
