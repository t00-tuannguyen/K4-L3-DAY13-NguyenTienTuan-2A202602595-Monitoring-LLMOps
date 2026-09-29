from __future__ import annotations

from contextlib import contextmanager

from app import agent as agent_module


class ManagedPrompt:
    version = 3

    def compile(self, **variables: str) -> str:
        return (
            f"Feature={variables['feature']}\n"
            f"Docs={variables['docs']}\n"
            f"Question={variables['message']}"
        )


class RecordingLangfuseClient:
    def __init__(self) -> None:
        self.prompt = ManagedPrompt()
        self.span_updates: list[dict] = []

    def get_prompt(self, name: str, **kwargs):
        return self.prompt

    def update_current_span(self, **kwargs) -> None:
        self.span_updates.append(kwargs)


def test_agent_records_prompt_version_with_v4_observation_api(monkeypatch) -> None:
    monkeypatch.setenv("LANGFUSE_PROMPT_NAME", "day13-chat")
    monkeypatch.setenv("LANGFUSE_PROMPT_LABEL", "production")
    client = RecordingLangfuseClient()
    monkeypatch.setattr(agent_module, "get_langfuse_client", lambda: client)
    monkeypatch.setattr(agent_module, "tracing_enabled", lambda: True)

    propagated: list[dict] = []

    @contextmanager
    def record_attributes(**kwargs):
        propagated.append(kwargs)
        yield

    monkeypatch.setattr(agent_module, "propagate_attributes", record_attributes)

    agent = agent_module.LabAgent()
    agent_module.LabAgent.run.__wrapped__(
        agent,
        user_id="student-01",
        feature="qa",
        session_id="session-01",
        message="Explain traces",
        correlation_id="req-12345678",
    )

    span_update = client.span_updates[-1]
    assert span_update["metadata"] == {
        "doc_count": 1,
        "query_preview": "Explain traces",
        "prompt_name": "day13-chat",
        "prompt_label": "production",
        "prompt_version": "3",
        "prompt_source": "langfuse",
        "prompt_fetch_error": "",
    }
    assert span_update["version"] == "3"
    assert propagated[0]["metadata"]["correlation_id"] == "req-12345678"
    assert propagated[-1]["prompt"] is client.prompt


class RecordingObservationClient:
    def __init__(self) -> None:
        self.span_updates: list[dict] = []
        self.generation_updates: list[dict] = []

    def update_current_span(self, **kwargs) -> None:
        self.span_updates.append(kwargs)

    def update_current_generation(self, **kwargs) -> None:
        self.generation_updates.append(kwargs)


def test_child_observations_record_retrieval_and_generation_usage(monkeypatch) -> None:
    from app import tracing
    from app.prompt_management import ResolvedPrompt

    client = RecordingObservationClient()
    monkeypatch.setattr(tracing, "get_langfuse_client", lambda: client)
    agent = agent_module.LabAgent()

    docs = agent._retrieve("What is the refund policy? mail me at a@b.vn")
    assert docs
    assert client.span_updates[-1]["metadata"]["doc_count"] == len(docs)
    assert "a@b.vn" not in client.span_updates[-1]["metadata"]["query_preview"]

    managed = ManagedPrompt()
    prompt = ResolvedPrompt(
        text="Feature=qa\nDocs=x\nQuestion=y",
        name="day13-chat",
        label="production",
        version="3",
        source="langfuse",
        managed_prompt=managed,
    )
    response = agent._generate(prompt)
    update = client.generation_updates[-1]
    assert update["model"] == agent.model
    assert update["prompt"] is managed
    assert update["usage_details"] == {
        "input": response.usage.input_tokens,
        "output": response.usage.output_tokens,
    }
    assert update["cost_details"]["total"] == agent._estimate_cost(
        response.usage.input_tokens, response.usage.output_tokens
    )
    assert "input" not in update  # không gửi prompt thô lên Langfuse
