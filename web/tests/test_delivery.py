"""Asset refresh and unavailable-provider behavior, with an isolated database."""
import importlib
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def local_client(tmp_path_factory):
    import os
    root = tmp_path_factory.mktemp("discussion-delivery")
    names = ("JIEHUO_DB_PATH", "JIEHUO_OUTPUT_DIR", "JIEHUO_INFOFLOW_ENV",
             "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "MIMO_API_KEY")
    previous = {key: os.environ.get(key) for key in names}
    os.environ["JIEHUO_DB_PATH"] = str(root / "sessions.db")
    os.environ["JIEHUO_OUTPUT_DIR"] = str(root / "notes")
    os.environ["JIEHUO_INFOFLOW_ENV"] = str(root / "absent.env")
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ.pop("DEEPSEEK_API_KEY", None)
    os.environ.pop("MIMO_API_KEY", None)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    # Keep local credentials out of offline tests.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: None)
        module = importlib.import_module("app")
    with TestClient(module.app) as client:
        yield client
    sys.path.pop(0)
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.mark.parametrize("path", ["/", "/app.js", "/style.css"])
def test_frontend_assets_revalidate(local_client, path):
    response = local_client.get(path)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"


def test_missing_provider_reports_error_without_answer(local_client):
    assert local_client.get("/api/health").json()["llm_configured"] is False
    personas = local_client.get("/api/personas").json()
    response = local_client.post("/api/chat", json={
        "mode": "solo", "persona_ids": [personas[0]["id"]],
        "messages": [{"role": "user", "content": "测试连接失败"}],
    })
    events = [json.loads(line[5:].strip()) for line in response.text.splitlines()
              if line.startswith("data:")]
    assert any(event["type"] == "error" and "尚未配置" in event["message"]
               for event in events)
    assert not any(event["type"] == "delta" for event in events)
    assert local_client.get("/api/sessions").json() == []


def test_health_and_frontend_hide_model(local_client):
    health = local_client.get("/api/health").json()
    assert "model" not in health
    page = local_client.get("/").text
    script = local_client.get("/app.js").text
    for text in (page, script):
        assert "deepseek" not in text.lower()
        assert "mimo" not in text.lower()
        assert "modelSel" not in text
    assert 'id="serviceTag"' in page


def test_mimo_request_and_stream(local_client, monkeypatch):
    import httpx
    from openai import AsyncOpenAI
    import llm
    requests = []

    def handle(request):
        body = json.loads(request.content)
        requests.append(body)
        assert request.url == "https://api.xiaomimimo.com/v1/chat/completions"
        assert body["model"] == "mimo-v2.6-flash"
        assert body["thinking"] == {"type": "disabled"}
        chunk = {"id": "test", "object": "chat.completion.chunk", "created": 0,
                 "model": body["model"], "choices": [{"index": 0,
                 "delta": {"content": "先厘清你的困惑。"}, "finish_reason": None}]}
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
                             text="data: " + json.dumps(chunk) + "\n\ndata: [DONE]\n\n")

    monkeypatch.setattr(llm, "_S", {**llm._S, "api_key": "test", "model": "mimo-v2.6-flash"})
    monkeypatch.setattr(llm, "_client", AsyncOpenAI(api_key="test",
                        base_url="https://api.xiaomimimo.com/v1",
                        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle))))
    persona = local_client.get("/api/personas").json()[0]["id"]
    response = local_client.post("/api/chat", json={"mode": "solo",
        "persona_ids": [persona], "messages": [{"role": "user", "content": "如何做选择？"}],
        "model": "deepseek-v4-pro"})
    assert response.status_code == 200
    assert "先厘清你的困惑" in response.text
    assert len(requests) == 1
