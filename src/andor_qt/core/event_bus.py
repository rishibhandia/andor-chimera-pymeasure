"""Event bus for decoupled component communication.

This module provides a publish-subscribe event system that allows
components to communicate without tight coupling. It supports:
- Exact event matching
- Wildcard subscriptions (e.g., "hardware.*")
- Qt signal integration for thread-safe communication
"""

from __future__ import annotations

import fnmatch
import threading
from collections import defaultdict
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QObject, Signal

if TYPE_CHECKING:
    pass


class EventBus(QObject):
    """Publish-subscribe event bus with wildcard support.

    The EventBus allows components to communicate through events without
    direct references to each other. Components can subscribe to specific
    events or use wildcards to receive groups of events.

    Example:
        >>> bus = get_event_bus()
        >>> bus.subscribe("hardware.initialized", on_hardware_ready)
        >>> bus.subscribe("hardware.*", on_any_hardware_event)
        >>> bus.publish("hardware.initialized", status="ready")
    """

    _instance: EventBus | None = None
    _lock = threading.Lock()

    # Qt signal emitted on every publish (event_name, data_dict)
    event_emitted = Signal(str, object)

    def __new__(cls) -> EventBus:
        """Create or return singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize the event bus."""
        # Prevent re-initialization
        if hasattr(self, "_initialized") and self._initialized:
            return

        super().__init__()
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._wildcard_subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._initialized = True

    @classmethod
    def instance(cls) -> EventBus:
        """Get the singleton instance.

        Returns:
            The EventBus singleton instance.
        """
        return cls()

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance.

        This is primarily useful for testing to ensure test isolation.
        """
        with cls._lock:
            if cls._instance is not None:
                cls._instance._subscribers.clear()
                cls._instance._wildcard_subscribers.clear()
            cls._instance = None

    def subscribe(self, event_name: str, handler: Callable) -> None:
        """Subscribe a handler to an event.

        Args:
            event_name: The event name to subscribe to. Can include
                a wildcard suffix (e.g., "hardware.*") to receive
                all events matching the pattern.
            handler: The function to call when the event is published.
                Will receive keyword arguments from the publish call.
        """
        if event_name.endswith(".*"):
            self._wildcard_subscribers[event_name].append(handler)
        else:
            self._subscribers[event_name].append(handler)

    def unsubscribe(self, event_name: str, handler: Callable) -> None:
        """Unsubscribe a handler from an event.

        Args:
            event_name: The event name to unsubscribe from.
            handler: The handler function to remove.
        """
        if event_name.endswith(".*"):
            subscribers = self._wildcard_subscribers.get(event_name, [])
        else:
            subscribers = self._subscribers.get(event_name, [])

        if handler in subscribers:
            subscribers.remove(handler)

    def publish(self, event_name: str, **data) -> None:
        """Publish an event to all subscribers.

        Args:
            event_name: The name of the event to publish.
            **data: Keyword arguments to pass to subscriber handlers.
        """
        # Emit Qt signal for thread-safe communication
        self.event_emitted.emit(event_name, data)

        # Notify exact subscribers
        for handler in self._subscribers.get(event_name, []):
            handler(**data)

        # Notify wildcard subscribers
        for pattern, handlers in self._wildcard_subscribers.items():
            if fnmatch.fnmatch(event_name, pattern):
                for handler in handlers:
                    # Include event_name in kwargs for wildcard handlers
                    handler(event_name=event_name, **data)

    def clear_event(self, event_name: str) -> None:
        """Remove all subscribers for a specific event.

        Args:
            event_name: The event name to clear subscribers from.
        """
        if event_name.endswith(".*"):
            self._wildcard_subscribers.pop(event_name, None)
        else:
            self._subscribers.pop(event_name, None)

    def clear_all(self) -> None:
        """Remove all subscribers for all events."""
        self._subscribers.clear()
        self._wildcard_subscribers.clear()


def get_event_bus() -> EventBus:
    """Get the global EventBus instance.

    Returns:
        The singleton EventBus instance.
    """
    return EventBus.instance()
