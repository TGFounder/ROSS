"""Local telemetry. Nothing leaves the machine. Every figure carries its class."""
CLASSES = ("MEASURED", "COUNTED", "ESTIMATED", "INFERRED")


class Telemetry:
    def __init__(self, store=None, session_id=None):
        self.store, self.session_id, self.rows = store, session_id, []

    def __call__(self, kind, value, cls):
        assert cls in CLASSES, cls
        self.rows.append((kind, value, cls))
        if self.store is not None:
            self.store.metric(kind, value, cls, self.session_id)

    def summary(self):
        out = {}
        for kind, value, cls in self.rows:
            out.setdefault((kind, cls), 0)
            out[(kind, cls)] += value
        return out
