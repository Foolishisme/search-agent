import json
import logging

import httpx

from app.config import Settings
from app.schemas import AttachmentContext, CanvasDraft, ConversationMessage, ExecutionPlan, SearchDecision

logger = logging.getLogger(__name__)


class LLMClientError(Exception):
    pass


class DeepSeekClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.endpoint = f"{self.settings.deepseek_base_url.rstrip('/')}/chat/completions"

    async def plan(
        self,
        question: str,
        conversation: list[ConversationMessage] | None = None,
        attachments: list[AttachmentContext] | None = None,
    ) -> ExecutionPlan:
        prompt = self._build_plan_prompt(question, conversation or [], attachments or [])
        data = await self._generate_json(prompt)
        try:
            return ExecutionPlan.model_validate(data)
        except Exception as exc:
            logger.exception("LLM plan parse failed")
            raise LLMClientError("LLM returned an invalid execution plan") from exc

    async def suggest_search_query(
        self,
        question: str,
        history: list[dict],
        conversation: list[ConversationMessage] | None = None,
        attachments: list[AttachmentContext] | None = None,
    ) -> str:
        prompt = self._build_search_query_prompt(question, history, conversation or [], attachments or [])
        data = await self._generate_json(prompt)
        query = str(data.get("query", "")).strip()
        if not query:
            raise LLMClientError("LLM did not return a valid search query")
        return query

    async def assess_search_progress(
        self,
        question: str,
        history: list[dict],
        conversation: list[ConversationMessage] | None = None,
        attachments: list[AttachmentContext] | None = None,
    ) -> SearchDecision:
        prompt = self._build_search_assessment_prompt(question, history, conversation or [], attachments or [])
        data = await self._generate_json(prompt)
        try:
            decision = SearchDecision.model_validate(data)
        except Exception as exc:
            logger.exception("LLM search assessment parse failed")
            raise LLMClientError("LLM returned an invalid search assessment") from exc
        if decision.next == "retry" and not (decision.query or "").strip():
            raise LLMClientError("LLM requested retry without providing a new search query")
        return decision

    async def final_answer(
        self,
        question: str,
        history: list[dict],
        conversation: list[ConversationMessage] | None = None,
        attachments: list[AttachmentContext] | None = None,
    ) -> str:
        prompt = self._build_final_answer_prompt(question, history, conversation or [], attachments or [])
        answer = await self._generate_text(prompt)
        if not answer.strip():
            raise LLMClientError("LLM returned an empty final answer")
        return answer.strip()

    async def build_canvas_document(
        self,
        question: str,
        answer: str,
        conversation: list[ConversationMessage] | None = None,
        attachments: list[AttachmentContext] | None = None,
    ) -> CanvasDraft:
        prompt = self._build_canvas_prompt(question, answer, conversation or [], attachments or [])
        data = await self._generate_json(prompt)
        try:
            draft = CanvasDraft.model_validate(data)
        except Exception as exc:
            logger.exception("LLM canvas draft parse failed")
            raise LLMClientError("LLM returned an invalid canvas document") from exc
        if not draft.title.strip():
            raise LLMClientError("Canvas document title cannot be empty")
        if not draft.content.strip():
            raise LLMClientError("Canvas document content cannot be empty")
        return draft

    def _serialize_conversation(self, conversation: list[ConversationMessage]) -> str:
        payload = [
            {"role": item.role, "content": item.content, "created_at": item.created_at}
            for item in conversation[-6:]
        ]
        return json.dumps(payload, ensure_ascii=False)

    def _serialize_attachments(self, attachments: list[AttachmentContext]) -> str:
        payload = [
            {
                "filename": item.filename,
                "media_type": item.media_type,
                "excerpt": item.excerpt,
            }
            for item in attachments
        ]
        return json.dumps(payload, ensure_ascii=False)

    def _serialize_history(self, history: list[dict]) -> str:
        return json.dumps(history, ensure_ascii=False)

    def _build_plan_prompt(
        self,
        question: str,
        conversation: list[ConversationMessage],
        attachments: list[AttachmentContext],
    ) -> str:
        return (
            "You are the planner for a lightweight search agent.\n"
            "Return exactly one JSON object.\n"
            'Schema: {"route":"direct_answer"|"information_gathering","canvas_requested":boolean,"rationale":"..."}\n'
            "Rules:\n"
            "- route=direct_answer when the user can be answered from general knowledge or the provided conversation/attachments.\n"
            "- route=information_gathering when up-to-date, factual, or externally verified information is needed.\n"
            "- canvas_requested=true only when the user explicitly asks to save, export, generate, or keep a Markdown document/artifact.\n"
            "- Do not request canvas for ordinary Q&A.\n"
            f"\nQuestion: {question}\n"
            f"Conversation: {self._serialize_conversation(conversation)}\n"
            f"Attachments: {self._serialize_attachments(attachments)}"
        )

    def _build_search_query_prompt(
        self,
        question: str,
        history: list[dict],
        conversation: list[ConversationMessage],
        attachments: list[AttachmentContext],
    ) -> str:
        return (
            "You generate one web search query for a lightweight search agent.\n"
            "Return exactly one JSON object with schema: {\"query\":\"...\"}.\n"
            "Rules:\n"
            "- Produce a concise query optimized for web search.\n"
            "- If previous search attempts exist, adjust the query instead of repeating the same wording.\n"
            "- Use explicit dates, names, aliases, and time anchors when helpful.\n"
            f"\nQuestion: {question}\n"
            f"Conversation: {self._serialize_conversation(conversation)}\n"
            f"Attachments: {self._serialize_attachments(attachments)}\n"
            f"Tool history: {self._serialize_history(history)}"
        )

    def _build_search_assessment_prompt(
        self,
        question: str,
        history: list[dict],
        conversation: list[ConversationMessage],
        attachments: list[AttachmentContext],
    ) -> str:
        return (
            "You are judging whether a search subtask should continue.\n"
            "Return exactly one JSON object.\n"
            'Schema: {"next":"answer"|"retry"|"stop","reason":"...","query":"..."}\n'
            "Rules:\n"
            "- next=answer when the gathered public information is enough for a useful answer.\n"
            "- next=retry when another search attempt is likely to help materially. Provide a different query.\n"
            "- next=stop when more searching is unlikely to help. The system will answer with available information and may state that public information is insufficient.\n"
            "- Prefer stop over endless retry.\n"
            f"\nQuestion: {question}\n"
            f"Conversation: {self._serialize_conversation(conversation)}\n"
            f"Attachments: {self._serialize_attachments(attachments)}\n"
            f"Tool history: {self._serialize_history(history)}"
        )

    def _build_final_answer_prompt(
        self,
        question: str,
        history: list[dict],
        conversation: list[ConversationMessage],
        attachments: list[AttachmentContext],
    ) -> str:
        return (
            "You are the final answer generator for a lightweight search agent.\n"
            "Write the final answer in the user's language.\n"
            "You may use Markdown.\n"
            "If public information is insufficient, say so plainly instead of inventing facts.\n"
            f"\nQuestion: {question}\n"
            f"Conversation: {self._serialize_conversation(conversation)}\n"
            f"Attachments: {self._serialize_attachments(attachments)}\n"
            f"Tool history: {self._serialize_history(history)}"
        )

    def _build_canvas_prompt(
        self,
        question: str,
        answer: str,
        conversation: list[ConversationMessage],
        attachments: list[AttachmentContext],
    ) -> str:
        return (
            "You are preparing a Markdown artifact for a lightweight search agent.\n"
            "Return exactly one JSON object with schema: {\"title\":\"...\",\"content\":\"...\"}.\n"
            "Rules:\n"
            "- The content must be valid Markdown.\n"
            "- Base the document on the final answer.\n"
            "- Keep the title concise and user-facing.\n"
            f"\nQuestion: {question}\n"
            f"Final answer: {answer}\n"
            f"Conversation: {self._serialize_conversation(conversation)}\n"
            f"Attachments: {self._serialize_attachments(attachments)}"
        )

    async def _generate_json(self, prompt: str) -> dict:
        payload = {
            "model": self.settings.deepseek_model,
            "messages": [{"role": "user", "content": prompt}],
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
                logger.exception("DeepSeek JSON output could not be parsed")
                raise LLMClientError("LLM output is not valid JSON") from exc

    async def _generate_text(self, prompt: str) -> str:
        payload = {
            "model": self.settings.deepseek_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        }
        return await self._post_generate(payload)

    async def _post_generate(self, payload: dict) -> str:
        if not self.settings.deepseek_api_key:
            raise LLMClientError("DEEPSEEK_API_KEY is not configured")

        try:
            client_kwargs = {
                "timeout": self.settings.llm_request_timeout,
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
            logger.exception("DeepSeek connect timeout")
            raise LLMClientError("Unable to connect to DeepSeek API") from exc
        except httpx.TimeoutException as exc:
            logger.exception("DeepSeek request timeout")
            raise LLMClientError("LLM request timed out") from exc
        except httpx.HTTPError as exc:
            logger.exception("DeepSeek request failed")
            raise LLMClientError("LLM request failed") from exc

        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            raise LLMClientError("LLM returned no choices")

        message = choices[0].get("message", {})
        combined = str(message.get("content", "")).strip()
        if not combined:
            raise LLMClientError("LLM returned empty content")
        return combined
