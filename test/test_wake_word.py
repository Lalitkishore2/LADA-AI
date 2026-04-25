import modules.wake_word as wake_word


class _FakeMic:
    def __enter__(self):
        return object()

    def __exit__(self, exc_type, exc, tb):
        return False


def test_wake_word_detected_and_command_extracted(monkeypatch):
    woke = []
    cmds = []

    def on_wake():
        woke.append(True)

    def on_command(cmd: str):
        cmds.append(cmd)

    d = wake_word.WakeWordDetector(on_wake=on_wake, on_command=on_command)
    d.microphone = _FakeMic()

    class FakeRecognizer:
        def listen(self, source, timeout=None, phrase_time_limit=None):
            return object()

        def recognize_google(self, audio):
            # The detector checks WAKE_WORDS in order and matches "l" first.
            return "l do something"

    d.recognizer = FakeRecognizer()

    d._listen_once()

    assert woke == [True]
    assert cmds == ["do something"]


def test_wake_word_only_prompts_followup_listen(monkeypatch):
    woke = []
    followup = []

    def on_wake():
        woke.append(True)

    d = wake_word.WakeWordDetector(on_wake=on_wake, on_command=lambda _: None)
    d.microphone = _FakeMic()

    class FakeRecognizer:
        def listen(self, source, timeout=None, phrase_time_limit=None):
            return object()

        def recognize_google(self, audio):
            # Use a wake token that results in an empty command after split.
            return "l"

    d.recognizer = FakeRecognizer()

    monkeypatch.setattr(d, "_listen_for_command", lambda: followup.append(True))

    d._listen_once()

    assert woke == [True]
    assert followup == [True]
