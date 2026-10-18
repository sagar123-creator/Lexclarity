import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services import llm


class OpenAICompatibleProviderTests(unittest.TestCase):
    def setUp(self):
        self.settings = patch.object(
            llm,
            "settings",
            SimpleNamespace(
                LLM_PROVIDER="groq",
                LLM_API_KEY="gsk_test_key",
                LLM_MODEL="llama-3.3-70b-versatile",
                LLM_BASE_URL="https://api.groq.com/openai/v1",
                LLM_MAX_TOKENS=2000,
                LLM_MAX_RETRIES=0,
            ),
        )
        self.settings.start()
        self.addCleanup(self.settings.stop)

    @patch("openai.OpenAI")
    def test_groq_uses_openai_compatible_endpoint(self, openai_client):
        openai_client.return_value.chat.completions.create.return_value = (
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))])
        )

        result = llm.complete("system", "user", max_tokens=123)

        self.assertEqual(result, '{"ok": true}')
        openai_client.assert_called_once_with(
            base_url="https://api.groq.com/openai/v1",
            api_key="gsk_test_key",
        )
        openai_client.return_value.chat.completions.create.assert_called_once_with(
            model="llama-3.3-70b-versatile",
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
    def test_unavailable_groq_has_actionable_error(self, _openai_client):
        with self.assertRaisesRegex(llm.LLMError, "Groq API is unavailable"):
            llm.complete("system", "user")

    @patch("openai.OpenAI")
    def test_complete_json_accepts_groq_markdown_fence(self, openai_client):
        openai_client.return_value.chat.completions.create.return_value = (
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="```json\n{\"ok\": true}\n```"))])
        )
        self.assertEqual(llm.complete_json("system", "user"), {"ok": True})

    @patch("openai.OpenAI")
    def test_complete_json_rejects_invalid_response(self, openai_client):
        openai_client.return_value.chat.completions.create.return_value = (
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="not json"))])
        )
        with self.assertRaisesRegex(llm.LLMError, "did not return valid JSON"):
            llm.complete_json("system", "user")

    def test_missing_groq_key_has_actionable_error(self):
        with patch.object(llm.settings, "LLM_API_KEY", ""):
            with self.assertRaisesRegex(llm.LLMError, "Groq API key is missing"):
                llm.complete("system", "user")

    @patch("openai.OpenAI")
    def test_ollama_adapter_remains_available(self, openai_client):
        with patch.object(
            llm,
            "settings",
            SimpleNamespace(
                LLM_PROVIDER="ollama",
                LLM_API_KEY="",
                LLM_MODEL="qwen2.5:7b",
                LLM_BASE_URL="http://localhost:11434/v1",
                LLM_MAX_TOKENS=2000,
            ),
        ):
            openai_client.return_value.chat.completions.create.return_value = (
                SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])
            )
            self.assertEqual(llm.complete("system", "user"), "ok")
            openai_client.assert_called_once_with(
                base_url="http://localhost:11434/v1",
                api_key="ollama",
            )


class CloudProviderKeyTests(unittest.TestCase):
    def test_cloud_providers_require_api_key(self):
        for provider in ("anthropic", "openai", "gemini", "groq"):
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
                expected = "Groq API key is missing" if provider == "groq" else "LLM_API_KEY is not set"
                with self.assertRaisesRegex(llm.LLMError, expected):
                    llm.complete("system", "user")


class TransientRetryTests(unittest.TestCase):
    def _settings(self, retries=2):
        return SimpleNamespace(
            LLM_PROVIDER="groq",
            LLM_API_KEY="gsk_test_key",
            LLM_MODEL="llama-3.3-70b-versatile",
            LLM_BASE_URL="https://api.groq.com/openai/v1",
            LLM_MAX_TOKENS=2000,
            LLM_MAX_RETRIES=retries,
            LLM_RETRY_BACKOFF_SECONDS=0.0,
        )

    @patch("time.sleep")
    @patch("openai.OpenAI")
    def test_transient_error_is_retried_then_succeeds(self, openai_client, sleep):
        client = openai_client.return_value.chat.completions.create
        client.side_effect = [
            ConnectionError("connection refused"),
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]),
        ]

        with patch.object(llm, "settings", self._settings(retries=2)):
            self.assertEqual(llm.complete("system", "user"), "ok")
        self.assertEqual(client.call_count, 2)

    @patch("time.sleep")
    @patch("openai.OpenAI")
    def test_transient_error_gives_up_after_max_retries(self, openai_client, sleep):
        openai_client.return_value.chat.completions.create.side_effect = ConnectionError(
            "connection refused"
        )

        with patch.object(llm, "settings", self._settings(retries=2)):
            with self.assertRaisesRegex(llm.LLMError, "Groq API is unavailable"):
                llm.complete("system", "user")
        self.assertEqual(openai_client.return_value.chat.completions.create.call_count, 3)

    @patch("time.sleep")
    @patch("openai.OpenAI")
    def test_permanent_error_is_not_retried(self, openai_client, sleep):
        openai_client.return_value.chat.completions.create.side_effect = Exception(
            "401 Unauthorized: invalid api key"
        )

        with patch.object(llm, "settings", self._settings(retries=3)):
            with self.assertRaisesRegex(llm.LLMError, "invalid"):
                llm.complete("system", "user")
        self.assertEqual(openai_client.return_value.chat.completions.create.call_count, 1)
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
