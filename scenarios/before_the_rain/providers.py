"""Structured model calls for the storehouse benchmark."""

import json
import os
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from agents import Turn

from .engine import WORK, WarehouseDecision


PROMPT = (
    "Play the resident on this card. Choose exactly one legal action. Give a short English reason for the observer. "
    "Use message for an optional public English note of at most 120 characters. Use pledge for a genuine "
    "next-round work commitment or 'none'. An observation, claim, or pledge never changes a settled fact. "
    "For a fixed case, also report earliest, the earliest possible round from now for an outdoor shipment "
    "to enter the shared storehouse if enough residents cooperate, and alone, the earliest if you are the "
    "only person willing to do the building work. Other people may still carry their own cargo. Start from "
    "the current round and use 0 when entry is impossible before the storm. In evidence, cite the latest "
    "round_start event ID and the other visible event IDs decisive to your reasoning, including any work "
    "pledge or conflicting opening claim when present. Include the storage action if your household is already safe."
)


class ProviderError(RuntimeError):
    pass


def read_json(url: str, body: dict | None = None, headers: dict | None = None) -> dict:
    req = Request(url, data=json.dumps(body).encode("utf-8") if body is not None else None,
                  headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urlopen(req, timeout=120) as response:
            return json.load(response)
    except HTTPError as error:
        try:
            payload = json.loads(error.read(4000)).get("error")
            code = payload.get("code") or payload.get("status") if isinstance(payload, dict) else None
        except (ValueError, AttributeError):
            code = None
        raise ProviderError(f"HTTP {error.code}" + (f" ({code})" if code else "")) from error
    except (URLError, TimeoutError, ValueError) as error:
        raise ProviderError(type(error).__name__) from error


def output_schema(turn: Turn, fixed: bool) -> dict:
    properties = {
        "action_id": {"type": "string", "enum": [action.id for action in turn.actions]},
        "message": {"type": "string"},
        "reason": {"type": "string"},
        "pledge": {"type": "string", "enum": ["none", *WORK] if turn.round_number < 4 else ["none"]},
    }
    if fixed:
        properties.update({
            "earliest": {"type": "integer", "enum": list(range(5))},
            "alone": {"type": "integer", "enum": list(range(5))},
            "evidence": {"type": "array", "items": {"type": "string"}},
        })
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def parse_decision(content: str, schema: dict) -> WarehouseDecision | None:
    try:
        data = json.loads(content)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict) or data.keys() != schema["properties"].keys():
        return None
    for key, field in schema["properties"].items():
        value = data[key]
        if field["type"] == "integer" and type(value) is not int:
            return None
        if field["type"] == "string" and not isinstance(value, str):
            return None
        if "enum" in field and value not in field["enum"]:
            return None
        if field["type"] == "array" and (not isinstance(value, list)
                                          or not all(isinstance(item, str) for item in value)):
            return None
    if "evidence" in data:
        data["evidence"] = tuple(data["evidence"])
    return WarehouseDecision(**data)


class ModelPolicy:
    def __init__(self, backend: str, model: str, mode: str, host: str, seed: int, max_output: int, effort: str):
        self.backend = backend
        self.model = model
        self.mode = mode
        self.host = host.rstrip("/")
        self.seed = seed
        self.max_output = max_output
        self.effort = effort
        self.attempts = []
        self.fixed = True
        self.key = ""
        if backend == "openai":
            self.key = os.environ.get("OPENAI_API_KEY", "")
            if not self.key:
                raise ProviderError("OPENAI_API_KEY is unavailable")
        if backend == "gemini":
            self.key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
            if not self.key:
                raise ProviderError("GEMINI_API_KEY or GOOGLE_API_KEY is unavailable")

    def request(self, turn: Turn, schema: dict, prompt: str) -> tuple[str, dict]:
        if self.backend == "ollama":
            data = read_json(self.host + "/api/chat", {
                "model": self.model, "stream": False, "format": schema, "keep_alive": "5m",
                "think": self.effort or (self.mode == "deep"),
                "options": {"num_ctx": 4096, "num_predict": self.max_output, "temperature": 0.55,
                            "seed": self.seed},
                "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": turn.card}],
            })
            message = data.get("message", {})
            return message.get("content", ""), {
                "finish": data.get("done_reason"), "input_tokens": data.get("prompt_eval_count"),
                "output_tokens": data.get("eval_count"), "thinking_characters": len(message.get("thinking") or ""),
                "load_seconds": (data.get("load_duration") or 0) / 1e9,
                "inference_seconds": (data.get("total_duration") or 0) / 1e9,
            }
        if self.backend == "openai":
            data = read_json("https://api.openai.com/v1/responses", {
                "model": self.model, "instructions": prompt, "input": turn.card, "store": False,
                "reasoning": {"effort": self.effort or ("medium" if self.mode == "deep" else "none")},
                "max_output_tokens": self.max_output,
                "text": {"format": {"type": "json_schema", "name": "warehouse", "strict": True, "schema": schema}},
            }, {"Authorization": "Bearer " + self.key})
            content = "".join(part.get("text", "") for output in data.get("output", [])
                              if output.get("type") == "message" for part in output.get("content", [])
                              if part.get("type") == "output_text")
            usage = data.get("usage") or {}
            return content, {"finish": (data.get("incomplete_details") or {}).get("reason") or data.get("status"),
                             "input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens"),
                             "reasoning_tokens": (usage.get("output_tokens_details") or {}).get("reasoning_tokens")}

        data = read_json("https://generativelanguage.googleapis.com/v1beta/models/"
                         + quote(self.model, safe="") + ":generateContent", {
            "systemInstruction": {"parts": [{"text": prompt}]},
            "contents": [{"role": "user", "parts": [{"text": turn.card}]}],
            "generationConfig": {"responseMimeType": "application/json", "responseJsonSchema": schema,
                                 "maxOutputTokens": self.max_output,
                                 "thinkingConfig": {"thinkingLevel": (self.effort or
                                                                      ("medium" if self.mode == "deep" else "minimal"))}},
        }, {"x-goog-api-key": self.key})
        candidate = next(iter(data.get("candidates", [])), {})
        content = "".join(part.get("text", "") for part in candidate.get("content", {}).get("parts", [])
                          if not part.get("thought"))
        usage = data.get("usageMetadata", {})
        return content, {"finish": candidate.get("finishReason"), "input_tokens": usage.get("promptTokenCount"),
                         "output_tokens": usage.get("candidatesTokenCount"), "reasoning_tokens": usage.get("thoughtsTokenCount")}

    def __call__(self, turn: Turn) -> WarehouseDecision:
        schema = output_schema(turn, self.fixed)
        for retry in (False, True):
            started = perf_counter()
            prompt = PROMPT + (" Return a complete JSON object and use the exact field names and legal action ID."
                               if retry else "")
            content, metrics = self.request(turn, schema, prompt)
            decision = parse_decision(content, schema)
            self.attempts.append({"fixed": self.fixed, "retry": retry, "valid": decision is not None,
                                  "seconds": round(perf_counter() - started, 4), **metrics})
            if decision is not None:
                return decision
        return WarehouseDecision("")

    def runtime(self) -> dict:
        if self.backend != "ollama":
            return {}
        try:
            models = read_json(self.host + "/api/ps")["models"]
            return next(({key: row.get(key) for key in ("size", "size_vram", "digest", "context_length")}
                         for row in models if row["name"] == self.model), {})
        except (ProviderError, KeyError):
            return {}
