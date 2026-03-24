import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    deepseek_api_key: str
    deepseek_model: str
    deepseek_base_url: str
    tavily_api_key: str
    search_top_k: int
    request_timeout: float
    log_level: str
    proxy_url: str | None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    proxy_url = os.getenv("PROXY_URL", "").strip() or None
    return Settings(
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", "").strip(),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip(),
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip(),
        tavily_api_key=os.getenv("TAVILY_API_KEY", "").strip(),
        search_top_k=int(os.getenv("SEARCH_TOP_K", "5")),
        request_timeout=float(os.getenv("REQUEST_TIMEOUT", "20")),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip(),
        proxy_url=proxy_url,
    )
