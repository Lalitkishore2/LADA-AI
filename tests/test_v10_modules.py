"""LADA v10 module smoke tests (pytest-compatible)."""


def test_v10_sentiment_analysis_smoke():
    from modules.sentiment_analysis import SentimentAnalyzer

    analyzer = SentimentAnalyzer()
    result = analyzer.analyze("I am frustrated, nothing works!")

    assert result is not None
    assert hasattr(result, "sentiment")
    assert hasattr(result, "emotion")
    assert hasattr(result, "stress_level")


def test_v10_file_encryption_smoke():
    from modules.file_encryption import FileEncryption

    encryption = FileEncryption()
    encryption.set_password("test123")

    assert encryption is not None


def test_v10_document_reader_smoke():
    from modules.document_reader import DocumentReader

    reader = DocumentReader()

    assert reader is not None


def test_v10_pomodoro_configuration():
    from modules.productivity_tools import PomodoroTimer

    timer = PomodoroTimer()
    timer.configure(work_minutes=25, short_break_minutes=5)

    assert timer.work_minutes == 25
    assert timer.short_break_minutes == 5


def test_v10_personality_modes_smoke():
    from lada_jarvis_core import LadaPersonality

    for mode in ["jarvis", "friday", "karen", "casual"]:
        LadaPersonality.set_mode(mode)
        acknowledgment = LadaPersonality.get_acknowledgment()
        assert isinstance(acknowledgment, str)
        assert acknowledgment.strip() != ""


def test_v10_agent_memory_mixin_preference_roundtrip():
    from modules.agents.agent_memory import AgentMemoryMixin

    class _MemoryAgent(AgentMemoryMixin):
        agent_type = "test"

        def __init__(self):
            self.init_memory()

    agent = _MemoryAgent()
    agent.set_preference("test_pref", "value123")

    assert agent.get_preference("test_pref") == "value123"
