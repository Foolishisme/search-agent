import json
import logging

import httpx

from app.config import Settings
from app.schemas import DecisionResult, SearchResult

logger = logging.getLogger(__name__)


class LLMClientError(Exception):
    pass


class DeepSeekClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.endpoint = f"{self.settings.deepseek_base_url.rstrip('/')}/chat/completions"

    async def decide(self, question: str) -> DecisionResult:
        prompt = (
            "你是一个最小搜索 Agent 的决策器。请严格输出 JSON，不要输出 Markdown，不要输出额外解释。"
            '如果问题可以依赖稳定常识直接回答，返回 {"need_search": false, "answer": "..."}。'
            '如果问题需要外部信息、最新信息、事实检索或网页信息，返回 {"need_search": true, "query": "..."}。'
            "query 必须是适合搜索引擎执行的中文或英文短查询。"
            f"\n用户问题：{question}"
        )
        data = await self._generate_json(prompt)
        try:
            decision = DecisionResult.model_validate(data)
        except Exception as exc:
            logger.exception("DeepSeek 决策结果解析失败")
            raise LLMClientError("LLM 决策结果格式不合法") from exc

        if decision.need_search and not (decision.query or "").strip():
            raise LLMClientError("LLM 判断需要搜索，但未返回查询词")
        if not decision.need_search and not (decision.answer or "").strip():
            raise LLMClientError("LLM 判断无需搜索，但未返回直接答案")
        return decision

    async def summarize(self, question: str, search_results: list[SearchResult]) -> str:
        serialized_results = json.dumps([item.model_dump() for item in search_results], ensure_ascii=False)
        prompt = (
            "你是一个最小搜索 Agent 的回答器。"
            "请基于给定问题和搜索结果，用中文输出清晰、自然、简洁但完整的最终回答。"
            "如果信息不足，要明确说不确定或未找到充分信息。"
            "不要输出 JSON。"
            f"\n用户问题：{question}"
            f"\n搜索结果：{serialized_results}"
        )
        return await self._generate_text(prompt)

    async def _generate_json(self, prompt: str) -> dict:
        payload = {
            "model": self.settings.deepseek_model,
            "messages": [
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        text = await self._post_generate(payload)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            cleaned = text.strip().removeprefix("```json").removesuffix("```").strip()
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError as exc:
                logger.exception("DeepSeek JSON 输出无法解析")
                raise LLMClientError("LLM 决策结果不是合法 JSON") from exc

    async def _generate_text(self, prompt: str) -> str:
        payload = {
            "model": self.settings.deepseek_model,
            "messages": [
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
        }
        text = await self._post_generate(payload)
        if not text.strip():
            raise LLMClientError("LLM 未返回有效答案")
        return text.strip()

    async def _post_generate(self, payload: dict) -> str:
        if not self.settings.deepseek_api_key:
            raise LLMClientError("未配置 DEEPSEEK_API_KEY")

        try:
            client_kwargs = {
                "timeout": self.settings.request_timeout,
                "trust_env": False,
            }
            if self.settings.proxy_url:
                client_kwargs["proxy"] = self.settings.proxy_url

            async with httpx.AsyncClient(**client_kwargs) as client:
                response = await client.post(
                    self.endpoint,
                    headers={
                        "Authorization": f"Bearer {self.settings.deepseek_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
        except httpx.ConnectTimeout as exc:
            logger.exception("DeepSeek 连接超时")
            raise LLMClientError("无法连接 DeepSeek API，请检查本机网络，或在 .env 中配置 PROXY_URL") from exc
        except httpx.TimeoutException as exc:
            logger.exception("DeepSeek 请求超时")
            raise LLMClientError("LLM 请求超时，请检查网络连通性或代理配置") from exc
        except httpx.HTTPError as exc:
            logger.exception("DeepSeek 请求失败")
            raise LLMClientError("LLM 请求失败") from exc

        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            raise LLMClientError("LLM 未返回候选结果")

        message = choices[0].get("message", {})
        combined = str(message.get("content", "")).strip()
        if not combined:
            raise LLMClientError("LLM 返回内容为空")
        return combined
