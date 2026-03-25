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
    llm_request_timeout: float
    search_request_timeout: float
    python_execution_timeout: float
    wsl_distro_name: str | None
    wsl_python_command: str
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
        search_top_k=int(os.getenv("SEARCH_TOP_K", "10")),
        llm_request_timeout=float(os.getenv("LLM_REQUEST_TIMEOUT", "90")),
        search_request_timeout=float(os.getenv("SEARCH_REQUEST_TIMEOUT", "20")),
        python_execution_timeout=float(os.getenv("PYTHON_EXECUTION_TIMEOUT", "30")),
        wsl_distro_name=os.getenv("WSL_DISTRO_NAME", "Ubuntu-24.04").strip() or None,
        wsl_python_command=os.getenv("WSL_PYTHON_COMMAND", "python3").strip(),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip(),
        proxy_url=proxy_url,
    )
