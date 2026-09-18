from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# .env lives in the project root (one level above backend/), so it is found
# no matter which directory the app or tests are started from.
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    GEMINI_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_LLM_MODEL: str = "llama3.2"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    OLLAMA_NUM_CTX: int = 16384
    LLM_PROVIDER: str = "gemini"
    EMBED_PROVIDER: str = "gemini"
    LLM_MODEL: str = "gemini-flash-latest"
    # Tried in order when the main model is overloaded or rate limited.
    LLM_FALLBACK_MODELS: str = "gemini-flash-lite-latest"
    EMBEDDING_MODEL: str = "gemini-embedding-001"
    EMBEDDING_SIZE: int = 768
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION: str = "meeting_corpus"
    DEDUP_THRESHOLD: float = 0.78
    MOCK_INTEGRATIONS: bool = True
    WHISPER_MODEL: str = "base"
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

settings = Settings()
