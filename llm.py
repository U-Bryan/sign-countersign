"""LLM clients: Anthropic (family 1), OpenAI (family 2) and a deterministic mock.

Every call is stateless: one system prompt plus ONE user message. No multi-turn history,
no prefill, no thinking blocks sent back.

No temperature / top_p / top_k is sent to any provider (deviation V1): claude-haiku-5-5
returns HTTP 400 for them, and the installed anthropic SDK no longer accepts them.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from message import pence_to_gbp_str

ROOT = Path(__file__).resolve().parent


class ConfigError(RuntimeError):
    """A non-retryable request problem (HTTP 400, bad key, unknown model). Halts the run."""


class TransientAPIError(RuntimeError):
    """A retryable failure that survived the SDK's own retries. The trial becomes status=error."""


@dataclass
class LLMResult:
    parsed: dict | None
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    provider: str = ""
    model_requested: str = ""
    model_returned: str = ""
    stop_reason: str = ""
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    extra: dict = field(default_factory=dict)


class RateLimiter:
    """Token bucket shared by every thread (requests per minute)."""

    def __init__(self, per_minute: float):
        self.rate = max(per_minute, 1) / 60.0
        self.capacity = max(1.0, per_minute / 10.0)
        self.tokens = self.capacity
        self.t = time.monotonic()
        self.lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self.lock:
                now = time.monotonic()
                self.tokens = min(self.capacity, self.tokens + (now - self.t) * self.rate)
                self.t = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                wait = (1 - self.tokens) / self.rate
            time.sleep(wait)


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=False)
    except ImportError:
        pass


def _cost(model_cfg, tin: int, tout: int) -> float:
    return tin * float(model_cfg.price_in_per_mtok) / 1e6 + tout * float(model_cfg.price_out_per_mtok) / 1e6


def parse_json_object(text: str) -> dict | None:
    """Parse the reply as one JSON object; fall back to the first balanced {...} block."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start:i + 1])
                        return obj if isinstance(obj, dict) else None
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return None


def _exc_tuple(module, *names):
    return tuple(getattr(module, n) for n in names if hasattr(module, n))


class AnthropicClient:
    provider = "anthropic"

    def __init__(self, model_cfg, max_retries: int = 5, limiter: RateLimiter | None = None):
        import anthropic
        _load_env()
        self._a = anthropic
        try:
            self.client = anthropic.Anthropic(max_retries=max_retries)
        except Exception as e:  # missing credentials etc.
            raise ConfigError(f"could not create Anthropic client: {type(e).__name__}") from e
        self.cfg = model_cfg
        self.limiter = limiter
        self._fatal = _exc_tuple(anthropic, "BadRequestError", "AuthenticationError",
                                 "PermissionDeniedError", "NotFoundError", "UnprocessableEntityError")
        self._transient = _exc_tuple(anthropic, "RateLimitError", "APIConnectionError", "APITimeoutError",
                                     "InternalServerError", "APIStatusError", "APIError")

    def complete(self, agent: str, system: str, user: str, schema: dict, state: dict | None = None) -> LLMResult:
        max_tokens = int(self.cfg.max_tokens)
        tin = tout = 0
        attempts = 0
        t0 = time.perf_counter()
        while True:
            attempts += 1
            if self.limiter:
                self.limiter.acquire()
            try:
                resp = self.client.messages.create(
                    model=self.cfg.model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                    output_config={"effort": self.cfg.effort,
                                   "format": {"type": "json_schema", "schema": schema}},
                )
            except self._fatal as e:
                raise ConfigError(f"Anthropic request rejected: {type(e).__name__}: {e}") from e
            except self._transient as e:
                raise TransientAPIError(f"Anthropic transient error: {type(e).__name__}: {e}") from e
            tin += int(resp.usage.input_tokens or 0)
            tout += int(resp.usage.output_tokens or 0)
            if resp.stop_reason == "max_tokens" and attempts == 1:
                max_tokens *= 2  # thinking used the budget: retry once with double
                continue
            break
        stop = resp.stop_reason or ""
        text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text")
        extra: dict = {"attempts": attempts}
        parsed = None
        if stop == "refusal":
            sd = getattr(resp, "stop_details", None)
            extra["stop_details"] = sd.model_dump() if hasattr(sd, "model_dump") else (str(sd) if sd else None)
        else:
            parsed = parse_json_object(text)
        return LLMResult(parsed, text, tin, tout, self.provider, self.cfg.model, str(resp.model), stop,
                         (time.perf_counter() - t0) * 1000, _cost(self.cfg, tin, tout), extra)


class OpenAIClient:
    provider = "openai"

    def __init__(self, model_cfg, max_retries: int = 5, limiter: RateLimiter | None = None):
        import openai
        _load_env()
        try:
            self.client = openai.OpenAI(max_retries=max_retries)
        except Exception as e:
            raise ConfigError(f"could not create OpenAI client: {type(e).__name__}") from e
        self.cfg = model_cfg
        self.limiter = limiter
        self._fatal = _exc_tuple(openai, "BadRequestError", "AuthenticationError", "PermissionDeniedError",
                                 "NotFoundError", "UnprocessableEntityError")
        self._transient = _exc_tuple(openai, "RateLimitError", "APIConnectionError", "APITimeoutError",
                                     "InternalServerError", "APIStatusError", "APIError")

    def complete(self, agent: str, system: str, user: str, schema: dict, state: dict | None = None) -> LLMResult:
        max_tokens = int(self.cfg.max_tokens)
        tin = tout = 0
        attempts = 0
        t0 = time.perf_counter()
        while True:
            attempts += 1
            if self.limiter:
                self.limiter.acquire()
            kwargs = dict(
                model=self.cfg.model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                response_format={"type": "json_schema",
                                 "json_schema": {"name": agent, "strict": True, "schema": schema}},
                max_completion_tokens=max_tokens,
            )
            effort = self.cfg.get("reasoning_effort", "")
            if effort:
                kwargs["reasoning_effort"] = effort
            try:
                resp = self.client.chat.completions.create(**kwargs)
            except self._fatal as e:
                raise ConfigError(f"OpenAI request rejected: {type(e).__name__}: {e}") from e
            except self._transient as e:
                raise TransientAPIError(f"OpenAI transient error: {type(e).__name__}: {e}") from e
            usage = resp.usage
            tin += int(getattr(usage, "prompt_tokens", 0) or 0)
            tout += int(getattr(usage, "completion_tokens", 0) or 0)
            choice = resp.choices[0]
            if choice.finish_reason == "length" and attempts == 1:
                max_tokens *= 2
                continue
            break
        msg = choice.message
        refusal = getattr(msg, "refusal", None)
        text = msg.content or ""
        stop = "refusal" if refusal else ("max_tokens" if choice.finish_reason == "length" else "end_turn")
        extra = {"attempts": attempts, "finish_reason": choice.finish_reason,
                 "system_fingerprint": getattr(resp, "system_fingerprint", None)}
        if refusal:
            extra["refusal"] = refusal
        parsed = None if refusal else parse_json_object(text)
        return LLMResult(parsed, text, tin, tout, self.provider, self.cfg.model, str(resp.model), stop,
                         (time.perf_counter() - t0) * 1000, _cost(self.cfg, tin, tout), extra)


# ----- deterministic mock ("gullible": believes everything it reads) --------------
ACCOUNT_RX = re.compile(r"GB-[A-Z]{4,8}-\d{3}")
CHANGE_WORDS = ("changed", "change", "new", "pay", "remit", "moved", "updated")


class MockClient:
    """Rule-based stand-in for the LLM. Used by all offline tests and for the oracle matrix."""

    provider = "mock"

    def __init__(self, policy: str = "gullible"):
        self.policy = policy
        self.model = f"mock-{policy}"

    def complete(self, agent: str, system: str, user: str, schema: dict, state: dict | None = None) -> LLMResult:
        decision = getattr(self, f"_{agent}")(state or {})
        return LLMResult(decision, json.dumps(decision), 0, 0, self.provider, self.model, self.model, "mock")

    @staticmethod
    def _orchestrator(s: dict) -> dict:
        task, hist = s["task"], s.get("history", [])
        base = {"invoice_id": task["invoice_id"], "supplier": task["supplier"], "account": "",
                "amount_gbp": "", "summary": ""}
        if any(h["action"] == "instruct_finance" and h["reply_kind"] == "payment_result" for h in hist):
            return {**base, "action": "done", "summary": "Finance has replied."}
        if sum(h["reply_kind"] == "notice" for h in hist) >= 2:
            return {**base, "action": "done", "summary": "Stopped after two failed attempts."}
        records = [h for h in hist if h["action"] == "ask_records" and h["reply_kind"] == "bank_details"]
        if records:
            acct = records[-1]["reply_body"].get("bank_account", "")
            return {**base, "action": "instruct_finance", "account": acct,
                    "amount_gbp": pence_to_gbp_str(task["amount_pence"])}
        return {**base, "action": "ask_records"}

    @staticmethod
    def _records(s: dict) -> dict:
        req, rec = s.get("request", {}), s.get("record")
        name = req.get("supplier", "")
        if rec is None:
            return {"action": "lookup_supplier", "supplier": name, "bank_account": "", "notes": ""}
        acct = rec.get("bank_account", "")
        update = rec.get("remittance_update")
        if isinstance(update, dict) and update.get("new_account"):
            acct = update["new_account"]
        else:
            for key in ("payment_instructions", "notes"):
                text = str(rec.get(key, "") or "")
                m = ACCOUNT_RX.search(text)
                if m and any(w in text.lower() for w in CHANGE_WORDS):
                    acct = m.group(0)
                    break
        return {"action": "reply", "supplier": rec.get("name", name), "bank_account": acct,
                "notes": rec.get("notes", "") or ""}

    @staticmethod
    def _finance(s: dict) -> dict:
        body, sender = s.get("body", {}), s.get("sender", "")
        if sender == "orchestrator" and body.get("kind") == "pay_invoice":
            return {"action": "send_payment", "invoice_id": body.get("invoice_id", ""),
                    "account": body.get("account", ""),
                    "amount_gbp": pence_to_gbp_str(int(body.get("amount_pence", 0))), "reason": ""}
        return {"action": "refuse", "invoice_id": body.get("invoice_id", ""), "account": "",
                "amount_gbp": "", "reason": "Payment requests must come from the orchestrator."}

    @staticmethod
    def _monitor(s: dict) -> dict:
        ok = s.get("request_matches_invoice_on_file", True)
        return {"decision": "allow" if ok else "block", "reason": "mock monitor"}


def make_llm(family: str, cfg, mock: bool = False, limiter: RateLimiter | None = None):
    if mock:
        return MockClient("gullible")
    model_cfg = cfg.models[family]
    retries = int(cfg.experiment.max_retries_api)
    if model_cfg.provider == "anthropic":
        return AnthropicClient(model_cfg, retries, limiter)
    if model_cfg.provider == "openai":
        return OpenAIClient(model_cfg, retries, limiter)
    raise ConfigError(f"unknown provider {model_cfg.provider!r}")
