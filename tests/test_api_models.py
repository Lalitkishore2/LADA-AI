"""Direct tests for modules/api/models.py schema defaults and contracts."""

from modules.api.models import ChatResponse, AgentResponse


def test_chat_response_sources_default_isolation():
    first = ChatResponse(
        success=True,
        response="hello",
        conversation_id="conv-1",
        model="demo",
        timestamp="2026-04-20T00:00:00",
    )
    second = ChatResponse(
        success=True,
        response="world",
        conversation_id="conv-2",
        model="demo",
        timestamp="2026-04-20T00:00:01",
    )

    first.sources.append({"id": "source-1"})

    assert first.sources == [{"id": "source-1"}]
    assert second.sources == []


def test_agent_response_accepts_non_dict_result_payload():
    payload = AgentResponse(
        success=True,
        agent="demo",
        action="run",
        result="done",
        timestamp="2026-04-20T00:00:00",
    )

    assert payload.result == "done"
