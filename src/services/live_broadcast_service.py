"""RouteWise Live SSE Broadcasting Service.

Manages Server-Sent Events (SSE) subscriptions and real-time event dissemination
for the NH-44 Ramban-Banihal predictive corridor platform.

Supported Event Types:
- heartbeat: Periodic keep-alive signal emitted every 20s
- risk_update: Disseminated upon ST-GNN live risk recomputations
- event_update: Disseminated on hazard event creation, verification, or resolution
- alert: Advisory warnings and operational escalation triggers
- route_update: Journey planner recalculation alerts
- status: High-level system state, provider metrics, and data age changes
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

logger = logging.getLogger("routewise.live_broadcast")


class LiveBroadcaster:
    """Thread-safe pub/sub broadcaster distributing real-time SSE frames to active clients."""

    def __init__(self, max_queue_size: int = 100):
        self._subscribers: Set[asyncio.Queue] = set()
        self._max_queue_size = max_queue_size

    @property
    def subscriber_count(self) -> int:
        """Returns the number of currently active SSE subscriber queues."""
        return len(self._subscribers)

    def subscribe(self) -> asyncio.Queue:
        """Creates and registers a new subscriber queue."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue_size)
        self._subscribers.add(queue)
        logger.debug("SSE client subscribed (total active: %d)", len(self._subscribers))
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Removes a subscriber queue from active broadcast targets."""
        self._subscribers.discard(queue)
        logger.debug("SSE client unsubscribed (remaining active: %d)", len(self._subscribers))

    async def broadcast(self, event_type: str, data: Dict[str, Any]) -> None:
        """Asynchronously dispatches an event frame to all registered subscriber queues."""
        payload = {
            "event": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        for q in list(self._subscribers):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning("Subscriber queue is full; dropping frame to avoid latency lag.")
            except Exception as e:
                logger.debug("Error delivering to subscriber queue: %s", e)

    def broadcast_sync(self, event_type: str, data: Dict[str, Any]) -> None:
        """Synchronously enqueue an event to all subscriber queues.
        
        Safe to invoke from synchronous services, threads, or background scheduler tasks.
        """
        payload = {
            "event": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        for q in list(self._subscribers):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning("Subscriber queue is full; dropping frame to avoid latency lag.")
            except Exception as e:
                logger.debug("Error delivering to subscriber queue: %s", e)


# Global singleton instance
live_broadcaster = LiveBroadcaster()
