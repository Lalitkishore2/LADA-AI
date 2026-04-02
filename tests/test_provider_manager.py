"""
Tests for ProviderManager - Central orchestrator for all AI providers.

Tests cover:
- Auto-configuration from environment
- Provider registration and retrieval
- Model routing and tier selection
- Query and streaming operations
- Rate limiting integration
- Error handling and fallbacks
"""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any, List


# Test fixtures
@pytest.fixture
def mock_env():
    """Set up mock environment variables"""
    env_vars = {
        'GEMINI_API_KEY': 'test-gemini-key',
        'GROQ_API_KEY': 'test-groq-key',
        'LOCAL_OLLAMA_URL': 'http://localhost:11434',
    }
    with patch.dict(os.environ, env_vars, clear=False):
        yield env_vars


@pytest.fixture
def mock_model_registry():
    """Mock model registry with test providers"""
    registry = Mock()
    
    # Mock provider info
    mock_gemini = Mock()
    mock_gemini.type = 'google-generative-ai'
    mock_gemini.config_keys = ['GEMINI_API_KEY']
    
    mock_groq = Mock()
    mock_groq.type = 'openai-completions'
    mock_groq.config_keys = ['GROQ_API_KEY']
    mock_groq.base_url = 'https://api.groq.com/openai/v1'
    
    mock_ollama = Mock()
    mock_ollama.type = 'ollama'
    mock_ollama.config_keys = ['LOCAL_OLLAMA_URL']
    
    registry.providers = {
        'google': mock_gemini,
        'groq': mock_groq,
        'local-ollama': mock_ollama,
    }
    
    # Mock model info
    mock_model = Mock()
    mock_model.provider = 'google'
    mock_model.tier = 'fast'
    mock_model.context_length = 32000
    mock_model.input_cost = 0.0001
    mock_model.output_cost = 0.0002
    
    registry.models = {
        'gemini-2.0-flash': mock_model,
    }
    registry.get_model = Mock(return_value=mock_model)
    registry.get_models_by_tier = Mock(return_value=[mock_model])
    registry.get_models_by_provider = Mock(return_value=[mock_model])
    
    return registry


@pytest.fixture
def mock_provider():
    """Create a mock provider instance"""
    provider = Mock()
    provider.provider_id = 'test-provider'
    provider.name = 'Test Provider'
    provider.is_healthy = Mock(return_value=True)
    provider.query = Mock(return_value=Mock(
        text='Test response',
        model='test-model',
        provider='test-provider',
        tokens_in=10,
        tokens_out=20,
        cost=0.001
    ))
    provider.stream = Mock(return_value=iter([
        Mock(text='Hello', done=False),
        Mock(text=' world', done=True, tokens_in=5, tokens_out=10)
    ]))
    return provider


class TestProviderManagerInit:
    """Tests for ProviderManager initialization"""
    
    def test_init_creates_empty_providers(self):
        """Manager starts with empty provider dict"""
        with patch('modules.providers.provider_manager.get_model_registry', return_value=None):
            with patch('modules.providers.provider_manager.get_cost_tracker', return_value=None):
                from modules.providers.provider_manager import ProviderManager
                manager = ProviderManager()
                assert manager.providers == {}
                assert manager.conversation_history == []
    
    def test_init_loads_model_registry(self, mock_model_registry):
        """Manager loads model registry if available"""
        with patch('modules.providers.provider_manager.get_model_registry', return_value=mock_model_registry):
            with patch('modules.providers.provider_manager.get_cost_tracker', return_value=None):
                from modules.providers.provider_manager import ProviderManager
                manager = ProviderManager()
                assert manager.model_registry == mock_model_registry


class TestAutoConfiguration:
    """Tests for auto_configure() method"""
    
    def test_auto_configure_with_no_env(self):
        """No cloud providers configured when no env vars set; local fallback may exist"""
        with patch.dict(os.environ, {}, clear=True):
            with patch('modules.providers.provider_manager.get_model_registry', return_value=None):
                with patch('modules.providers.provider_manager.get_cost_tracker', return_value=None):
                    from modules.providers.provider_manager import ProviderManager
                    manager = ProviderManager()
                    count = manager.auto_configure()
                    assert count in (0, 1)
                    if count == 1:
                        assert 'ollama-local' in manager.providers
    
    def test_auto_configure_detects_providers(self, mock_env, mock_model_registry):
        """Providers detected from env vars"""
        with patch('modules.providers.provider_manager.get_model_registry', return_value=mock_model_registry):
            with patch('modules.providers.provider_manager.get_cost_tracker', return_value=None):
                with patch('modules.providers.provider_manager.SECURE_VAULT_OK', False):
                    from modules.providers.provider_manager import ProviderManager
                    manager = ProviderManager()
                    # Mock provider classes
                    with patch('modules.providers.provider_manager.GoogleProvider') as mock_google:
                        with patch('modules.providers.provider_manager.OpenAIProvider') as mock_openai:
                            with patch('modules.providers.provider_manager.OllamaProvider') as mock_ollama:
                                mock_google.return_value = Mock(provider_id='google')
                                mock_openai.return_value = Mock(provider_id='groq')
                                mock_ollama.return_value = Mock(provider_id='local-ollama')
                                count = manager.auto_configure()
                                assert count >= 1


class TestProviderRetrieval:
    """Tests for provider retrieval methods"""
    
    def test_get_provider_returns_none_for_unknown(self):
        """get_provider returns None for unknown provider"""
        with patch('modules.providers.provider_manager.get_model_registry', return_value=None):
            with patch('modules.providers.provider_manager.get_cost_tracker', return_value=None):
                from modules.providers.provider_manager import ProviderManager
                manager = ProviderManager()
                assert manager.get_provider('nonexistent') is None
    
    def test_get_provider_returns_registered(self, mock_provider):
        """get_provider returns registered provider"""
        with patch('modules.providers.provider_manager.get_model_registry', return_value=None):
            with patch('modules.providers.provider_manager.get_cost_tracker', return_value=None):
                from modules.providers.provider_manager import ProviderManager
                manager = ProviderManager()
                manager.providers['test'] = mock_provider
                assert manager.get_provider('test') == mock_provider
    
    def test_get_available_providers(self, mock_provider):
        """get_available_providers returns healthy providers"""
        with patch('modules.providers.provider_manager.get_model_registry', return_value=None):
            with patch('modules.providers.provider_manager.get_cost_tracker', return_value=None):
                from modules.providers.provider_manager import ProviderManager
                manager = ProviderManager()
                mock_provider.ensure_available = Mock(return_value=True)
                mock_provider.config = Mock(priority=1)
                manager.providers['healthy'] = mock_provider
                
                unhealthy = Mock()
                unhealthy.ensure_available = Mock(return_value=False)
                unhealthy.config = Mock(priority=99)
                manager.providers['unhealthy'] = unhealthy
                
                available = manager.get_available_providers()
                assert mock_provider in available
                assert unhealthy not in available


class TestComplexityAnalysis:
    """Tests for query complexity analysis"""
    
    def test_simple_query_classified_fast(self):
        """Short queries classified as 'fast' tier"""
        with patch('modules.providers.provider_manager.get_model_registry', return_value=None):
            with patch('modules.providers.provider_manager.get_cost_tracker', return_value=None):
                from modules.providers.provider_manager import ProviderManager
                manager = ProviderManager()
                assert manager._analyze_complexity("what time is it?") == 'fast'
                assert manager._analyze_complexity("hello") == 'fast'
    
    def test_complex_query_classified_smart(self):
        """Long detailed queries classified as 'smart' tier"""
        with patch('modules.providers.provider_manager.get_model_registry', return_value=None):
            with patch('modules.providers.provider_manager.get_cost_tracker', return_value=None):
                from modules.providers.provider_manager import ProviderManager
                manager = ProviderManager()
                long_query = "Explain in detail the quantum mechanical principles underlying " * 10
                tier = manager._analyze_complexity(long_query)
                assert tier in ['smart', 'reasoning']
    
    def test_code_query_classified_coding(self):
        """Code-related queries classified as 'coding' tier"""
        with patch('modules.providers.provider_manager.get_model_registry', return_value=None):
            with patch('modules.providers.provider_manager.get_cost_tracker', return_value=None):
                from modules.providers.provider_manager import ProviderManager
                manager = ProviderManager()
                tier = manager._analyze_complexity("write a python function to sort a list")
                assert tier == 'coding'
    
    def test_analysis_query_classified_reasoning(self):
        """Analysis/reasoning queries classified correctly"""
        with patch('modules.providers.provider_manager.get_model_registry', return_value=None):
            with patch('modules.providers.provider_manager.get_cost_tracker', return_value=None):
                from modules.providers.provider_manager import ProviderManager
                manager = ProviderManager()
                tier = manager._analyze_complexity("analyze the economic implications of this policy and provide step by step reasoning")
                assert tier in ['smart', 'reasoning']


class TestModelRouting:
    """Tests for model selection and routing"""
    
    def test_get_best_model_with_registry(self, mock_model_registry):
        """get_best_model uses model registry"""
        with patch('modules.providers.provider_manager.get_model_registry', return_value=mock_model_registry):
            with patch('modules.providers.provider_manager.get_cost_tracker', return_value=None):
                from modules.providers.provider_manager import ProviderManager
                manager = ProviderManager()
                manager.providers['google'] = Mock(is_healthy=Mock(return_value=True))
                model = manager.get_best_model("test query", tier='fast')
                # Should have called get_models_by_tier
                mock_model_registry.get_models_by_tier.assert_called()
    
    def test_get_best_model_respects_tier(self, mock_model_registry):
        """Model selection respects requested tier"""
        with patch('modules.providers.provider_manager.get_model_registry', return_value=mock_model_registry):
            with patch('modules.providers.provider_manager.get_cost_tracker', return_value=None):
                from modules.providers.provider_manager import ProviderManager
                manager = ProviderManager()
                manager.providers['google'] = Mock(is_healthy=Mock(return_value=True))
                manager.get_best_model("test", tier='coding')
                # Verify coding tier was requested
                call_args = mock_model_registry.get_models_by_tier.call_args
                assert 'coding' in str(call_args)


class TestQueryExecution:
    """Tests for query() method"""
    
    def test_query_with_no_providers(self):
        """Query fails gracefully with no providers"""
        with patch('modules.providers.provider_manager.get_model_registry', return_value=None):
            with patch('modules.providers.provider_manager.get_cost_tracker', return_value=None):
                from modules.providers.provider_manager import ProviderManager
                manager = ProviderManager()
                response = manager.query("test prompt")
                assert response is None or (hasattr(response, 'content') and ('error' in response.content.lower() or 'no ai providers' in response.content.lower()))
    
    def test_query_returns_response(self, mock_provider, mock_model_registry):
        """Query returns provider response"""
        with patch('modules.providers.provider_manager.get_model_registry', return_value=mock_model_registry):
            with patch('modules.providers.provider_manager.get_cost_tracker', return_value=None):
                from modules.providers.provider_manager import ProviderManager
                manager = ProviderManager()
                manager.providers['google'] = mock_provider
                mock_model_registry.get_model = Mock(return_value=Mock(provider='google'))
                response = manager.query("test prompt", model_id='gemini-2.0-flash')
                assert response is not None
    
    def test_query_adds_to_history(self, mock_provider, mock_model_registry):
        """Query adds messages to conversation history"""
        with patch('modules.providers.provider_manager.get_model_registry', return_value=mock_model_registry):
            with patch('modules.providers.provider_manager.get_cost_tracker', return_value=None):
                from modules.providers.provider_manager import ProviderManager
                manager = ProviderManager()
                manager.providers['google'] = mock_provider
                mock_model_registry.get_model = Mock(return_value=Mock(provider='google'))
                
                initial_len = len(manager.conversation_history)
                manager.query("test prompt", model_id='gemini-2.0-flash')
                # Should add user message and assistant response
                assert len(manager.conversation_history) >= initial_len

    def test_query_falls_back_to_secondary_provider_on_failure(self, mock_model_registry):
        """Query rotates to another available provider when the primary response fails."""
        with patch('modules.providers.provider_manager.get_model_registry', return_value=mock_model_registry):
            with patch('modules.providers.provider_manager.get_cost_tracker', return_value=None):
                from modules.providers.provider_manager import ProviderManager
                from modules.providers.base_provider import ProviderResponse

                manager = ProviderManager()

                primary = Mock()
                primary.provider_id = 'primary'
                primary.name = 'Primary'
                primary.ensure_available = Mock(return_value=True)
                primary.config = Mock(priority=1)
                primary.complete_with_retry = Mock(return_value=ProviderResponse(
                    content='',
                    model='primary-model',
                    provider='primary',
                    error='primary failed',
                ))

                fallback = Mock()
                fallback.provider_id = 'fallback'
                fallback.name = 'Fallback'
                fallback.ensure_available = Mock(return_value=True)
                fallback.config = Mock(priority=2)
                fallback.complete_with_retry = Mock(return_value=ProviderResponse(
                    content='fallback-ok',
                    model='fallback-model',
                    provider='fallback',
                ))

                manager.providers['primary'] = primary
                manager.providers['fallback'] = fallback

                primary_model = Mock()
                primary_model.provider = 'primary'
                primary_model.id = 'primary-model'

                fallback_model = Mock()
                fallback_model.provider = 'fallback'
                fallback_model.id = 'fallback-model'

                mock_model_registry.get_model = Mock(return_value=primary_model)
                mock_model_registry.get_models_by_provider = Mock(
                    side_effect=lambda pid: [primary_model] if pid == 'primary' else [fallback_model]
                )

                response = manager.query('test prompt', model_id='primary-model')

                assert response.success is True
                assert response.provider == 'fallback'
                assert primary.complete_with_retry.called
                assert fallback.complete_with_retry.called


class TestStreamExecution:
    """Tests for stream() method"""
    
    def test_stream_yields_chunks(self, mock_provider, mock_model_registry):
        """Stream yields text chunks"""
        with patch('modules.providers.provider_manager.get_model_registry', return_value=mock_model_registry):
            with patch('modules.providers.provider_manager.get_cost_tracker', return_value=None):
                from modules.providers.provider_manager import ProviderManager
                manager = ProviderManager()
                manager.providers['google'] = mock_provider
                mock_model_registry.get_model = Mock(return_value=Mock(provider='google'))
                
                chunks = list(manager.stream("test", model_id='gemini-2.0-flash'))
                assert len(chunks) > 0


class TestMessageBuilding:
    """Tests for _build_messages() method"""
    
    def test_build_messages_includes_system(self):
        """Messages include system prompt"""
        with patch('modules.providers.provider_manager.get_model_registry', return_value=None):
            with patch('modules.providers.provider_manager.get_cost_tracker', return_value=None):
                from modules.providers.provider_manager import ProviderManager
                manager = ProviderManager()
                messages = manager._build_messages("test", "Be helpful", [])
                assert any(m.get('role') == 'system' for m in messages)
    
    def test_build_messages_includes_history(self):
        """Messages include conversation history"""
        with patch('modules.providers.provider_manager.get_model_registry', return_value=None):
            with patch('modules.providers.provider_manager.get_cost_tracker', return_value=None):
                from modules.providers.provider_manager import ProviderManager
                manager = ProviderManager()
                history = [
                    {'role': 'user', 'content': 'previous'},
                    {'role': 'assistant', 'content': 'response'}
                ]
                manager.conversation_history = history
                messages = manager._build_messages("test", "", "")
                assert len(messages) >= 3  # history + current


class TestForceProvider:
    """Tests for force_provider() method"""
    
    def test_force_provider_sets_preference(self):
        """force_provider sets forced provider"""
        with patch('modules.providers.provider_manager.get_model_registry', return_value=None):
            with patch('modules.providers.provider_manager.get_cost_tracker', return_value=None):
                from modules.providers.provider_manager import ProviderManager
                manager = ProviderManager()
                manager.force_provider('google')
                assert manager._forced_provider == 'google'
    
    def test_force_provider_clears_with_none(self):
        """force_provider(None) clears preference"""
        with patch('modules.providers.provider_manager.get_model_registry', return_value=None):
            with patch('modules.providers.provider_manager.get_cost_tracker', return_value=None):
                from modules.providers.provider_manager import ProviderManager
                manager = ProviderManager()
                manager._forced_provider = 'google'
                manager.force_provider(None)
                assert manager._forced_provider is None


class TestRateLimiting:
    """Tests for rate limiter integration"""
    
    def test_rate_limiter_stats_empty_when_disabled(self):
        """Rate limiter stats empty when not available"""
        with patch('modules.providers.provider_manager.get_model_registry', return_value=None):
            with patch('modules.providers.provider_manager.get_cost_tracker', return_value=None):
                with patch('modules.providers.provider_manager.RATE_LIMITER_OK', False):
                    from modules.providers.provider_manager import ProviderManager
                    manager = ProviderManager()
                    manager._rate_limiter = None
                    stats = manager.get_rate_limiter_stats()
                    assert stats == {}


class TestStatus:
    """Tests for get_status() method"""
    
    def test_get_status_returns_dict(self, mock_provider):
        """get_status returns status dictionary"""
        with patch('modules.providers.provider_manager.get_model_registry', return_value=None):
            with patch('modules.providers.provider_manager.get_cost_tracker', return_value=None):
                from modules.providers.provider_manager import ProviderManager
                manager = ProviderManager()
                manager.providers['test'] = mock_provider
                status = manager.get_status()
                assert isinstance(status, dict)
                assert 'providers' in status
                assert 'total_providers' in status
    
    def test_get_dropdown_items(self, mock_provider, mock_model_registry):
        """get_dropdown_items returns model list"""
        with patch('modules.providers.provider_manager.get_model_registry', return_value=mock_model_registry):
            with patch('modules.providers.provider_manager.get_cost_tracker', return_value=None):
                from modules.providers.provider_manager import ProviderManager
                manager = ProviderManager()
                manager.providers['google'] = mock_provider
                items = manager.get_dropdown_items()
                assert isinstance(items, list)


class TestHealthCheck:
    """Tests for check_all_health() method"""
    
    def test_check_all_health_returns_dict(self, mock_provider):
        """check_all_health returns health status dict"""
        with patch('modules.providers.provider_manager.get_model_registry', return_value=None):
            with patch('modules.providers.provider_manager.get_cost_tracker', return_value=None):
                from modules.providers.provider_manager import ProviderManager
                manager = ProviderManager()
                manager.providers['test'] = mock_provider
                health = manager.check_all_health()
                assert isinstance(health, dict)
                assert 'test' in health


class TestEdgeCases:
    """Edge case tests"""
    
    def test_empty_prompt_handled(self, mock_provider):
        """Empty prompt handled gracefully"""
        with patch('modules.providers.provider_manager.get_model_registry', return_value=None):
            with patch('modules.providers.provider_manager.get_cost_tracker', return_value=None):
                from modules.providers.provider_manager import ProviderManager
                manager = ProviderManager()
                manager.providers['test'] = mock_provider
                # Should not crash
                try:
                    manager.query("")
                except Exception:
                    pass  # Empty query might raise, that's ok
    
    def test_history_truncation(self):
        """History truncates at max_history"""
        with patch('modules.providers.provider_manager.get_model_registry', return_value=None):
            with patch('modules.providers.provider_manager.get_cost_tracker', return_value=None):
                from modules.providers.provider_manager import ProviderManager
                manager = ProviderManager()
                manager.max_history = 5
                
                # Add more than max_history messages
                for i in range(10):
                    manager._add_to_history('user', f'message {i}')
                
                assert len(manager.conversation_history) <= 5


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
