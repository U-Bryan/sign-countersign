"""The three honest agents: Orchestrator, Records and Finance.

Each LLM call is stateless: the agent's system prompt plus one user message that renders
its working memory (task, messages and tool results so far, in order). The rendering is
identical under every defence. Agents never read Message.origin.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from defences.base import Allow, PaymentRequest
from message import (BANK_DETAILS, GET_BANK_DETAILS, NOTICE, PAY_INVOICE, PAYMENT_RESULT, Message, new_msg_id,
                     parse_gbp_to_pence, render_body, render_for_agent)
from schemas import SCHEMAS, validate

ROOT = Path(__file__).resolve().parent
PROMPT_DIR = ROOT / "prompts"
AGENT_NAMES = ("orchestrator", "records", "finance")


def load_prompts() -> dict[str, str]:
    return {a: (PROMPT_DIR / f"{a}.txt").read_text(encoding="utf-8") for a in AGENT_NAMES}


PROMPTS = load_prompts()


def prompts_sha256(prompts: dict[str, str] | None = None) -> str:
    p = prompts or PROMPTS
    h = hashlib.sha256()
    for name in sorted(p):
        h.update(name.encode("utf-8") + b"\n" + p[name].encode("utf-8") + b"\n")
    return h.hexdigest()


PROMPT_SHA = prompts_sha256()


@dataclass
class AgentStats:
    llm_calls: int = 0
    parse_failures: int = 0
    refusals: int = 0
    max_tokens_stops: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    models_returned: set = field(default_factory=set)


class AgentRuntime:
    """Shared per-trial plumbing: LLM calls with validation, one repair attempt and logging."""

    def __init__(self, world, bus, logger, llm, cfg, defence, rng, clock):
        self.world, self.bus, self.log, self.llm = world, bus, logger, llm
        self.cfg, self.defence, self.rng, self.clock = cfg, defence, rng, clock
        self.stats = AgentStats()

    def _call(self, agent: str, user: str, state: dict, attempt: int):
        system = PROMPTS[agent]
        res = self.llm.complete(agent, system, user, SCHEMAS[agent], state)
        s = self.stats
        s.llm_calls += 1
        s.tokens_in += res.input_tokens
        s.tokens_out += res.output_tokens
        s.cost_usd += res.cost_usd
        s.models_returned.add(res.model_returned)
        if res.stop_reason == "refusal":
            s.refusals += 1
        if res.stop_reason == "max_tokens":
            s.max_tokens_stops += 1
        self.log.log("llm_call", agent=agent, attempt=attempt, provider=res.provider,
                     model_requested=res.model_requested, model_returned=res.model_returned,
                     prompt_sha=hashlib.sha256(system.encode("utf-8")).hexdigest(),
                     user_sha=hashlib.sha256(user.encode("utf-8")).hexdigest(),
                     input_tokens=res.input_tokens, output_tokens=res.output_tokens,
                     latency_ms=round(res.latency_ms, 2), stop_reason=res.stop_reason,
                     cost_usd=res.cost_usd, text=res.text[:4000], parsed=res.parsed, extra=res.extra,
                     user=user[:4000])
        return res

    def decide(self, agent: str, user: str, state: dict) -> dict | None:
        """One validated decision, with at most one repair call. None = the agent did not act."""
        res = self._call(agent, user, state, attempt=1)
        if res.stop_reason == "refusal":
            return None
        err = validate(agent, res.parsed) if res.parsed is not None else "the reply was not valid JSON"
        if err is None:
            return res.parsed
        self.stats.parse_failures += 1
        self.log.log("parse_failure", agent=agent, attempt=1, error=err, text=res.text[:2000])
        repair = f"{user}\nYour previous reply was not valid: {err}. Reply again with one JSON object."
        res2 = self._call(agent, repair, state, attempt=2)
        if res2.stop_reason == "refusal":
            return None
        err2 = validate(agent, res2.parsed) if res2.parsed is not None else "the reply was not valid JSON"
        if err2 is None:
            return res2.parsed
        self.stats.parse_failures += 1
        self.log.log("parse_failure", agent=agent, attempt=2, error=err2, text=res2.text[:2000], final=True)
        return None

    def new_message(self, sender: str, recipient: str, task_id: str, body: dict) -> Message:
        return Message(new_msg_id(self.rng), sender, recipient, self.clock.agent_now_ms(sender), task_id, body)


def _indent(text: str, pad: str = "   ") -> str:
    return "\n".join(pad + line if line else line for line in text.rstrip("\n").split("\n"))


class Orchestrator:
    name = "orchestrator"

    def __init__(self, rt: AgentRuntime):
        self.rt = rt

    def render(self, task, memory: list[str]) -> str:
        happened = "\n".join(memory) if memory else "Nothing has happened yet."
        return (f"User task (task_id {task.task_id}): {task.text}\n\n"
                f"What has happened so far:\n{happened}\n\n"
                "Choose your next action.")

    def run(self, task) -> dict:
        rt = self.rt
        memory: list[str] = []
        history: list[dict] = []
        outcome = {"finished": False, "steps": 0, "summary": ""}
        state_task = task.to_dict()
        for step in range(int(rt.cfg.experiment.max_orchestrator_steps)):
            outcome["steps"] = step + 1
            d = rt.decide(self.name, self.render(task, memory), {"task": state_task, "history": history})
            if d is None:
                rt.log.log("agent_gave_up", agent=self.name, step=step + 1)
                break
            if d["action"] == "done":
                outcome.update(finished=True, summary=d["summary"])
                rt.log.log("orchestrator_done", summary=d["summary"], step=step + 1)
                break
            if d["action"] == "ask_records":
                to = "records"
                body = {"kind": GET_BANK_DETAILS,
                        "invoice_id": d["invoice_id"].strip() or task.invoice_id,
                        "supplier": d["supplier"].strip() or task.supplier}
            else:  # instruct_finance
                to = "finance"
                body = {"kind": PAY_INVOICE, "invoice_id": d["invoice_id"].strip(),
                        "supplier": d["supplier"].strip(), "account": d["account"].strip(),
                        "amount_pence": parse_gbp_to_pence(d["amount_gbp"])}
            msg = rt.new_message(self.name, to, task.task_id, body)
            reply = rt.bus.request(msg)
            n = len(history) + 1
            memory.append(f"{n}. You sent to {to}: {json.dumps(render_body(body), ensure_ascii=False)}")
            if reply.kind == NOTICE:
                memory.append(f"   Your message to {to} was not delivered: {reply.body.get('text', '')}")
            else:
                memory.append("   Reply received:\n" + _indent(render_for_agent(reply)))
            history.append({"action": d["action"], "to": to, "sent_body": body, "reply_kind": reply.kind,
                            "reply_sender": reply.sender, "reply_body": dict(reply.body)})
        else:
            rt.log.log("step_limit_reached", agent=self.name)
        return outcome


class RecordsAgent:
    name = "records"

    def __init__(self, rt: AgentRuntime):
        self.rt = rt

    def handle(self, msg: Message, verdict) -> Message:
        rt = self.rt
        if msg.kind != GET_BANK_DETAILS:
            return rt.new_message(self.name, msg.sender, msg.task_id,
                                  {"kind": BANK_DETAILS, "supplier": "", "bank_account": "",
                                   "notes": "unsupported request"})
        parts = [render_for_agent(msg)]
        record = None
        d = rt.decide(self.name, "\n".join(parts) + "\nDecide what to do.", {"request": msg.body, "record": None})
        lookups = 0
        while d is not None and d["action"] == "lookup_supplier" and lookups < 2:
            lookups += 1
            name = d["supplier"].strip()
            record = rt.world.supplier_record(name)
            shown = record if record is not None else {"error": "no supplier with that name"}
            rt.log.log("tool_call", agent=self.name, tool="lookup_supplier", args={"name": name}, result=shown)
            parts.append(f"Tool result (lookup_supplier for {json.dumps(name, ensure_ascii=False)}):\n"
                         f"{json.dumps(shown, ensure_ascii=False)}")
            d = rt.decide(self.name, "\n".join(parts) + "\nDecide what to do.",
                          {"request": msg.body, "record": record})
        if d is None or d["action"] != "reply":
            body = {"kind": BANK_DETAILS, "supplier": msg.body.get("supplier", ""), "bank_account": "", "notes": ""}
        else:
            body = {"kind": BANK_DETAILS, "supplier": d["supplier"], "bank_account": d["bank_account"].strip(),
                    "notes": d["notes"]}
        return rt.new_message(self.name, msg.sender, msg.task_id, body)


class FinanceAgent:
    name = "finance"

    def __init__(self, rt: AgentRuntime):
        self.rt = rt

    def handle(self, msg: Message, verdict) -> Message:
        rt = self.rt
        d = rt.decide(self.name, render_for_agent(msg) + "\nDecide what to do.",
                      {"sender": msg.sender, "body": msg.body})
        invoice_id = str(msg.body.get("invoice_id", ""))
        if d is None:
            status, detail = "error", "no valid decision"
        elif d["action"] == "refuse":
            status, detail, invoice_id = "refused", d["reason"], d["invoice_id"] or invoice_id
        else:
            req = PaymentRequest(d["invoice_id"].strip(), d["account"].strip(),
                                 int(parse_gbp_to_pence(d["amount_gbp"])))
            invoice_id = req.invoice_id
            rt.log.log("tool_call", agent=self.name, tool="send_payment",
                       args={"invoice_id": req.invoice_id, "account": req.account,
                             "amount_pence": req.amount_pence},
                       trigger_msg_id=msg.msg_id, attributed_sender=verdict.attributed_sender)
            gate = rt.defence.payment_gate(req, msg, verdict)
            if isinstance(gate, Allow):
                rt.world.send_payment(req.invoice_id, req.account, req.amount_pence,
                                      verdict.attributed_sender, verdict.basis, msg.msg_id)
                status, detail = "paid", f"paid {req.invoice_id}"
            else:
                status, detail = "blocked", "payment was not executed"
        return rt.new_message(self.name, msg.sender, msg.task_id,
                              {"kind": PAYMENT_RESULT, "invoice_id": invoice_id, "status": status,
                               "detail": detail})


@dataclass
class Agents:
    runtime: AgentRuntime
    orchestrator: Orchestrator
    records: RecordsAgent
    finance: FinanceAgent


def make_agents(world, bus, logger, llm, cfg, defence, rng, clock) -> Agents:
    rt = AgentRuntime(world, bus, logger, llm, cfg, defence, rng, clock)
    agents = Agents(rt, Orchestrator(rt), RecordsAgent(rt), FinanceAgent(rt))
    bus.register_endpoint("records", agents.records.handle)
    bus.register_endpoint("finance", agents.finance.handle)
    bus.register_endpoint("orchestrator", lambda m, v: None)  # never receives unsolicited requests
    return agents
