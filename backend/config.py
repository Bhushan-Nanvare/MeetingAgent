from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    GEMINI_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_LLM_MODEL: str = "llama3.2"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    LLM_PROVIDER: str = "gemini"
    EMBED_PROVIDER: str = "gemini"
    LLM_MODEL: str = "gemini-1.5-flash"
    EMBEDDING_MODEL: str = "models/text-embedding-004"
    EMBEDDING_SIZE: int = 768
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION: str = "meeting_corpus"
    DEDUP_THRESHOLD: float = 0.78
    MOCK_INTEGRATIONS: bool = True
    WHISPER_MODEL: str = "base"
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
