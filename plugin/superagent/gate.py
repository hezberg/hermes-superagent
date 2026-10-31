"""The Gate: deterministic admission control in front of the Router.

Pure logic, no Hermes imports — unit-testable in isolation. Modelled on
the Eval gate in DeepSeek's dsh-superagent-prototype: the Gate runs
BEFORE any model judgement and decides the *strength* of a request:

  explicit — the sender is on the source's allowed list and addressed
             the agent directly. Real work may start.
  inferred — a proactive candidate: a configured rule matched, or a
             listed bot produced the event. Work may start only when
             the accept mode is `auto`; in `observe` mode the candidate
             is recorded ("would accept") and nothing runs.

Everything else is rejected by the Gate and never reaches a model.

An *event* is a plain dict:
  {source, sender, addressed (bool), is_stop (bool),
   is_bot (bool), rule_match (bool), rule_id (optional)}

A *decision* is a plain dict:
  {outcome: accept | observe | stop | ignore | reject,
   strength: explicit | inferred | None,
   basis: {...}}   — the facts the decision rests on; on an accept this
                     becomes the core of the task's Mandate.
"""
import hashlib
import json

IMPLICIT_ALLOWED_SOURCES = {"cli"}  # the local operator is always allowed


def policy_version(policy):
    """Stable fingerprint of the policy block.

    Recorded on every Mandate, so a task always names the exact rules it
    was accepted under. Changes whenever rules, mode, sources or bots do.
    """
    policy = policy or {}
    canonical = {
        "accept_mode": policy.get("accept_mode", "observe"),
        "sources": policy.get("sources") or {},
        "bots": policy.get("bots") or [],
        "rules": policy.get("rules") or [],
    }
    blob = json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:12]


def accept_mode(policy, events_cfg=None):
    """Effective accept mode, with the v0.1 `speculative_execution`
    boolean honoured as a legacy alias when no policy block exists."""
    policy = policy or {}
    if "accept_mode" in policy:
        return policy.get("accept_mode") or "observe"
    if events_cfg and events_cfg.get("speculative_execution"):
        return "auto"
    return "observe"


def _allowed_senders(policy, source):
    sources = (policy or {}).get("sources") or {}
    cfg = sources.get(source) or {}
    return cfg.get("allowed_senders") or []


def _is_allowed(policy, source, sender):
    if source in IMPLICIT_ALLOWED_SOURCES:
        return True
    return sender is not None and sender in _allowed_senders(policy, source)


def evaluate(event, policy):
    """Run the Gate over one event and return the decision dict."""
    policy = policy or {}
    source = event.get("source")
    sender = event.get("sender")
    basis = {"source": source, "sender": sender, "via": None}

    # A stop from an allowed sender always wins, whatever the mode.
    if event.get("is_stop") and _is_allowed(policy, source, sender):
        basis["via"] = "addressed"
        return {"outcome": "stop", "strength": "explicit", "basis": basis}

    # Explicit path: allowed sender, directly addressed.
    if event.get("addressed"):
        if _is_allowed(policy, source, sender):
            basis["via"] = "addressed"
            return {"outcome": "accept", "strength": "explicit", "basis": basis}
        basis["via"] = "not_allowed"
        return {"outcome": "reject", "strength": None, "basis": basis}

    # Inferred path: proactive candidates.
    via = None
    if event.get("is_bot") and sender in (policy.get("bots") or []):
        via = "bot"
    elif event.get("rule_match"):
        via = "rule"
        basis["rule_id"] = event.get("rule_id")
    if via is None:
        return {"outcome": "ignore", "strength": None, "basis": basis}
    basis["via"] = via
    if accept_mode(policy) == "auto":
        return {"outcome": "accept", "strength": "inferred", "basis": basis}
    return {"outcome": "observe", "strength": "inferred", "basis": basis}


def make_mandate(policy, *, source, sender, strength, scope, basis, now):
    """Build the immutable Mandate recorded on an accepted task.

    The Mandate states why the work may be done and how far it may go:
    the policy version it was accepted under, its scope, its strength,
    and the Gate basis. Widening the scope means a new task, never an
    edited Mandate.
    """
    return {
        "policy_version": policy_version(policy),
        "source": source,
        "sender": sender,
        "strength": strength,
        "scope": scope,
        "basis": basis,
        "accepted_at": now,
    }


def mandate_block(mandate):
    """Render a Mandate as the fixed header block of a Kanban card body."""
    lines = [
        "## Mandate",
        f"- policy_version: {mandate.get('policy_version')}",
        f"- source: {mandate.get('source')} · sender: {mandate.get('sender')}",
        f"- strength: {mandate.get('strength')} · via: {(mandate.get('basis') or {}).get('via')}",
        f"- scope: {mandate.get('scope')}",
    ]
    return "\n".join(lines)
