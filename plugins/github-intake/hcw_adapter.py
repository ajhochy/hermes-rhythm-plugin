from __future__ import annotations


class TransientDispatchError(Exception):
    pass


class PermanentDispatchError(Exception):
    pass


class DryRunSink:
    """Default recording dry-run adapter — no real HCW dispatch."""

    def __init__(self):
        self.dispatched = []
        self.is_dry_run = True

    def dispatch(self, intent) -> dict:
        self.dispatched.append(intent)
        return {"status": "recorded", "intent": intent}
