from modules.console_encoding import configure_console_utf8


class _FakeStream:
    def __init__(self):
        self.calls = []

    def reconfigure(self, **kwargs):
        self.calls.append(kwargs)


class _BrokenStream:
    def reconfigure(self, **kwargs):
        raise OSError("not writable")


def test_configure_console_utf8_reconfigures_both_streams():
    stdout = _FakeStream()
    stderr = _FakeStream()

    changed = configure_console_utf8(stdout=stdout, stderr=stderr)

    assert changed == 2
    assert stdout.calls == [{"encoding": "utf-8", "errors": "replace"}]
    assert stderr.calls == [{"encoding": "utf-8", "errors": "replace"}]


def test_configure_console_utf8_skips_streams_without_reconfigure():
    changed = configure_console_utf8(stdout=object(), stderr=object())

    assert changed == 0


def test_configure_console_utf8_handles_stream_reconfigure_failure():
    stdout = _FakeStream()
    stderr = _BrokenStream()

    changed = configure_console_utf8(stdout=stdout, stderr=stderr)

    assert changed == 1
    assert stdout.calls == [{"encoding": "utf-8", "errors": "replace"}]


def test_configure_console_utf8_handles_none_streams():
    changed = configure_console_utf8(stdout=None, stderr=None)

    assert isinstance(changed, int)
