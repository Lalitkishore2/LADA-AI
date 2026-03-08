# nlu_engine.py
# Advanced Natural Language Understanding with spaCy & Gemini
# Replaces simple keyword matching with intelligent intent classification

import spacy
from typing import Dict, List, Tuple, Any
import re
from difflib import SequenceMatcher
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class SensitiveDataDetector:
    """Detect sensitive information in text"""
    
    PATTERNS = {
        'password': r'(?:password|pwd|pass)\s*[:=]\s*[^\s]+',
        'credit_card': r'\b(?:\d{4}[-\s]?){3}\d{4}\b',
        'ssn': r'\b\d{3}-\d{2}-\d{4}\b',
        'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        'phone': r'\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b',
        'bank_account': r'(?:account|acct)\s*[:=]\s*\d{8,17}',
        'api_key': r'(?:api[_-]?key|token)\s*[:=]\s*[a-zA-Z0-9_-]+',
    }
    
    @classmethod
    def detect(cls, text: str) -> Dict[str, List[str]]:
        """Detect sensitive data in text"""
        found = {}
        for data_type, pattern in cls.PATTERNS.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                found[data_type] = matches
        return found
    
    @classmethod
    def redact(cls, text: str) -> str:
        """Replace sensitive data with [REDACTED]"""
        for data_type, pattern in cls.PATTERNS.items():
            text = re.sub(pattern, '[REDACTED]', text, flags=re.IGNORECASE)
        return text


class NLUEngine:
    """Advanced Natural Language Understanding"""
    
    def __init__(self):
        """Initialize NLU engine with spaCy model"""
        try:
            self.nlp = spacy.load("en_core_web_sm")
            logger.info("spaCy model loaded successfully")
        except OSError:
            logger.warning("spaCy model not found. Install with: python -m spacy download en_core_web_sm")
            self.nlp = None
        
        # Intent patterns (intent_name → keywords)
        self.intent_patterns = {
            'file_operation': {
                'keywords': ['open', 'create', 'delete', 'remove', 'move', 'copy', 'rename', 'search', 'find', 'read'],
                'entity_types': ['FILE', 'FOLDER', 'DOCUMENT'],
                'slots': ['source', 'destination', 'filename', 'extension']
            },
            'system_control': {
                'keywords': ['volume', 'brightness', 'wifi', 'bluetooth', 'sleep', 'shutdown', 'restart', 'power'],
                'entity_types': ['SETTING', 'VALUE'],
                'slots': ['setting_name', 'value', 'device']
            },
            'app_control': {
                'keywords': ['open', 'close', 'start', 'launch', 'run', 'quit', 'exit', 'click', 'type', 'fill'],
                'entity_types': ['APPLICATION', 'WINDOW', 'ELEMENT'],
                'slots': ['app_name', 'action', 'target']
            },
            'task_execution': {
                'keywords': ['download', 'extract', 'compress', 'convert', 'process', 'execute', 'run'],
                'entity_types': ['FILE', 'URL', 'DESTINATION'],
                'slots': ['action', 'object', 'parameters']
            },
            'information': {
                'keywords': ['what', 'where', 'how', 'tell', 'show', 'display', 'is', 'are', 'status'],
                'entity_types': ['QUERY', 'SUBJECT'],
                'slots': ['query_type', 'subject']
            },
            'memory': {
                'keywords': ['remember', 'recall', 'yesterday', 'last', 'previous', 'again', 'do it again'],
                'entity_types': ['TEMPORAL', 'REFERENCE'],
                'slots': ['time_reference', 'action_reference']
            }
        }
        
        # Application database
        self.known_apps = {
            'chrome': ['google chrome', 'chrome browser'],
            'firefox': ['firefox browser', 'mozilla firefox'],
            'edge': ['microsoft edge', 'edge browser'],
            'notepad': ['notepad text editor'],
            'word': ['microsoft word', 'word document'],
            'excel': ['microsoft excel', 'excel spreadsheet'],
            'explorer': ['file explorer', 'windows explorer'],
            'spotify': ['spotify music'],
            'vlc': ['vlc media player', 'vlc player'],
        }
        
        # Common entities
        self.entity_replacements = {
            'download folder': r'C:\Users\[user]\Downloads',
            'documents': r'C:\Users\[user]\Documents',
            'desktop': r'C:\Users\[user]\Desktop',
            'pictures': r'C:\Users\[user]\Pictures',
        }
    
    def process(self, text: str, context: Dict = None) -> Dict[str, Any]:
        """
        Process user input and return structured intent
        
        Returns:
        {
            'intent': 'file_operation',
            'confidence': 0.92,
            'entities': {'file': 'document.pdf', 'action': 'open'},
            'slots': {'source': 'document.pdf'},
            'requires_confirmation': False,
            'sensitive_data': []
        }
        """
        context = context or {}
        
        # Detect sensitive data
        sensitive = SensitiveDataDetector.detect(text)
        if sensitive:
            logger.warning(f"Sensitive data detected: {list(sensitive.keys())}")
            redacted_text = SensitiveDataDetector.redact(text)
        else:
            redacted_text = text
        
        # Resolve pronouns and coreferences
        resolved_text = self._resolve_coreference(text, context.get('history', []))
        
        # Classify intent using spaCy + pattern matching
        intent_result = self._classify_intent(resolved_text)
        
        # Extract entities
        entities = self._extract_entities(resolved_text)
        
        # Fill missing slots from context
        slots = self._fill_slots(intent_result['intent'], entities, context)
        
        # Check if destructive (needs confirmation)
        requires_confirmation = self._check_destructive(intent_result['intent'], entities)
        
        return {
            'original_text': text,
            'processed_text': redacted_text,
            'resolved_text': resolved_text,
            'intent': intent_result['intent'],
            'confidence': intent_result['confidence'],
            'entities': entities,
            'slots': slots,
            'requires_confirmation': requires_confirmation,
            'sensitive_data': sensitive,
            'timestamp': datetime.now().isoformat()
        }
    
    def _resolve_coreference(self, text: str, history: List[str]) -> str:
        """
        Resolve pronouns and coreferences
        
        Examples:
        - "open it" → resolve "it" to previous object
        - "do it again" → resolve to previous action
        - "that file" → resolve to recently mentioned file
        """
        resolved = text.lower()
        
        # Handle "it", "that", "this"
        if ('it' in resolved or 'that' in resolved) and history:
            last_action = history[-1] if history else ""
            # Extract noun from last action
            if self.nlp:
                doc = self.nlp(last_action)
                for token in doc:
                    if token.pos_ in ['NOUN', 'PROPN']:
                        resolved = resolved.replace('it', token.text)
                        resolved = resolved.replace('that', token.text)
                        break
        
        # Handle "do it again"
        if 'do it again' in resolved or 'again' in resolved:
            if history:
                resolved = history[-1]
        
        # Handle temporal references
        temporal_map = {
            'yesterday': (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'),
            'last week': (datetime.now() - timedelta(weeks=1)).strftime('%Y-%m-%d'),
            'today': datetime.now().strftime('%Y-%m-%d'),
        }
        for key, value in temporal_map.items():
            if key in resolved:
                resolved = resolved.replace(key, value)
        
        return resolved
    
    def _classify_intent(self, text: str) -> Dict[str, Any]:
        """Classify user intent using spaCy + fuzzy matching"""
        text_lower = text.lower()
        best_intent = None
        best_confidence = 0
        
        # Score each intent
        for intent_name, intent_data in self.intent_patterns.items():
            # Count keyword matches
            keyword_matches = sum(1 for kw in intent_data['keywords'] if kw in text_lower)
            
            if keyword_matches > 0:
                # Confidence based on keyword density
                confidence = min(0.99, keyword_matches / len(intent_data['keywords']))
                
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_intent = intent_name
        
        # If no keyword match, try spaCy semantic similarity
        if best_intent is None and self.nlp:
            doc = self.nlp(text)
            # Use verb-based classification
            for token in doc:
                if token.pos_ == 'VERB':
                    for intent_name, intent_data in self.intent_patterns.items():
                        if token.text in intent_data['keywords']:
                            best_intent = intent_name
                            best_confidence = 0.7
                            break
        
        return {
            'intent': best_intent or 'information',
            'confidence': best_confidence or 0.5
        }
    
    def _extract_entities(self, text: str) -> Dict[str, List[str]]:
        """Extract named entities from text"""
        entities = {}
        
        if not self.nlp:
            return entities
        
        doc = self.nlp(text)
        
        # Extract spaCy entities
        for ent in doc.ents:
            if ent.label_ not in entities:
                entities[ent.label_] = []
            entities[ent.label_].append(ent.text)
        
        # Extract application names with fuzzy matching
        text_lower = text.lower()
        for app_name, aliases in self.known_apps.items():
            for alias in aliases:
                if self._fuzzy_match(alias, text_lower)[1] > 0.8:
                    if 'APPLICATION' not in entities:
                        entities['APPLICATION'] = []
                    if app_name not in entities['APPLICATION']:
                        entities['APPLICATION'].append(app_name)
        
        # Extract file references
        file_patterns = r'\b\w+\.\w+\b'  # matches: file.txt, image.jpg, etc.
        file_matches = re.findall(file_patterns, text)
        if file_matches:
            entities['FILE'] = file_matches
        
        # Extract folder/directory references
        folder_keywords = ['folder', 'directory', 'path', 'location']
        if any(kw in text.lower() for kw in folder_keywords):
            entities['FOLDER'] = ['<current_directory>']
        
        return entities
    
    def _fill_slots(self, intent: str, entities: Dict, context: Dict) -> Dict[str, str]:
        """Fill command slots from entities and context"""
        slots = {}
        
        # Define slot requirements per intent
        slot_requirements = {
            'file_operation': ['action', 'target'],
            'system_control': ['setting_name', 'value'],
            'app_control': ['app_name', 'action'],
            'task_execution': ['action', 'object'],
        }
        
        required_slots = slot_requirements.get(intent, [])
        
        # Try to fill from entities
        for slot in required_slots:
            if slot == 'action':
                # Extract from verbs
                if self.nlp:
                    doc = self.nlp(' '.join(entities.keys()))
                    for token in doc:
                        if token.pos_ == 'VERB':
                            slots['action'] = token.text
                            break
            
            elif slot == 'target':
                if 'FILE' in entities and entities['FILE']:
                    slots['target'] = entities['FILE'][0]
                elif 'FOLDER' in entities and entities['FOLDER']:
                    slots['target'] = entities['FOLDER'][0]
            
            elif slot == 'app_name':
                if 'APPLICATION' in entities and entities['APPLICATION']:
                    slots['app_name'] = entities['APPLICATION'][0]
            
            elif slot == 'setting_name':
                setting_keywords = ['volume', 'brightness', 'wifi', 'bluetooth']
                for keyword in setting_keywords:
                    if keyword in ' '.join(entities.keys()).lower():
                        slots['setting_name'] = keyword
                        break
            
            elif slot == 'value':
                # Extract numbers
                numbers = re.findall(r'\d+', ' '.join(entities.keys()))
                if numbers:
                    slots['value'] = numbers[0]
        
        # Fill missing slots from context
        if context:
            for slot in required_slots:
                if slot not in slots and slot in context:
                    slots[slot] = context[slot]
        
        return slots
    
    def _check_destructive(self, intent: str, entities: Dict) -> bool:
        """Check if command is destructive (delete, format, etc.)"""
        destructive_keywords = ['delete', 'remove', 'format', 'clear', 'uninstall', 'disable']
        return intent == 'file_operation' and any(kw in str(entities).lower() for kw in destructive_keywords)
    
    def _fuzzy_match(self, reference: str, text: str) -> Tuple[str, float]:
        """
        Fuzzy match with typo tolerance
        
        Returns: (best_match, confidence)
        """
        words = text.split()
        best_match = None
        best_ratio = 0
        
        for word in words:
            ratio = SequenceMatcher(None, reference.lower(), word.lower()).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = word
        
        return best_match or reference, best_ratio
    
    def suggest_command(self, text: str) -> str:
        """Suggest corrected command if typos detected"""
        # Placeholder for future enhancement
        return text


# Example usage
if __name__ == "__main__":
    engine = NLUEngine()
    
    # Test cases
    test_commands = [
        "open the file I downloaded yesterday",
        "delete all PDF files in downloads",
        "set volume to 50 percent",
        "download this file and extract it",
        "show me my system status",
    ]
    
    for cmd in test_commands:
        result = engine.process(cmd)
        print(f"\nCommand: {cmd}")
        print(f"Intent: {result['intent']} ({result['confidence']:.2%})")
        print(f"Entities: {result['entities']}")
        print(f"Slots: {result['slots']}")
