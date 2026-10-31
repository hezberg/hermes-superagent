"""Fast Path classification for incoming events.

Pure logic, no Hermes imports — unit-testable in isolation.

Rules come from superagent.yaml `events.fastpath`: a list of
{pattern: <regex>, action: passthrough|drop|slowpath}. The first matching
rule wins; anything unmatched (or a broken rule) falls back to "slowpath",
i.e. normal Router handling. The Fast Path can only ever *skip* the
Router's judgement for messages the operator explicitly pattern-matched.
"""
import re

ACTIONS = {"passthrough", "drop", "slowpath"}
DEFAULT = "slowpath"


def classify(text, rules):
    """Return the fastpath action for an incoming message text."""
    if not text:
        return DEFAULT
    for rule in rules or []:
        if not isinstance(rule, dict):
            continue
        pattern = rule.get("pattern")
        if not pattern:
            continue
        try:
            matched = re.search(pattern, text) is not None
        except re.error:
            continue  # a broken operator regex must never break the gateway
        if matched:
            action = rule.get("action", DEFAULT)
            return action if action in ACTIONS else DEFAULT
    return DEFAULT
