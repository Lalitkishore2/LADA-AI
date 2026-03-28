"""
Tests for XTTS-v2 TTS Engine
"""

import pytest
from unittest.mock import MagicMock
import sys

# Mock heavy imports before loading module
sys.modules['TTS'] = MagicMock()
sys.modules['TTS.api'] = MagicMock()
sys.modules['torch'] = MagicMock()
sys.modules['torchaudio'] = MagicMock()

# Now import our module
from voice.xtts_engine import XTTSEngine, FallbackTTSEngine, get_xtts_engine


class TestXTTSEngine:
    """Test XTTS-v2 TTS Engine"""
    
    def test_engine_creation(self):
        """Test engine initializes"""
        engine = XTTSEngine()
        assert engine is not None
    
    def test_speak_method_exists(self):
        """Test speak method exists"""
        engine = XTTSEngine()
        assert hasattr(engine, 'speak')


class TestFallbackTTSEngine:
    """Test TTS fallback engine"""
    
    def test_fallback_creation(self):
        """Test fallback engine initializes"""
        engine = FallbackTTSEngine()
        assert engine is not None


class TestGetXTTSEngine:
    """Test module-level factory function"""
    
    def test_factory_returns_engine(self):
        """Test get_xtts_engine returns engine"""
        engine = get_xtts_engine()
        assert engine is not None
