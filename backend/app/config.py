import warnings

from pydantic_settings import BaseSettings

_INSECURE_DEFAULT_SECRET = "your-secret-key-change-in-production"


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    # Redis
    REDIS_URL: str
    CACHE_TTL_SECONDS: int = 3600

    # LLM Configuration (provider-agnostic via OpenAI-compatible SDK)
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.deepseek.com/v1"
    LLM_CHAT_MODEL: str = "deepseek-chat"
    LLM_TEMPERATURE: float = 0.3

    # Embedding Configuration (falls back to LLM_* if not set)
    EMBEDDING_API_KEY: str | None = None
    EMBEDDING_BASE_URL: str | None = None
    EMBEDDING_MODEL: str = "text-embedding-v1"
    EMBEDDING_DIMENSION: int = 1024

    # Auth
    JWT_SECRET: str = _INSECURE_DEFAULT_SECRET
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440

    # Upload
    UPLOAD_DIR: str = "/app/uploads"
    MAX_FILE_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: list[str] = [".pdf"]

    # Agent
    AGENT_MAX_ITERATIONS: int = 5
    RETRIEVAL_TOP_K: int = 5

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 20

    @property
    def effective_embedding_api_key(self) -> str:
        return self.EMBEDDING_API_KEY or self.LLM_API_KEY

    @property
    def effective_embedding_base_url(self) -> str:
        return self.EMBEDDING_BASE_URL or self.LLM_BASE_URL

    model_config = {"env_file": ".env"}


settings = Settings()

if settings.JWT_SECRET == _INSECURE_DEFAULT_SECRET:
    warnings.warn(
        "JWT_SECRET is using the insecure default value! "
        "Set JWT_SECRET in .env before deploying to production.",
        stacklevel=1,
    )
