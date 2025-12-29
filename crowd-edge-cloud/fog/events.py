import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Dict


@dataclass
class FogEvent:
    event_id: str
    event_type: str
    camera_id: str
    people_count: int
    timestamp: str

    def to_dict(self) -> Dict[str, str]:
        """Convierte el evento a diccionario listo para serializar."""
        return asdict(self)


def build_event(event_type: str, camera_id: str, people_count: int) -> FogEvent:
    """Crea un evento con UUID y timestamp en UTC."""
    now_iso = datetime.now(timezone.utc).isoformat()
    return FogEvent(
        event_id=str(uuid.uuid4()),
        event_type=event_type,
        camera_id=camera_id,
        people_count=people_count,
        timestamp=now_iso,
    )
