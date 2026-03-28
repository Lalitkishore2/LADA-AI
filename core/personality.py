"""
LADA Personality System
Provides multiple personality modes with consistent phrase generation
"""
import random
import json
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)


class LadaPersonality:
    """
    Manages LADA's personality modes and response phrases.
    
    Supported modes:
    - JARVIS: British, formal, sophisticated (Tony Stark's AI)
    - FRIDAY: Modern, efficient, professional (Tony's successor AI)  
    - KAREN: Warm, friendly, supportive (Peter Parker's suit AI)
    - CASUAL: Relaxed, conversational, fun
    """
    
    # Current personality mode (default: JARVIS)
    _current_mode = "jarvis"
    
    # Loaded phrases
    _phrases: Dict[str, Dict[str, Any]] = {}
    
    @classmethod
    def _load_phrases(cls) -> Dict[str, Dict[str, Any]]:
        """Load personality phrases from JSON file"""
        if cls._phrases:
            return cls._phrases
            
        # Find phrases file
        project_root = Path(__file__).parent.parent
        phrases_file = project_root / "data" / "personality_phrases.json"
        
        if not phrases_file.exists():
            logger.error(f"Personality phrases file not found: {phrases_file}")
            # Return minimal fallback phrases
            return {
                "jarvis": {
                    "acknowledgments": ["Right away, sir."],
                    "greetings": {"morning": ["Good morning, sir."], "afternoon": ["Good afternoon, sir."], "evening": ["Good evening, sir."], "night": ["Good evening, sir."]},
                    "errors": ["I'm afraid there's been an issue."],
                    "not_understood": ["I beg your pardon, sir. Could you clarify?"],
                    "confirmations": ["Understood, sir."],
                    "status_updates": ["Sir, you should know that {info}."],
                    "warnings": ["Sir, I must advise caution. {warning}."],
                    "completion": ["Task completed, sir."]
                }
            }
        
        try:
            with open(phrases_file, 'r', encoding='utf-8') as f:
                cls._phrases = json.load(f)
                logger.info(f"[Personality] Loaded phrases for {len(cls._phrases)} modes")
                return cls._phrases
        except Exception as e:
            logger.error(f"Failed to load personality phrases: {e}")
            return {}
    
    @classmethod
    def set_mode(cls, mode: str) -> bool:
        """
        Set personality mode.
        
        Args:
            mode: One of 'jarvis', 'friday', 'karen', 'casual'
            
        Returns:
            True if mode was set successfully
        """
        mode = mode.lower()
        phrases = cls._load_phrases()
        
        if mode in phrases:
            cls._current_mode = mode
            logger.info(f"[Personality] Mode set to: {mode.upper()}")
            return True
        else:
            logger.warning(f"[Personality] Unknown mode: {mode}")
            return False
    
    @classmethod
    def get_mode(cls) -> str:
        """Get current personality mode"""
        return cls._current_mode
    
    @classmethod
    def _get_phrases(cls) -> Dict[str, Any]:
        """Get phrase dictionary for current mode"""
        all_phrases = cls._load_phrases()
        return all_phrases.get(cls._current_mode, all_phrases.get('jarvis', {}))
    
    @staticmethod
    def get_time_greeting() -> str:
        """Get appropriate greeting based on time of day"""
        hour = datetime.now().hour
        phrases = LadaPersonality._get_phrases()
        greetings = phrases.get('greetings', {})
        
        if 5 <= hour < 12:
            options = greetings.get('morning', ["Good morning."])
        elif 12 <= hour < 17:
            options = greetings.get('afternoon', ["Good afternoon."])
        elif 17 <= hour < 21:
            options = greetings.get('evening', ["Good evening."])
        else:
            options = greetings.get('night', ["Hello."])
        
        return random.choice(options)
    
    @staticmethod
    def get_acknowledgment() -> str:
        """Get acknowledgment phrase in current mode"""
        phrases = LadaPersonality._get_phrases()
        options = phrases.get('acknowledgments', ["Understood."])
        return random.choice(options)
    
    @staticmethod
    def get_error() -> str:
        """Get error phrase in current mode"""
        phrases = LadaPersonality._get_phrases()
        options = phrases.get('errors', ["Something went wrong."])
        return random.choice(options)
    
    @staticmethod
    def get_confirmation() -> str:
        """Get confirmation phrase in current mode"""
        phrases = LadaPersonality._get_phrases()
        options = phrases.get('confirmations', ["Understood."])
        return random.choice(options)
    
    @staticmethod
    def get_not_understood() -> str:
        """Get not understood phrase in current mode"""
        phrases = LadaPersonality._get_phrases()
        options = phrases.get('not_understood', ["I didn't understand."])
        return random.choice(options)
    
    @staticmethod
    def get_completion() -> str:
        """Get task completion phrase in current mode"""
        phrases = LadaPersonality._get_phrases()
        options = phrases.get('completion', ["Task complete."])
        return random.choice(options)
    
    @staticmethod
    def get_status_update(info: str) -> str:
        """Get status update phrase with info in current mode"""
        phrases = LadaPersonality._get_phrases()
        templates = phrases.get('status_updates', ["Update: {info}."])
        template = random.choice(templates)
        return template.format(info=info)
    
    @staticmethod
    def get_warning(warning: str) -> str:
        """Get warning phrase in current mode"""
        phrases = LadaPersonality._get_phrases()
        templates = phrases.get('warnings', ["Warning: {warning}."])
        template = random.choice(templates)
        return template.format(warning=warning)
    
    # Backward compatibility - expose phrase dictionaries
    @classmethod
    def get_all_phrases(cls) -> Dict[str, Any]:
        """Get all phrases for current mode (for backward compatibility)"""
        return cls._get_phrases()
    
    # Legacy phrase list access
    @property
    def ACKNOWLEDGMENTS(cls) -> list:
        """Backward compatibility: get acknowledgments list"""
        return cls._get_phrases().get('acknowledgments', [])
    
    @property
    def GREETINGS(cls) -> dict:
        """Backward compatibility: get greetings dict"""
        return cls._get_phrases().get('greetings', {})
    
    @property
    def ERRORS(cls) -> list:
        """Backward compatibility: get errors list"""
        return cls._get_phrases().get('errors', [])
    
    @property
    def NOT_UNDERSTOOD(cls) -> list:
        """Backward compatibility: get not_understood list"""
        return cls._get_phrases().get('not_understood', [])
    
    @property
    def CONFIRMATIONS(cls) -> list:
        """Backward compatibility: get confirmations list"""
        return cls._get_phrases().get('confirmations', [])


# For backward compatibility, expose at module level
def get_time_greeting() -> str:
    """Module-level function for time-based greeting"""
    return LadaPersonality.get_time_greeting()


def get_acknowledgment() -> str:
    """Module-level function for acknowledgment"""
    return LadaPersonality.get_acknowledgment()


def get_error() -> str:
    """Module-level function for error message"""
    return LadaPersonality.get_error()


def get_confirmation() -> str:
    """Module-level function for confirmation"""
    return LadaPersonality.get_confirmation()


def get_not_understood() -> str:
    """Module-level function for not understood message"""
    return LadaPersonality.get_not_understood()


def get_completion() -> str:
    """Module-level function for completion message"""
    return LadaPersonality.get_completion()


def get_status_update(info: str) -> str:
    """Module-level function for status update"""
    return LadaPersonality.get_status_update(info)


def get_warning(warning: str) -> str:
    """Module-level function for warning"""
    return LadaPersonality.get_warning(warning)


def set_personality_mode(mode: str) -> bool:
    """Module-level function to set personality mode"""
    return LadaPersonality.set_mode(mode)


def get_personality_mode() -> str:
    """Module-level function to get current personality mode"""
    return LadaPersonality.get_mode()
