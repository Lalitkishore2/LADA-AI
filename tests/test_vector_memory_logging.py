import logging
import threading

from modules import vector_memory as vm


class _DummyEmbedder:
    def __init__(self, *args, **kwargs):
        self.uses_custom_embeddings = False

    def encode(self, texts):
        return None


def test_embeddings_fallback_info_logged_once(caplog, monkeypatch):
    monkeypatch.setattr(vm, "EMBEDDINGS_OK", False)
    monkeypatch.setattr(vm, "_EMBEDDINGS_FALLBACK_LOGGED", False)

    with caplog.at_level(logging.INFO, logger=vm.logger.name):
        vm.EmbeddingProvider()
        vm.EmbeddingProvider()

    info_messages = [
        r.message
        for r in caplog.records
        if r.levelno == logging.INFO and "sentence-transformers not installed" in r.message
    ]
    assert len(info_messages) == 1


def test_chromadb_fallback_info_logged_once_by_default(caplog, monkeypatch, tmp_path):
    monkeypatch.setattr(vm, "CHROMADB_OK", False)
    monkeypatch.setattr(vm, "_CHROMADB_FALLBACK_WARNED", False)
    monkeypatch.setattr(vm, "EmbeddingProvider", _DummyEmbedder)
    monkeypatch.delenv("LADA_REQUIRE_CHROMADB", raising=False)

    with caplog.at_level(logging.INFO, logger=vm.logger.name):
        vm.VectorMemorySystem(data_dir=str(tmp_path / "vm_one"))
        vm.VectorMemorySystem(data_dir=str(tmp_path / "vm_two"))

    info_messages = [
        r.message
        for r in caplog.records
        if r.levelno == logging.INFO and "ChromaDB not installed" in r.message
    ]
    warning_messages = [
        r.message
        for r in caplog.records
        if r.levelno == logging.WARNING and "ChromaDB not installed" in r.message
    ]
    assert len(info_messages) == 1
    assert len(warning_messages) == 0


def test_chromadb_fallback_warning_logged_once_in_strict_mode(caplog, monkeypatch, tmp_path):
    monkeypatch.setattr(vm, "CHROMADB_OK", False)
    monkeypatch.setattr(vm, "_CHROMADB_FALLBACK_WARNED", False)
    monkeypatch.setattr(vm, "EmbeddingProvider", _DummyEmbedder)
    monkeypatch.setenv("LADA_REQUIRE_CHROMADB", "1")

    with caplog.at_level(logging.WARNING, logger=vm.logger.name):
        vm.VectorMemorySystem(data_dir=str(tmp_path / "vm_one"))
        vm.VectorMemorySystem(data_dir=str(tmp_path / "vm_two"))

    warning_messages = [
        r.message
        for r in caplog.records
        if r.levelno == logging.WARNING and "ChromaDB not installed" in r.message
    ]
    assert len(warning_messages) == 1


def test_embeddings_fallback_info_threadsafe_once(monkeypatch):
    monkeypatch.setattr(vm, "_EMBEDDINGS_FALLBACK_LOGGED", False)

    calls = []
    calls_lock = threading.Lock()

    def _fake_info(message, *args, **kwargs):
        if "sentence-transformers not installed" in str(message):
            with calls_lock:
                calls.append(str(message))

    monkeypatch.setattr(vm.logger, "info", _fake_info)

    barrier = threading.Barrier(8)

    def _worker():
        barrier.wait()
        vm.EmbeddingProvider._log_embeddings_fallback_once()

    threads = [threading.Thread(target=_worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(calls) == 1


def test_chromadb_fallback_info_threadsafe_once(monkeypatch):
    monkeypatch.setattr(vm, "_CHROMADB_FALLBACK_WARNED", False)
    monkeypatch.delenv("LADA_REQUIRE_CHROMADB", raising=False)

    calls = []
    calls_lock = threading.Lock()

    def _fake_log(level, message, *args, **kwargs):
        if "ChromaDB not installed" in str(message):
            with calls_lock:
                calls.append((level, str(message)))

    monkeypatch.setattr(vm.logger, "log", _fake_log)

    barrier = threading.Barrier(8)

    def _worker():
        barrier.wait()
        vm.VectorMemorySystem._warn_chromadb_fallback_once()

    threads = [threading.Thread(target=_worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert calls == [(logging.INFO, "[VectorMemory] ChromaDB not installed. Using in-memory fallback.")]
