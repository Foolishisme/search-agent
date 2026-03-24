import json
import logging

import httpx

from app.config import Settings
from app.schemas import AgentAction, AttachmentContext, ConversationMessage

logger = logging.getLogger(__name__)


class LLMClientError(Exception):
    pass


class DeepSeekClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.endpoint = f"{self.settings.deepseek_base_url.rstrip('/')}/chat/completions"

    async def next_action(
        self,
        question: str,
        history: list[dict],
        conversation: list[ConversationMessage] | None = None,
        attachments: list[AttachmentContext] | None = None,
    ) -> AgentAction:
        prompt = self._build_action_prompt(question, history, conversation or [], attachments or [])
        data = await self._generate_json(prompt)
        try:
            action = AgentAction.model_validate(data)
        except Exception as exc:
            logger.exception("DeepSeek 决策结果解析失败")
            raise LLMClientError("LLM 决策结果格式不合法") from exc

        if action.action == "search" and not (action.query or "").strip():
            raise LLMClientError("LLM 选择 search，但未返回查询词")
        if action.action == "final" and not (action.answer or "").strip():
            raise LLMClientError("LLM 选择 final，但未返回最终答案")
        return action

    def _build_action_prompt(
        self,
        question: str,
        history: list[dict],
        conversation: list[ConversationMessage],
        attachments: list[AttachmentContext],
    ) -> str:
        serialized_history = json.dumps(history, ensure_ascii=False)
        recent_conversation = [
            {
                "role": item.role,
                "content": item.content,
                "created_at": item.created_at,
            }
            for item in conversation[-6:]
        ]
        serialized_attachments = json.dumps(
            [
                {
                    "filename": item.filename,
                    "media_type": item.media_type,
                    "excerpt": item.excerpt,
                }
                for item in attachments
            ],
            ensure_ascii=False,
        )
        serialized_conversation = json.dumps(recent_conversation, ensure_ascii=False)
        return (
            "你是一个最小搜索 Agent。你每一轮只能输出一个 JSON 对象，不能输出 Markdown，不能输出额外解释。"
            "你可用的 action 只有两种："
            '1. {"action":"search","query":"..."} 表示调用搜索工具；'
            '2. {"action":"final","answer":"..."} 表示直接输出最终答案。'
            "如果当前信息不足以可靠回答，你应该优先选择 search。"
            "如果 history 中已经有搜索结果，你应基于 history 里的结果整理答案，而不是继续盲目搜索。"
            "如果 conversation 中有历史对话，你应把它当作当前会话记忆；当用户问题依赖上下文时，需要结合这些历史信息理解意图。"
            "如果 attachments 中有附件摘录，你应结合附件内容回答；当附件已经足够回答时，不必强制搜索。"
            "当搜索结果不足时，可以直接输出带不确定性的 final。"
            f"\n用户问题：{question}"
            f"\n当前 conversation：{serialized_conversation}"
            f"\n当前 attachments：{serialized_attachments}"
            f"\n当前 history：{serialized_history}"
        )

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
