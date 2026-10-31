"""Outbox: store-first message delivery with per-conversation ordering.

Adapted from dsh-superagent-prototype's stored-work discipline: a
message is written to the store BEFORE anything tries to send it, the
send happens afterwards, and failures retry instead of vanishing.

Ordering rule: messages of one ticket to one conversation go out in
queue order — a message waits while an earlier one to the same
(ticket, conversation) is unsent, UNLESS that earlier one has failed
MAX_FAILURES times in a row, in which case it is flagged as a problem
and stops holding the queue back.

Storage is a single JSON file; every operation loads, mutates and saves
(atomic via rename). Volumes here are human-scale, so this is plenty.
"""
import json
import os
import time

MAX_FAILURES = 3


class Outbox:
    def __init__(self, path):
        self.path = path

    # -- storage ------------------------------------------------------
    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"seq": 0, "messages": []}

    def _save(self, state):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    # -- queue --------------------------------------------------------
    def enqueue(self, ticket, conversation, body, now=None):
        state = self._load()
        state["seq"] += 1
        msg = {
            "id": f"m{state['seq']}",
            "ticket": ticket,
            "conversation": conversation,
            "body": body,
            "queued_at": now if now is not None else time.time(),
            "failures": 0,
            "sent_at": None,
        }
        state["messages"].append(msg)
        self._save(state)
        return msg["id"]

    def due(self):
        """Messages that may be sent now, in queue order."""
        state = self._load()
        ready = []
        blocked_keys = set()
        for msg in state["messages"]:
            if msg["sent_at"] is not None:
                continue
            key = (msg["ticket"], msg["conversation"])
            if key in blocked_keys:
                continue
            if msg["failures"] >= MAX_FAILURES:
                # A problem message no longer holds back its queue —
                # but it is not itself due again without intervention.
                continue
            ready.append(msg)
            blocked_keys.add(key)  # later ones wait for this one
        return ready

    def mark_sent(self, msg_id, now=None):
        state = self._load()
        for msg in state["messages"]:
            if msg["id"] == msg_id:
                msg["sent_at"] = now if now is not None else time.time()
        self._save(state)

    def mark_failed(self, msg_id):
        state = self._load()
        for msg in state["messages"]:
            if msg["id"] == msg_id:
                msg["failures"] += 1
        self._save(state)

    def problems(self):
        """Unsent messages that failed MAX_FAILURES times: system problems."""
        state = self._load()
        return [
            m
            for m in state["messages"]
            if m["sent_at"] is None and m["failures"] >= MAX_FAILURES
        ]
