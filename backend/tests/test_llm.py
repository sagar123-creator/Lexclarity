import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services import llm


class OllamaProviderTests(unittest.TestCase):
    def setUp(self):
        self.settings = patch.object(
            llm,
            "settings",
            SimpleNamespace(
                LLM_PROVIDER="ollama",
                LLM_API_KEY="",
                LLM_MODEL="qwen2.5:7b",
                LLM_BASE_URL="http://localhost:11434/v1",
                LLM_MAX_TOKENS=2000,
            ),
        )
        self.settings.start()
        self.addCleanup(self.settings.stop)

    @patch("openai.OpenAI")
    def test_ollama_uses_local_openai_compatible_endpoint(self, openai_client):
        openai_client.return_value.chat.completions.create.return_value = (
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))])
        )

        result = llm.complete("system", "user", max_tokens=123)

        self.assertEqual(result, '{"ok": true}')
        openai_client.assert_called_once_with(
            base_url="http://localhost:11434/v1",
            api_key="ollama",
        )
        openai_client.return_value.chat.completions.create.assert_called_once_with(
            model="qwen2.5:7b",
            max_tokens=123,
            messages=[
                {"role": "system", "content": "system"},
                {"role": "user", "content": "user"},
            ],
        )

    @patch("openai.OpenAI")
    def test_complete_json_preserves_structured_output_contract(self, openai_client):
        openai_client.return_value.chat.completions.create.return_value = (
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"items": []}'))])
        )

        self.assertEqual(llm.complete_json("system", "user"), {"items": []})

    @patch("openai.OpenAI", side_effect=ConnectionError("connection refused"))
    def test_unavailable_ollama_has_actionable_error(self, _openai_client):
        with self.assertRaisesRegex(llm.LLMError, "Local Ollama server is unavailable"):
            llm.complete("system", "user")

    @patch("openai.OpenAI")
    def test_missing_model_has_pull_instruction(self, openai_client):
        openai_client.return_value.chat.completions.create.side_effect = RuntimeError("404 model not found")

        with self.assertRaisesRegex(llm.LLMError, "ollama pull qwen2.5:7b"):
            llm.complete("system", "user")

    def test_ollama_does_not_require_api_key(self):
        with patch("app.services.llm._complete_ollama", return_value="ok") as provider:
            self.assertEqual(llm.complete("system", "user"), "ok")
            provider.assert_called_once()


class CloudProviderKeyTests(unittest.TestCase):
    def test_cloud_providers_require_api_key(self):
        for provider in ("anthropic", "openai", "gemini"):
            with self.subTest(provider=provider), patch.object(
                llm,
                "settings",
                SimpleNamespace(
                    LLM_PROVIDER=provider,
                    LLM_API_KEY="",
                    LLM_MODEL="test-model",
                    LLM_BASE_URL="http://localhost:11434/v1",
                    LLM_MAX_TOKENS=2000,
                ),
            ):
                with self.assertRaisesRegex(llm.LLMError, "LLM_API_KEY is not set"):
                    llm.complete("system", "user")


if __name__ == "__main__":
    unittest.main()
