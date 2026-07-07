import json
import logging
from pathlib import Path
import time
from typing import Any

from app.config import config


Path(config.log_path).parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


class EventLogger:
    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def event(self, event_type: str, **fields: Any) -> None:
        record = {
            "time": time.time(),
            "type": event_type,
            **fields,
        }
        logging.info("%s %s", event_type, fields)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()[-limit:]
        records = []
        for line in lines:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                records.append({"type": "log_parse_error", "raw": line})
        return records


event_logger = EventLogger(config.log_path)

