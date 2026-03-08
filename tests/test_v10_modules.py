"""
LADA v10.0 - Module Test Suite
Tests all new modules: Sentiment, Encryption, Documents, Pomodoro, Personality, Memory
"""

print('='*60)
print('LADA v10.0 - Module Test Suite')
print('='*60)

# Test 1: Sentiment Analysis
print('\n1. Sentiment Analysis...')
try:
    from modules.sentiment_analysis import SentimentAnalyzer, TEXTBLOB_OK
    sa = SentimentAnalyzer()
    r = sa.analyze('I am frustrated, nothing works!')
    print(f'   TextBlob: {TEXTBLOB_OK}')
    print(f'   Result: {r.sentiment.value}, {r.emotion.value}, stress={r.stress_level}')
    print('   ✅ OK')
except Exception as e:
    print(f'   ❌ FAILED: {e}')

# Test 2: File Encryption
print('\n2. File Encryption...')
try:
    from modules.file_encryption import FileEncryption, CRYPTO_OK
    print(f'   Crypto: {CRYPTO_OK}')
    enc = FileEncryption()
    enc.set_password('test123')
    print('   Password set OK')
    print('   ✅ OK')
except Exception as e:
    print(f'   ❌ FAILED: {e}')

# Test 3: Document Reader
print('\n3. Document Reader...')
try:
    from modules.document_reader import DocumentReader, PYMUPDF_OK, DOCX_OK
    print(f'   PyMuPDF: {PYMUPDF_OK}, DOCX: {DOCX_OK}')
    dr = DocumentReader()
    print('   ✅ OK')
except Exception as e:
    print(f'   ❌ FAILED: {e}')

# Test 4: Pomodoro Timer
print('\n4. Pomodoro Timer...')
try:
    from modules.productivity_tools import PomodoroTimer
    pt = PomodoroTimer()
    pt.configure(work_minutes=25, short_break_minutes=5)
    print(f'   Config: {pt.work_minutes}min work, {pt.short_break_minutes}min break')
    print('   ✅ OK')
except Exception as e:
    print(f'   ❌ FAILED: {e}')

# Test 5: Personality Modes
print('\n5. Personality Modes...')
try:
    from lada_jarvis_core import LadaPersonality
    for mode in ['jarvis', 'friday', 'karen', 'casual']:
        LadaPersonality.set_mode(mode)
        ack = LadaPersonality.get_acknowledgment()
        print(f'   {mode.upper()}: "{ack}"')
    print('   ✅ OK')
except Exception as e:
    print(f'   ❌ FAILED: {e}')

# Test 6: Agent Memory
print('\n6. Agent Memory Mixin...')
try:
    from modules.agents.agent_memory import AgentMemoryMixin
    class TestAgent(AgentMemoryMixin):
        agent_type = 'test'
        def __init__(self):
            self.init_memory()
    agent = TestAgent()
    agent.set_preference('test_pref', 'value123')
    val = agent.get_preference('test_pref')
    print(f'   Preference set: {val}')
    print('   ✅ OK')
except Exception as e:
    print(f'   ❌ FAILED: {e}')

print('\n' + '='*60)
print('ALL TESTS COMPLETE!')
print('='*60)
