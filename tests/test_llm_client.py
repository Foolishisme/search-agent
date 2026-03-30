import unittest

from app.config import Settings
from app.llm_client import DeepSeekClient
from app.schemas import ExecutionPlan, SkillContext, SkillSummary


class LLMClientPromptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = DeepSeekClient(
            Settings(
                deepseek_api_key="test",
                deepseek_model="deepseek-chat",
                deepseek_base_url="https://api.deepseek.com",
                tavily_api_key="test",
                search_top_k=10,
                llm_request_timeout=90,
                search_request_timeout=20,
                python_execution_timeout=30,
                wsl_distro_name="Ubuntu-24.04",
                wsl_python_command="python3",
                log_level="INFO",
                proxy_url=None,
            )
        )

    def test_final_answer_prompt_includes_tools_plan_progress_rules_and_skills(self):
        prompt = self.client._build_final_answer_prompt(
            "你现在有哪些工具",
            history=[{"tool": "execute_python_wsl", "status": "success"}],
            plan=ExecutionPlan(route="python_execution", canvas_requested=False, selected_skills=["python-1"]),
            rules_text="Always be concise.",
            selected_skills=[SkillContext(skill_id="python-1", name="Python", description="Run code", content="Prefer print for outputs.")],
            conversation=[],
            attachments=[],
        )

        self.assertIn("Available tools:", prompt)
        self.assertIn("Global rules:", prompt)
        self.assertIn("Selected skills:", prompt)
        self.assertIn("search_web", prompt)
        self.assertIn("save_markdown_artifact", prompt)
        self.assertIn("execute_python_wsl", prompt)
        self.assertIn("Current plan:", prompt)
        self.assertIn("python_execution", prompt)
        self.assertIn("Current progress / tool history:", prompt)

    def test_plan_prompt_includes_available_tools_and_skills(self):
        prompt = self.client._build_plan_prompt(
            "你是否可以执行代码？",
            conversation=[],
            attachments=[],
            rules_text="Be honest about tools.",
            available_skills=[SkillSummary(seq=1, skill_id="python-1", name="Python", description="Python execution", enabled=True)],
        )

        self.assertIn("Available tools:", prompt)
        self.assertIn("Available skills:", prompt)
        self.assertIn("execute_python_wsl", prompt)
        self.assertIn("python-1", prompt)
