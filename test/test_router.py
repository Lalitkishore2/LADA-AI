"""
LADA - AI Router Tests
Tests for the unified ProviderManager-based routing system
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
from types import SimpleNamespace

# Mock modules that may not be installed in test environment
sys.modules.setdefault("modules.web_search", MagicMock())
sys.modules.setdefault("modules.deep_research", MagicMock())
sys.modules.setdefault("modules.citation_engine", MagicMock())
sys.modules.setdefault("modules.vector_memory", MagicMock())
sys.modules.setdefault("modules.rag_engine", MagicMock())

from lada_ai_router import HybridAIRouter


class TestHybridAIRouter:
    """Test suite for AI router"""

    @pytest.fixture
    def router(self):
        with patch("lada_ai_router.get_provider_manager") as mock_pm_factory, \
             patch("lada_ai_router.PROVIDER_MANAGER_OK", True):
            mock_pm = MagicMock()
            mock_pm.providers = {}
            mock_pm.conversation_history = []
            mock_pm_factory.return_value = mock_pm
            router = HybridAIRouter()
            return router

    def test_router_initialization(self, router):
        """Test router initializes correctly"""
        assert router is not None
        assert router.provider_manager is not None
        assert router.current_backend_name == "Auto"

    def test_query_basic(self, router):
        """Test basic query via ProviderManager"""
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.content = "Hello from provider"
        mock_response.provider = "groq"
        mock_response.model = "llama-3.3-70b"

        router.provider_manager.get_best_model.return_value = {
            'model_id': 'llama-3.3-70b', 'provider_id': 'groq',
            'model_name': 'Llama 3.3 70B', 'tier': 'smart',
        }
        mock_provider = MagicMock()
        mock_provider.complete_with_retry.return_value = mock_response
        router.provider_manager.get_provider_for_model.return_value = mock_provider
        router.provider_manager._build_messages.return_value = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "Hello"},
        ]

        response = router.query("Hello")
        assert response == "Hello from provider"

    def test_query_empty_prompt(self, router):
        """Test query with empty prompt returns error message"""
        response = router.query("")
        assert "didn't catch that" in response

    def test_query_all_providers_fail(self, router):
        """Test graceful fallback when all providers fail"""
        router.provider_manager.get_best_model.return_value = None
        router.provider_manager.query.return_value = MagicMock(success=False, content="")

        response = router.query("Hello")
        assert "trouble connecting" in response

    def test_streaming_basic(self, router):
        """Test streaming query yields chunks"""
        mock_chunk1 = MagicMock()
        mock_chunk1.text = "Hello "
        mock_chunk1.done = False
        mock_chunk1.source = "groq"

        mock_chunk2 = MagicMock()
        mock_chunk2.text = "world"
        mock_chunk2.done = False
        mock_chunk2.source = "groq"

        mock_chunk3 = MagicMock()
        mock_chunk3.text = ""
        mock_chunk3.done = True
        mock_chunk3.source = "groq"

        router.provider_manager.get_best_model.return_value = {
            'model_id': 'test', 'provider_id': 'groq',
            'model_name': 'Test', 'tier': 'fast',
        }
        router.provider_manager.stream.return_value = iter([mock_chunk1, mock_chunk2, mock_chunk3])

        chunks = []
        for data in router.stream_query("Stream test"):
            if data.get('chunk'):
                chunks.append(data['chunk'])

        assert "Hello " in chunks
        assert "world" in chunks

    def test_web_search_detection(self, router):
        """Test _is_knowledge_query for real-time data detection"""
        # Should trigger — temporal/live data
        assert router._is_knowledge_query("latest news about AI") is True
        assert router._is_knowledge_query("weather in Chennai") is True
        assert router._is_knowledge_query("stock price of Apple") is True
        assert router._is_knowledge_query("what happened today") is True

        # Should NOT trigger — conceptual questions
        assert router._is_knowledge_query("thanks") is False
        assert router._is_knowledge_query("goodbye") is False
        assert router._is_knowledge_query("hello") is False

    def test_get_status(self, router):
        """Test get_status returns provider info"""
        status = router.get_status()
        assert isinstance(status, dict)

    def test_clear_history(self, router):
        """Test clearing conversation history"""
        router.provider_manager.conversation_history = [{"role": "user", "content": "test"}]
        router.clear_history()
        assert router.provider_manager.conversation_history == []

    def test_clear_cache(self, router):
        """Test clearing response cache"""
        router.cache = {"test": "cached"}
        router.clear_cache()
        assert router.cache == {}

    def test_set_phase2_model(self, router):
        """Test forcing a specific model"""
        router.model_registry = MagicMock()
        router.model_registry.get_model.return_value = MagicMock(name="Test Model", provider="groq")
        router.set_phase2_model("test-model")
        assert router._phase2_forced_model == "test-model"

    def test_get_backend_from_name_auto(self, router):
        """Test get_backend_from_name with auto clears forced model"""
        router._phase2_forced_model = "some-model"
        result = router.get_backend_from_name("auto")
        assert result is None
        assert router._phase2_forced_model is None

    def test_get_all_available_models_uses_live_provider_health(self, router):
        """Dropdown availability should reflect current provider health, including local providers."""
        router.model_registry = MagicMock()
        router.model_registry.to_dropdown_items.return_value = [
            {
                "id": "llama-local",
                "name": "Llama 3.1",
                "provider": "ollama-local",
                "available": True,
            },
            {
                "id": "gemini-2.5",
                "name": "Gemini 2.5 (offline)",
                "provider": "google",
                "available": False,
            },
        ]

        local_provider = MagicMock()
        local_provider.ensure_available.return_value = False
        cloud_provider = MagicMock()
        cloud_provider.ensure_available.return_value = True
        router.provider_manager.providers = {
            "ollama-local": local_provider,
            "google": cloud_provider,
        }

        models = router.get_all_available_models()
        by_id = {item["id"]: item for item in models}

        assert by_id["llama-local"]["available"] is False
        assert by_id["llama-local"]["name"].endswith("(offline)")
        assert by_id["gemini-2.5"]["available"] is True
        assert "(offline)" not in by_id["gemini-2.5"]["name"].lower()

    def test_query_forced_model_unavailable_returns_offline_message(self, router):
        """Forced model should not silently fall back to another provider."""
        router.provider_manager.get_provider_for_model.return_value = None

        response = router.query("Hello", model="ollama-local-model")

        assert "unavailable" in response.lower() or "offline" in response.lower()
        router.provider_manager.get_best_model.assert_not_called()

    def test_stream_forced_model_unavailable_emits_terminal_error(self, router):
        """Streaming should end with explicit model-unavailable message when forced model is offline."""
        router.provider_manager.get_provider_for_model.return_value = None

        chunks = list(router.stream_query("Hello", model="ollama-local-model"))

        assert chunks
        final = chunks[-1]
        assert final.get("done") is True
        assert final.get("source") == "error"
        assert "unavailable" in final.get("chunk", "").lower() or "offline" in final.get("chunk", "").lower()

    def test_get_all_available_models_preserves_provider_without_ensure_available(self, router):
        """Providers without ensure_available should not be forced offline in dropdown output."""
        router.model_registry = MagicMock()
        router.model_registry.to_dropdown_items.return_value = [
            {
                "id": "custom-model",
                "name": "Custom Model",
                "provider": "custom-provider",
                "available": True,
            }
        ]

        provider_without_health_check = SimpleNamespace(is_available=True)
        router.provider_manager.providers = {
            "custom-provider": provider_without_health_check,
        }

        models = router.get_all_available_models()

        assert len(models) == 1
        assert models[0]["available"] is True
        assert "(offline)" not in models[0]["name"].lower()

    def test_conversation_history_property(self, router):
        """Test conversation_history property delegates to ProviderManager"""
        router.provider_manager.conversation_history = [{"role": "user", "content": "hi"}]
        assert len(router.conversation_history) == 1
        assert router.conversation_history[0]["content"] == "hi"

    def test_backward_compat_methods(self, router):
        """Test backward compatibility no-op methods don't crash"""
        router.force_backend(None)
        assert router.get_forced_backend() is None
        router._ensure_backends_checked()  # No-op
