from datetime import datetime
from pathlib import Path

LOG_PATH = Path("supervisor_log.txt")
# Creates a timestamped oneline entries in a text log file.
def write_event(event: str, details: dict):
    """
    Append a one-line audit entry for supervisor demos.
    Example line:
    2025-10-22T12:34:56.789123 | CREATE | id=5 ; model=gpt-4o-mini ; chars=42
    """
    ts = datetime.utcnow().isoformat()
    parts = [f"{k}={str(v)[:200]}" for k, v in (details or {}).items()]
    line = f"{ts} | {event} | " + " ; ".join(parts)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
# Each entry will include the UTC timestamp, the event time and, a compact list of key value pairs describing  details.