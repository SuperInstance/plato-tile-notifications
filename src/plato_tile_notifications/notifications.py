"""Event-driven tile notification system."""
import time
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

class NotificationType(Enum):
    TILE_CREATED = "tile_created"
    TILE_UPDATED = "tile_updated"
    TILE_GHOSTED = "tile_ghosted"
    TILE_RESURRECTED = "tile_resurrected"
    TILE_DELETED = "tile_deleted"
    TILE_SCORED = "tile_scored"
    TILE_PROMOTED = "tile_promoted"
    TILE_FLAGGED = "tile_flagged"
    ROOM_CHANGE = "room_change"

@dataclass
class Notification:
    ntype: NotificationType
    tile_id: str
    message: str
    source: str = ""
    timestamp: float = field(default_factory=time.time)
    read: bool = False
    priority: int = 0

class TileNotifications:
    def __init__(self, max_notifications: int = 500):
        self.max = max_notifications
        self._inbox: list[Notification] = []
        self._subscriptions: dict[str, set[NotificationType]] = defaultdict(set)
        self._handlers: dict[str, list] = defaultdict(list)

    def subscribe(self, agent: str, ntypes: list[str] = None):
        if ntypes:
            for nt in ntypes:
                self._subscriptions[agent].add(NotificationType(nt))
        else:
            self._subscriptions[agent] = set(NotificationType)

    def unsubscribe(self, agent: str):
        self._subscriptions.pop(agent, None)

    def on(self, ntype: str, handler):
        self._handlers[ntype].append(handler)

    def emit(self, ntype: str, tile_id: str, message: str, source: str = "", priority: int = 0) -> Notification:
        notif = Notification(ntype=NotificationType(ntype), tile_id=tile_id,
                           message=message, source=source, priority=priority)
        self._inbox.append(notif)
        if len(self._inbox) > self.max:
            self._inbox = self._inbox[-self.max:]
        for handler in self._handlers.get(ntype, []):
            try:
                handler(notif)
            except Exception:
                pass
        return notif

    def for_agent(self, agent: str, unread_only: bool = True, limit: int = 50) -> list[Notification]:
        subscribed = self._subscriptions.get(agent, set())
        if not subscribed:
            return []
        results = [n for n in self._inbox if n.ntype in subscribed]
        if unread_only:
            results = [n for n in results if not n.read]
        results.sort(key=lambda n: (n.priority, n.timestamp), reverse=True)
        return results[:limit]

    def mark_read(self, tile_id: str = "", ntype: str = ""):
        for n in self._inbox:
            if (not tile_id or n.tile_id == tile_id) and (not ntype or n.ntype.value == ntype):
                n.read = True

    def unread_count(self, agent: str) -> int:
        return len(self.for_agent(agent, unread_only=True, limit=1000))

    @property
    def stats(self) -> dict:
        types = defaultdict(int)
        for n in self._inbox:
            types[n.ntype.value] += 1
        return {"total": len(self._inbox),
                "unread": sum(1 for n in self._inbox if not n.read),
                "subscribers": len(self._subscriptions),
                "types": dict(types)}
