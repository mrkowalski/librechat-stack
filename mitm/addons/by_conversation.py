"""Append each OpenRouter chat completion to logs/conversations/<conversation_id>.jsonl."""

import json
import re
from datetime import datetime
from pathlib import Path

from mitmproxy import http

OUT = Path("/data/conversations")
UNSAFE = re.compile(r"[^A-Za-z0-9_-]")


def _conversation_id(flow: http.HTTPFlow) -> str:
    raw = flow.request.headers.get("x-conversation-id", "")
    if not raw or raw.startswith("{{") or raw in ("new", "null", "undefined"):
        return "_unassigned"
    return UNSAFE.sub("_", raw)[:100]


def _loads(text: str) -> object:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}


def _parse_sse(text: str) -> dict:
    """Reassemble a streamed completion: text, tool calls, usage."""
    content: list[str] = []
    calls: dict[int, dict] = {}
    usage = model = finish = None
    for line in text.splitlines():
        if not line.startswith("data:"):
            continue  # skips OpenRouter ": PROCESSING" keep-alives
        data = line[5:].strip()
        if data == "[DONE]":
            break
        chunk = _loads(data)
        if not isinstance(chunk, dict):
            continue
        model = chunk.get("model", model)
        usage = chunk.get("usage") or usage
        for choice in chunk.get("choices", []):
            finish = choice.get("finish_reason") or finish
            delta = choice.get("delta") or {}
            if delta.get("content"):
                content.append(delta["content"])
            for tc in delta.get("tool_calls") or []:
                slot = calls.setdefault(tc.get("index", 0), {"id": None, "name": None, "arguments": ""})
                fn = tc.get("function") or {}
                slot["id"] = tc.get("id") or slot["id"]
                slot["name"] = fn.get("name") or slot["name"]
                slot["arguments"] += fn.get("arguments") or ""
    for slot in calls.values():
        slot["arguments"] = _loads(slot["arguments"]) if slot["arguments"] else {}
    return {
        "model": model,
        "finish_reason": finish,
        "content": "".join(content),
        "tool_calls": [calls[i] for i in sorted(calls)],
        "usage": usage,
    }


def response(flow: http.HTTPFlow) -> None:
    if not flow.request.path.startswith("/api/v1/chat/completions"):
        return
    body = flow.response.get_text() or ""
    streamed = "text/event-stream" in flow.response.headers.get("content-type", "")
    end = flow.response.timestamp_end or flow.response.timestamp_start
    record = {
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": flow.response.status_code,
        "duration_s": round(end - flow.request.timestamp_start, 3),
        "request": _loads(flow.request.get_text() or "{}"),
        "response": _parse_sse(body) if streamed else _loads(body),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / f"{_conversation_id(flow)}.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
