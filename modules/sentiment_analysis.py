"""
LADA v10.0 - Sentiment Analysis Module
Detect user mood and emotion for empathetic responses

Features:
- Text sentiment analysis (positive/negative/neutral)
- Emotion detection (happy, sad, angry, frustrated, stressed)
- Mood tracking over time
- Adaptive response recommendations
- Stress level detection from typing patterns
- Integration with memory system
"""

import re
import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from collections import deque

logger = logging.getLogger(__name__)

# Try to import TextBlob for sentiment analysis
try:
    from textblob import TextBlob
    TEXTBLOB_OK = True
except ImportError:
    TextBlob = None
    TEXTBLOB_OK = False
    logger.warning("TextBlob not installed. Install with: pip install textblob")


class Sentiment(Enum):
    """Sentiment categories"""
    VERY_POSITIVE = "very_positive"
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    VERY_NEGATIVE = "very_negative"


class Emotion(Enum):
    """Detected emotions"""
    HAPPY = "happy"
    EXCITED = "excited"
    GRATEFUL = "grateful"
    CURIOUS = "curious"
    NEUTRAL = "neutral"
    CONFUSED = "confused"
    FRUSTRATED = "frustrated"
    STRESSED = "stressed"
    SAD = "sad"
    ANGRY = "angry"
    TIRED = "tired"


@dataclass
class SentimentResult:
    """Result from sentiment analysis"""
    sentiment: Sentiment
    emotion: Emotion
    confidence: float  # 0.0 to 1.0
    polarity: float   # -1.0 to 1.0
    subjectivity: float  # 0.0 to 1.0
    stress_level: str  # low, medium, high
    keywords: List[str] = field(default_factory=list)
    recommended_tone: str = "neutral"  # How LADA should respond


class SentimentAnalyzer:
    """
    Analyzes user text to detect sentiment, emotion, and stress levels.
    Provides recommendations for empathetic responses.
    """
    
    # Emotion keyword patterns
    EMOTION_KEYWORDS = {
        Emotion.HAPPY: [
            'happy', 'great', 'awesome', 'amazing', 'wonderful', 'fantastic',
            'excellent', 'perfect', 'love', 'joy', 'excited', 'glad', 'pleased',
            'delighted', 'thrilled', 'yay', 'woohoo', 'nice', 'good'
        ],
        Emotion.EXCITED: [
            'excited', 'cant wait', "can't wait", 'thrilled', 'pumped',
            'stoked', 'eager', 'looking forward', 'amazing', '!!'
        ],
        Emotion.GRATEFUL: [
            'thank', 'thanks', 'appreciate', 'grateful', 'thankful',
            'helped', 'awesome', 'saved my', 'lifesaver'
        ],
        Emotion.CURIOUS: [
            'how', 'what', 'why', 'when', 'where', 'who', 'which',
            'wondering', 'curious', 'interested', 'tell me', 'explain',
            'show me', 'help me understand', '?'
        ],
        Emotion.CONFUSED: [
            'confused', "don't understand", 'dont understand', 'unclear',
            "doesn't make sense", 'doesnt make sense', 'lost', 'huh',
            'what do you mean', 'not sure', 'confusing', '???'
        ],
        Emotion.FRUSTRATED: [
            'frustrated', 'annoying', 'annoyed', "doesn't work", 'doesnt work',
            'not working', 'broken', 'stuck', 'ugh', 'argh', 'damn',
            'why wont', "why won't", 'keeps failing', 'again', 'still'
        ],
        Emotion.STRESSED: [
            'stressed', 'overwhelmed', 'too much', 'deadline', 'urgent',
            'asap', 'hurry', 'rush', 'pressure', 'cant handle', "can't handle",
            'exhausted', 'tired', 'burned out', 'burnout'
        ],
        Emotion.SAD: [
            'sad', 'unhappy', 'disappointed', 'upset', 'depressed',
            'down', 'miserable', 'heartbroken', 'miss', 'lonely',
            'crying', 'tears', 'hurt', 'painful'
        ],
        Emotion.ANGRY: [
            'angry', 'furious', 'mad', 'hate', 'stupid', 'ridiculous',
            'unacceptable', 'terrible', 'worst', 'garbage', 'trash',
            'useless', 'awful', 'disgusting', 'infuriating'
        ],
        Emotion.TIRED: [
            'tired', 'exhausted', 'sleepy', 'drained', 'worn out',
            'need sleep', 'need rest', 'long day', 'late night', 'fatigued'
        ]
    }
    
    # Stress indicators
    STRESS_INDICATORS = {
        'high': [
            'asap', 'urgent', 'emergency', 'deadline', 'immediately',
            'right now', 'stressed', 'overwhelmed', 'panic', 'critical',
            '!!!', 'HELP', 'URGENT', 'need it now'
        ],
        'medium': [
            'soon', 'quickly', 'fast', 'hurry', 'busy', 'lots to do',
            'running late', 'behind schedule', 'pressure'
        ]
    }
    
    # Recommended response tones based on emotion
    RESPONSE_TONES = {
        Emotion.HAPPY: "enthusiastic",
        Emotion.EXCITED: "enthusiastic",
        Emotion.GRATEFUL: "warm",
        Emotion.CURIOUS: "helpful",
        Emotion.NEUTRAL: "professional",
        Emotion.CONFUSED: "patient_explanatory",
        Emotion.FRUSTRATED: "calm_supportive",
        Emotion.STRESSED: "calm_reassuring",
        Emotion.SAD: "empathetic",
        Emotion.ANGRY: "calm_professional",
        Emotion.TIRED: "gentle_efficient",
    }
    
    def __init__(self, memory_system=None):
        """
        Initialize sentiment analyzer.
        
        Args:
            memory_system: Optional MemorySystem for tracking mood over time
        """
        self.memory = memory_system
        self._mood_history = deque(maxlen=50)  # Last 50 sentiment readings
        self._session_start = datetime.now()
    
    def analyze(self, text: str) -> SentimentResult:
        """
        Analyze text for sentiment, emotion, and stress level.
        
        Args:
            text: User input text
            
        Returns:
            SentimentResult with analysis
        """
        text_lower = text.lower().strip()
        
        # Get TextBlob sentiment if available
        polarity = 0.0
        subjectivity = 0.5
        
        if TEXTBLOB_OK:
            try:
                blob = TextBlob(text)
                polarity = blob.sentiment.polarity
                subjectivity = blob.sentiment.subjectivity
            except:
                pass
        else:
            # Fallback: simple keyword-based polarity
            polarity = self._calculate_simple_polarity(text_lower)
        
        # Determine sentiment category
        sentiment = self._polarity_to_sentiment(polarity)
        
        # Detect emotion
        emotion, keywords = self._detect_emotion(text_lower)
        
        # Detect stress level
        stress_level = self._detect_stress(text_lower)
        
        # Calculate confidence
        confidence = self._calculate_confidence(text_lower, emotion, keywords)
        
        # Get recommended response tone
        recommended_tone = self.RESPONSE_TONES.get(emotion, "professional")
        
        result = SentimentResult(
            sentiment=sentiment,
            emotion=emotion,
            confidence=confidence,
            polarity=polarity,
            subjectivity=subjectivity,
            stress_level=stress_level,
            keywords=keywords,
            recommended_tone=recommended_tone
        )
        
        # Track in history
        self._mood_history.append({
            'timestamp': datetime.now().isoformat(),
            'sentiment': sentiment.value,
            'emotion': emotion.value,
            'stress': stress_level
        })
        
        # Store in memory if available
        if self.memory:
            try:
                self.memory.store_fact(
                    f"mood_{datetime.now().strftime('%H%M')}",
                    {
                        'sentiment': sentiment.value,
                        'emotion': emotion.value,
                        'stress': stress_level
                    },
                    category='mood_tracking'
                )
            except:
                pass
        
        return result
    
    def _calculate_simple_polarity(self, text: str) -> float:
        """Calculate polarity without TextBlob"""
        positive_words = set(self.EMOTION_KEYWORDS[Emotion.HAPPY] + 
                            self.EMOTION_KEYWORDS[Emotion.EXCITED] +
                            self.EMOTION_KEYWORDS[Emotion.GRATEFUL])
        
        negative_words = set(self.EMOTION_KEYWORDS[Emotion.SAD] +
                            self.EMOTION_KEYWORDS[Emotion.ANGRY] +
                            self.EMOTION_KEYWORDS[Emotion.FRUSTRATED])
        
        words = text.split()
        pos_count = sum(1 for w in words if w in positive_words)
        neg_count = sum(1 for w in words if w in negative_words)
        
        total = pos_count + neg_count
        if total == 0:
            return 0.0
        
        return (pos_count - neg_count) / total
    
    def _polarity_to_sentiment(self, polarity: float) -> Sentiment:
        """Convert polarity score to sentiment category"""
        if polarity >= 0.5:
            return Sentiment.VERY_POSITIVE
        elif polarity >= 0.1:
            return Sentiment.POSITIVE
        elif polarity <= -0.5:
            return Sentiment.VERY_NEGATIVE
        elif polarity <= -0.1:
            return Sentiment.NEGATIVE
        else:
            return Sentiment.NEUTRAL
    
    def _detect_emotion(self, text: str) -> Tuple[Emotion, List[str]]:
        """Detect primary emotion from text"""
        emotion_scores = {}
        found_keywords = {}
        
        for emotion, keywords in self.EMOTION_KEYWORDS.items():
            score = 0
            matches = []
            for keyword in keywords:
                if keyword in text:
                    score += 1
                    matches.append(keyword)
            
            if score > 0:
                emotion_scores[emotion] = score
                found_keywords[emotion] = matches
        
        if not emotion_scores:
            return Emotion.NEUTRAL, []
        
        # Get emotion with highest score
        top_emotion = max(emotion_scores, key=emotion_scores.get)
        return top_emotion, found_keywords.get(top_emotion, [])
    
    def _detect_stress(self, text: str) -> str:
        """Detect stress level from text"""
        for level, indicators in self.STRESS_INDICATORS.items():
            for indicator in indicators:
                if indicator.lower() in text:
                    return level
        
        # Check for multiple exclamation marks or caps
        if text.count('!') >= 3 or sum(1 for c in text if c.isupper()) > len(text) * 0.5:
            return 'medium'
        
        return 'low'
    
    def _calculate_confidence(
        self,
        text: str,
        emotion: Emotion,
        keywords: List[str]
    ) -> float:
        """Calculate confidence in the analysis"""
        # Base confidence on keyword matches and text length
        if not keywords:
            return 0.3
        
        keyword_confidence = min(len(keywords) / 3, 1.0) * 0.5
        length_confidence = min(len(text.split()) / 10, 1.0) * 0.3
        
        # Add bonus for strong indicators
        strong_indicators = ['very', 'really', 'so', 'extremely', 'super']
        indicator_bonus = 0.2 if any(ind in text for ind in strong_indicators) else 0
        
        return min(keyword_confidence + length_confidence + indicator_bonus, 1.0)
    
    def get_empathetic_prefix(self, result: SentimentResult) -> str:
        """
        Get an empathetic prefix for LADA's response.
        
        Args:
            result: SentimentResult from analysis
            
        Returns:
            Empathetic prefix string
        """
        prefixes = {
            Emotion.HAPPY: [
                "That's wonderful! ",
                "Great to hear! ",
                "Awesome! ",
            ],
            Emotion.EXCITED: [
                "I can feel your excitement! ",
                "That sounds amazing! ",
                "How exciting! ",
            ],
            Emotion.GRATEFUL: [
                "You're welcome! ",
                "Happy to help! ",
                "Glad I could assist! ",
            ],
            Emotion.CURIOUS: [
                "Great question! ",
                "Let me explain. ",
                "I'd be happy to help with that. ",
            ],
            Emotion.CONFUSED: [
                "No worries, let me clarify. ",
                "I understand it can be confusing. ",
                "Let me break this down. ",
            ],
            Emotion.FRUSTRATED: [
                "I understand your frustration. ",
                "Let's work through this together. ",
                "I'm here to help sort this out. ",
            ],
            Emotion.STRESSED: [
                "I understand you're under pressure. ",
                "Let me help you with this quickly. ",
                "Don't worry, we'll get this done. ",
            ],
            Emotion.SAD: [
                "I'm sorry to hear that. ",
                "That sounds difficult. ",
                "I understand. ",
            ],
            Emotion.ANGRY: [
                "I understand your concerns. ",
                "Let me help address this. ",
                "I hear you. ",
            ],
            Emotion.TIRED: [
                "I'll make this quick for you. ",
                "Let me handle this efficiently. ",
                "I've got you covered. ",
            ],
            Emotion.NEUTRAL: [
                "",  # No prefix needed
            ]
        }
        
        import random
        options = prefixes.get(result.emotion, [""])
        return random.choice(options)
    
    def get_session_mood_summary(self) -> Dict[str, Any]:
        """Get summary of mood throughout the session"""
        if not self._mood_history:
            return {'status': 'no_data'}
        
        emotions = [m['emotion'] for m in self._mood_history]
        sentiments = [m['sentiment'] for m in self._mood_history]
        stress_levels = [m['stress'] for m in self._mood_history]
        
        # Calculate averages
        from collections import Counter
        emotion_counts = Counter(emotions)
        sentiment_counts = Counter(sentiments)
        stress_counts = Counter(stress_levels)
        
        return {
            'session_duration_minutes': (datetime.now() - self._session_start).seconds // 60,
            'total_messages_analyzed': len(self._mood_history),
            'predominant_emotion': emotion_counts.most_common(1)[0][0] if emotion_counts else 'neutral',
            'predominant_sentiment': sentiment_counts.most_common(1)[0][0] if sentiment_counts else 'neutral',
            'stress_breakdown': dict(stress_counts),
            'emotion_breakdown': dict(emotion_counts),
        }
    
    def should_offer_break(self) -> Tuple[bool, str]:
        """Check if user might need a break based on stress patterns"""
        if len(self._mood_history) < 5:
            return False, ""
        
        recent = list(self._mood_history)[-5:]
        high_stress_count = sum(1 for m in recent if m['stress'] == 'high')
        negative_count = sum(1 for m in recent if 'negative' in m['sentiment'])
        
        if high_stress_count >= 3:
            return True, "I've noticed you seem under a lot of pressure. Would you like to take a short break?"
        
        if negative_count >= 4:
            return True, "It seems like things have been challenging. Remember, it's okay to step away for a moment."
        
        return False, ""


# ============================================================
# EXAMPLE USAGE
# ============================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    analyzer = SentimentAnalyzer()
    
    print("😊 Sentiment Analysis Test")
    print("=" * 50)
    
    test_texts = [
        "This is amazing! I love how this works!",
        "I'm so frustrated, nothing is working correctly.",
        "Can you help me understand how this works?",
        "URGENT! I need this done ASAP!!!",
        "Thanks so much, you really helped me out.",
        "I'm feeling tired after this long day.",
        "Why won't this stupid thing work?!",
        "I'm a bit confused about the process.",
    ]
    
    for text in test_texts:
        result = analyzer.analyze(text)
        prefix = analyzer.get_empathetic_prefix(result)
        
        print(f"\n📝 Input: \"{text}\"")
        print(f"   Sentiment: {result.sentiment.value}")
        print(f"   Emotion: {result.emotion.value}")
        print(f"   Stress: {result.stress_level}")
        print(f"   Confidence: {result.confidence:.2f}")
        print(f"   Tone: {result.recommended_tone}")
        print(f"   Prefix: \"{prefix}\"")
    
    # Session summary
    print("\n" + "=" * 50)
    summary = analyzer.get_session_mood_summary()
    print(f"Session Summary: {summary}")
    
    print("\n✅ Sentiment Analysis test complete!")
