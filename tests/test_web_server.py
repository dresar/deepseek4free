import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from web_server import app, pool


class TestWebServerEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_serve_index_html(self):
        """Verify GET / returns HTML playground"""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers.get("content-type", ""))
        self.assertIn("DeepSeek4Free", response.text)
        self.assertIn("Playground", response.text)

    def test_health_check(self):
        """Verify GET /health returns 200 and health metrics"""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertIn("healthy_tokens", data)

    def test_get_pool_status(self):
        """Verify GET /api/status returns live pool metrics"""
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("total_tokens", data)
        self.assertIn("healthy", data)
        self.assertIn("tokens", data)

    def test_update_settings(self):
        """Verify POST /api/settings updates strategy and boost mode"""
        response = self.client.post("/api/settings", json={
            "strategy": "lru",
            "boost_enabled": True
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("strategy"), "lru")
        self.assertTrue(data.get("boost_enabled"))

        # Restore default
        self.client.post("/api/settings", json={
            "strategy": "round_robin",
            "boost_enabled": False
        })

    def test_add_and_remove_tokens(self):
        """Verify adding single and bulk tokens via API and removing them"""
        raw_tokens = "test_tok_web_1\ntest_tok_web_2"
        add_res = self.client.post("/api/tokens/add", json={
            "tokens_raw": raw_tokens,
            "save_disk": False
        })
        self.assertEqual(add_res.status_code, 200)
        data = add_res.json()
        self.assertGreaterEqual(data.get("added", 0), 2)

        # Remove
        rem_res = self.client.post("/api/tokens/remove", json={"token": "test_tok_web_1"})
        self.assertEqual(rem_res.status_code, 200)
        self.client.post("/api/tokens/remove", json={"token": "test_tok_web_2"})

    def test_openai_models_list(self):
        """Verify GET /v1/models returns standard OpenAI format list"""
        response = self.client.get("/v1/models")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("object"), "list")
        model_ids = [m["id"] for m in data.get("data", [])]
        self.assertIn("deepseek-chat", model_ids)
        self.assertIn("deepseek-reasoner", model_ids)

    def test_openai_chat_completions_mock(self):
        """Verify POST /v1/chat/completions formats non-streaming response correctly"""
        mock_chunks = [
            {"type": "text", "content": "Hello "},
            {"type": "text", "content": "World!"}
        ]

        with patch.object(pool, "chat_completion", return_value=iter(mock_chunks)):
            response = self.client.post("/v1/chat/completions", json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": "Hi"}],
                "stream": False
            })

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data.get("object"), "chat.completion")
            self.assertEqual(data["choices"][0]["message"]["content"], "Hello World!")
            self.assertEqual(data["choices"][0]["finish_reason"], "stop")

    def test_openai_chat_completions_streaming_mock(self):
        """Verify POST /v1/chat/completions formats SSE streaming response correctly"""
        mock_chunks = [
            {"type": "thinking", "content": "Plan response"},
            {"type": "text", "content": "Output"}
        ]

        with patch.object(pool, "chat_completion", return_value=iter(mock_chunks)):
            response = self.client.post("/v1/chat/completions", json={
                "model": "deepseek-reasoner",
                "messages": [{"role": "user", "content": "Solve math"}],
                "stream": True
            })

            self.assertEqual(response.status_code, 200)
            self.assertIn("text/event-stream", response.headers.get("content-type", ""))
            body = response.text
            self.assertIn("data: ", body)
            self.assertIn("[DONE]", body)
            self.assertIn("reasoning_content", body)


if __name__ == "__main__":
    unittest.main()
