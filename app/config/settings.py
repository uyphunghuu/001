import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv():
    """Load .env file từ root project nếu có."""
    # Tìm .env từ thư mục app lên 2 cấp (app/config -> app -> root)
    root = Path(__file__).parent.parent.parent
    env_file = root / ".env"
    if env_file.exists():
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip()
                # Chỉ set nếu chưa có trong environment (không override env thật)
                if key and not os.environ.get(key):
                    os.environ[key] = val


_load_dotenv()


@dataclass
class Settings:
    pg_host: str = field(default_factory=lambda: os.getenv("PG_HOST", "localhost"))
    pg_port: int = field(default_factory=lambda: int(os.getenv("PG_PORT", "5433")))
    pg_user: str = field(default_factory=lambda: os.getenv("PG_USER", "platform"))
    pg_password: str = field(default_factory=lambda: os.getenv("PG_PASSWORD", "platform123"))
    pg_db: str = field(default_factory=lambda: os.getenv("PG_DB", "ai_platform"))

    llm_api_key: str = field(
        default_factory=lambda: os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    )
    llm_base_url: str = field(
        default_factory=lambda: os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    )
    llm_model: str = field(
        default_factory=lambda: os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
    )

    pg_sslmode: str = field(default_factory=lambda: os.getenv("PG_SSLMODE", "require"))

    @property
    def database_url(self) -> str:
        return f"postgresql://{self.pg_user}:{self.pg_password}@{self.pg_host}:{self.pg_port}/{self.pg_db}?sslmode={self.pg_sslmode}"


settings = Settings()
