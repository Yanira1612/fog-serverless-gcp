import json
import os
from typing import Callable, Dict, List


class DiskBuffer:
    """Buffer local en disco para reenviar eventos cuando falle la red."""

    def __init__(self, path: str, max_pending: int = 1000):
        self.path = path
        self.max_pending = max_pending
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    def _read_events(self) -> List[Dict]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, "r", encoding="utf-8") as f:
            return [json.loads(line.strip()) for line in f if line.strip()]

    def _write_events(self, events: List[Dict]) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")

    def save_event(self, event: Dict) -> None:
        """Guarda un evento fallido para reintentar más tarde."""
        events = self._read_events()
        events.append(event)
        events = events[-self.max_pending :]
        self._write_events(events)

    def flush(self, send_func: Callable[[Dict], bool]) -> int:
        """Reintenta enviar todos los eventos pendientes.

        Retorna la cantidad de eventos reenviados con éxito.
        """
        events = self._read_events()
        if not events:
            return 0

        remaining = []
        sent_count = 0
        for ev in events:
            if send_func(ev):
                sent_count += 1
            else:
                remaining.append(ev)

        self._write_events(remaining)
        return sent_count
