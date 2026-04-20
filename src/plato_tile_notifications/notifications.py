"""Tile notifications — delivery channels, templates, batching, and preferences."""
import time
from dataclasses import dataclass, field
from typing import Optional, Callable
from collections import defaultdict
from enum import Enum

class Channel(Enum):
    IN_APP = "in_app"
    WEBHOOK = "webhook"
    LOG = "log"
    CALLBACK = "callback"
    DIGEST = "digest"

class Priority(Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"

@dataclass
class Notification:
    id: str
    recipient: str
    title: str
    body: str
    channel: Channel = Channel.IN_APP
    priority: Priority = Priority.NORMAL
    tile_id: str = ""
    room: str = ""
    read: bool = False
    delivered: bool = False
    delivered_at: float = 0.0
    created_at: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)

@dataclass
class DeliveryPreference:
    agent: str
    channels: list[Channel] = field(default_factory=lambda: [Channel.IN_APP])
    min_priority: Priority = Priority.LOW
    quiet_hours_start: int = 23  # 11pm
    quiet_hours_end: int = 8     # 8am
    digest_enabled: bool = True
    digest_interval: float = 3600.0

class NotificationSystem:
    def __init__(self):
        self._inbox: dict[str, list[Notification]] = defaultdict(list)
        self._digest_queue: dict[str, list[Notification]] = defaultdict(list)
        self._preferences: dict[str, DeliveryPreference] = {}
        self._templates: dict[str, str] = {}
        self._handlers: dict[str, Callable] = {}
        self._delivery_log: list[dict] = []
        self._notif_counter: int = 0

    def send(self, recipient: str, title: str, body: str, channel: str = "in_app",
             priority: str = "normal", tile_id: str = "", room: str = "",
             metadata: dict = None) -> Notification:
        self._notif_counter += 1
        notif = Notification(id=f"n-{self._notif_counter}", recipient=recipient,
                           title=title, body=body, channel=Channel(channel),
                           priority=Priority(priority), tile_id=tile_id, room=room,
                           metadata=metadata or {})
        # Check preferences
        pref = self._preferences.get(recipient)
        if pref:
            hour = time.localtime().time().hour
            if pref.quiet_hours_end <= hour < pref.quiet_hours_start:
                if pref.digest_enabled:
                    self._digest_queue[recipient].append(notif)
                    return notif
            if pref.channels and Channel(channel) not in pref.channels:
                notif.delivered = False
                self._inbox[recipient].append(notif)
                return notif
        # Deliver
        notif.delivered = True
        notif.delivered_at = time.time()
        self._inbox[recipient].append(notif)
        if len(self._inbox[recipient]) > 500:
            self._inbox[recipient] = self._inbox[recipient][-500:]
        # Run handler
        handler = self._handlers.get(channel)
        if handler:
            try:
                handler(notif)
            except Exception:
                pass
        self._delivery_log.append({"id": notif.id, "recipient": recipient,
                                   "channel": channel, "priority": priority,
                                   "delivered": notif.delivered, "timestamp": time.time()})
        if len(self._delivery_log) > 2000:
            self._delivery_log = self._delivery_log[-2000:]
        return notif

    def send_template(self, recipient: str, template_name: str, context: dict,
                      **kwargs) -> Optional[Notification]:
        template = self._templates.get(template_name)
        if not template:
            return None
        title = template.get("title", "").format(**context)
        body = template.get("body", "").format(**context)
        return self.send(recipient, title, body,
                        channel=kwargs.get("channel", template.get("channel", "in_app")),
                        priority=kwargs.get("priority", template.get("priority", "normal")),
                        **kwargs)

    def register_template(self, name: str, title: str, body: str,
                          channel: str = "in_app", priority: str = "normal"):
        self._templates[name] = {"title": title, "body": body,
                                "channel": channel, "priority": priority}

    def register_handler(self, channel: str, fn: Callable):
        self._handlers[channel] = fn

    def set_preference(self, agent: str, channels: list[str] = None,
                       min_priority: str = "low", quiet_start: int = 23,
                       quiet_end: int = 8, digest: bool = True):
        self._preferences[agent] = DeliveryPreference(
            agent=agent,
            channels=[Channel(c) for c in channels] if channels else [Channel.IN_APP],
            min_priority=Priority(min_priority),
            quiet_hours_start=quiet_start, quiet_hours_end=quiet_end,
            digest_enabled=digest)

    def inbox(self, recipient: str, unread_only: bool = False,
              limit: int = 50) -> list[Notification]:
        msgs = self._inbox.get(recipient, [])
        if unread_only:
            msgs = [m for m in msgs if not m.read]
        return list(reversed(msgs))[:limit]

    def mark_read(self, recipient: str, notification_id: str) -> bool:
        for n in self._inbox.get(recipient, []):
            if n.id == notification_id:
                n.read = True
                return True
        return False

    def mark_all_read(self, recipient: str) -> int:
        count = 0
        for n in self._inbox.get(recipient, []):
            if not n.read:
                n.read = True
                count += 1
        return count

    def flush_digest(self, recipient: str) -> list[Notification]:
        pending = self._digest_queue.pop(recipient, [])
        results = []
        for n in pending:
            n.delivered = True
            n.delivered_at = time.time()
            self._inbox[recipient].append(n)
            results.append(n)
        return results

    def unread_count(self, recipient: str) -> int:
        return sum(1 for n in self._inbox.get(recipient, []) if not n.read)

    @property
    def stats(self) -> dict:
        total_inbox = sum(len(v) for v in self._inbox.values())
        unread = sum(sum(1 for n in v if not n.read) for v in self._inbox.values())
        return {"notifications": self._notif_counter, "inbox_size": total_inbox,
                "unread": unread, "templates": len(self._templates),
                "preferences": len(self._preferences),
                "pending_digests": sum(len(v) for v in self._digest_queue.values())}
