import logging

import httpx

from app.config import Settings
from app.schemas import SearchResult

logger = logging.getLogger(__name__)


class SearchToolError(Exception):
    pass


class TavilySearchTool:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def search(self, query: str) -> list[SearchResult]:
        if not self.settings.tavily_api_key:
            raise SearchToolError("未配置 TAVILY_API_KEY")

        payload = {
            "api_key": self.settings.tavily_api_key,
            "query": query,
            "max_results": self.settings.search_top_k,
            "search_depth": "basic",
            "include_answer": False,
            "include_images": False,
            "include_raw_content": False,
        }

        try:
            client_kwargs = {
                "timeout": self.settings.search_request_timeout,
                "trust_env": False,
            }
            if self.settings.proxy_url:
                client_kwargs["proxy"] = self.settings.proxy_url

            async with httpx.AsyncClient(**client_kwargs) as client:
                response = await client.post("https://api.tavily.com/search", json=payload)
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            logger.exception("Tavily 请求超时")
            raise SearchToolError("搜索请求超时") from exc
        except httpx.HTTPError as exc:
            logger.exception("Tavily 请求失败")
            raise SearchToolError("搜索请求失败") from exc

        data = response.json()
        results = data.get("results", [])
        normalized: list[SearchResult] = []
        for item in results[: self.settings.search_top_k]:
            normalized.append(
                SearchResult(
                    title=str(item.get("title", "")).strip() or "无标题",
                    snippet=str(item.get("content", "")).strip() or "无摘要",
                    url=str(item.get("url", "")).strip() or "",
                )
            )
        return normalized
