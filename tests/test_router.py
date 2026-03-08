"""
LADA v9.0 - AI Router Tests
Tests for the hybrid AI routing system
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys

# Mock modules
sys.modules["modules.web_search"] = MagicMock()
sys.modules["google.genai"] = MagicMock()

from lada_ai_router import HybridAIRouter, AIBackend

class TestHybridAIRouter:
    """Test suite for AI router"""
    
    @pytest.fixture
    def router(self):
        with patch("lada_ai_router.HybridAIRouter._check_all_backends"):
            router = HybridAIRouter()
            # Disable Phase 2 so legacy backend mocks are used
            router._use_phase2 = False
            # Mock backends to be available with proper attributes
            mock_ollama = Mock()
            mock_ollama.available = True
            mock_ollama.last_check = 0.0
            mock_ollama.response_time = 0.1
            mock_ollama.name = "Local Ollama"
            mock_ollama.error = None
            
            mock_gemini = Mock()
            mock_gemini.available = True
            mock_gemini.last_check = 0.0
            mock_gemini.response_time = 0.2
            mock_gemini.name = "Gemini"
            mock_gemini.error = None
            
            router.backend_status = {
                AIBackend.LOCAL_OLLAMA: mock_ollama,
                AIBackend.GEMINI: mock_gemini
            }
            return router

    def test_router_initialization(self, router):
        """Test router initializes correctly"""
        assert router is not None
        assert hasattr(router, "backend_status")
    
    def test_query_basic(self, router):
        """Test basic query functionality"""
        with patch.object(router, "_query_ollama_local", return_value="Local response"):
            response = router.query("Hello")
            assert response == "Local response"
    
    def test_query_with_conversation(self, router):
        """Test query with conversation history"""
        with patch.object(router, "_query_ollama_local", return_value="Response"):
            router.conversation_history = [{"role": "user", "content": "Hi"}]
            response = router.query("Tell me more")
            assert response == "Response"
            assert len(router.conversation_history) == 3 # Hi, Tell me more, Response
    
    def test_streaming_query(self, router):
        """Test streaming query functionality"""
        # Mock _stream_ollama_local to yield chunks
        def mock_stream(prompt):
            yield {"chunk": "Chunk 1", "source": "local_ollama", "done": False}
            yield {"chunk": "Chunk 2", "source": "local_ollama", "done": True}
            
        with patch.object(router, "_stream_ollama_local", side_effect=mock_stream):
            chunks = []
            for chunk_data in router.stream_query("Stream test"):
                if "chunk" in chunk_data:
                    chunks.append(chunk_data["chunk"])
            
            assert len(chunks) == 2
            assert "Chunk 1" in chunks
            assert "Chunk 2" in chunks
    
    def test_backend_failover(self, router):
        """Test backend failover on error"""
        # Mock _query_ollama_local to fail, _query_gemini to succeed
        with patch.object(router, "_query_ollama_local", side_effect=Exception("Fail")), \
             patch.object(router, "_query_gemini", return_value="Gemini response"):
            
            # Ensure Gemini is in priority list
            with patch.object(router, "_get_backend_priority", return_value=[AIBackend.LOCAL_OLLAMA, AIBackend.GEMINI]):
                response = router.query("Test failover")
                
                assert response == "Gemini response"
                assert router.current_backend_name == "Google Gemini 2.0 Flash"
    
    def test_web_search_detection(self, router):
        """Test automatic web search detection"""
        # Should trigger web search
        knowledge_queries = [
            "what is Python",
            "who is Elon Musk",
            "tell me about SRM University",
            "where is Paris"
        ]
        
        for query in knowledge_queries:
            result = router._is_knowledge_query(query)
            assert result is True, f"Failed for query: {query}"
        
        # Should NOT trigger web search
        casual_queries = [
            "thanks",
            "goodbye"
        ]
        
        for query in casual_queries:
            result = router._is_knowledge_query(query)
            assert result is False, f"False positive for query: {query}"
    
    def test_backend_status(self, router):
        """Test backend status checking"""
        with patch.object(router, "_check_all_backends"):
            status = router.get_status()
            assert isinstance(status, dict)

