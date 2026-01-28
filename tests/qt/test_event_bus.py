"""Tests for EventBus.

These tests verify the EventBus singleton provides correct pub/sub
functionality for decoupled component communication.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestEventBusSingleton:
    """Tests for EventBus singleton pattern."""

    def test_singleton_instance(self, qt_app, reset_event_bus):
        """get_event_bus() returns the same instance."""
        from andor_qt.core.event_bus import get_event_bus

        bus1 = get_event_bus()
        bus2 = get_event_bus()

        assert bus1 is bus2

    def test_reset_clears_singleton(self, qt_app, reset_event_bus):
        """reset_event_bus() allows creating a new singleton."""
        from andor_qt.core.event_bus import EventBus, get_event_bus

        bus1 = get_event_bus()
        id1 = id(bus1)

        EventBus.reset_instance()

        bus2 = get_event_bus()
        id2 = id(bus2)

        assert id1 != id2


class TestEventBusSubscribePublish:
    """Tests for subscribe and publish functionality."""

    def test_subscribe_and_publish(self, qt_app, reset_event_bus, handler_factory):
        """Subscriber receives published events."""
        from andor_qt.core.event_bus import get_event_bus

        bus = get_event_bus()
        handler = handler_factory("test_handler")

        bus.subscribe("test.event", handler)
        bus.publish("test.event", value=42)

        handler.assert_called_once()
        call_args = handler.call_args
        assert call_args.kwargs["value"] == 42

    def test_multiple_subscribers_same_event(
        self, qt_app, reset_event_bus, handler_factory
    ):
        """Multiple subscribers all receive the same event."""
        from andor_qt.core.event_bus import get_event_bus

        bus = get_event_bus()
        handler1 = handler_factory("handler1")
        handler2 = handler_factory("handler2")
        handler3 = handler_factory("handler3")

        bus.subscribe("shared.event", handler1)
        bus.subscribe("shared.event", handler2)
        bus.subscribe("shared.event", handler3)

        bus.publish("shared.event", data="test")

        handler1.assert_called_once()
        handler2.assert_called_once()
        handler3.assert_called_once()

    def test_publish_with_no_subscribers(self, qt_app, reset_event_bus):
        """Publishing to event with no subscribers doesn't raise."""
        from andor_qt.core.event_bus import get_event_bus

        bus = get_event_bus()

        # Should not raise
        bus.publish("nonexistent.event", data="test")

    def test_subscribers_only_receive_subscribed_events(
        self, qt_app, reset_event_bus, handler_factory
    ):
        """Subscribers only receive events they subscribed to."""
        from andor_qt.core.event_bus import get_event_bus

        bus = get_event_bus()
        handler = handler_factory("test_handler")

        bus.subscribe("event.a", handler)
        bus.publish("event.b", data="test")

        handler.assert_not_called()

    def test_publish_passes_all_kwargs(self, qt_app, reset_event_bus, handler_factory):
        """Publish passes all keyword arguments to subscribers."""
        from andor_qt.core.event_bus import get_event_bus

        bus = get_event_bus()
        handler = handler_factory("test_handler")

        bus.subscribe("test.event", handler)
        bus.publish(
            "test.event", value=42, name="test", data={"key": "value"}, flag=True
        )

        handler.assert_called_once()
        call_args = handler.call_args
        assert call_args.kwargs["value"] == 42
        assert call_args.kwargs["name"] == "test"
        assert call_args.kwargs["data"] == {"key": "value"}
        assert call_args.kwargs["flag"] is True


class TestEventBusUnsubscribe:
    """Tests for unsubscribe functionality."""

    def test_unsubscribe(self, qt_app, reset_event_bus, handler_factory):
        """Unsubscribed handler no longer receives events."""
        from andor_qt.core.event_bus import get_event_bus

        bus = get_event_bus()
        handler = handler_factory("test_handler")

        bus.subscribe("test.event", handler)
        bus.unsubscribe("test.event", handler)
        bus.publish("test.event", value=42)

        handler.assert_not_called()

    def test_unsubscribe_nonexistent_handler(
        self, qt_app, reset_event_bus, handler_factory
    ):
        """Unsubscribing a non-subscribed handler doesn't raise."""
        from andor_qt.core.event_bus import get_event_bus

        bus = get_event_bus()
        handler = handler_factory("test_handler")

        # Should not raise
        bus.unsubscribe("test.event", handler)

    def test_unsubscribe_from_nonexistent_event(
        self, qt_app, reset_event_bus, handler_factory
    ):
        """Unsubscribing from a non-existent event doesn't raise."""
        from andor_qt.core.event_bus import get_event_bus

        bus = get_event_bus()
        handler = handler_factory("test_handler")

        # Should not raise
        bus.unsubscribe("nonexistent.event", handler)

    def test_unsubscribe_one_keeps_others(
        self, qt_app, reset_event_bus, handler_factory
    ):
        """Unsubscribing one handler doesn't affect others."""
        from andor_qt.core.event_bus import get_event_bus

        bus = get_event_bus()
        handler1 = handler_factory("handler1")
        handler2 = handler_factory("handler2")

        bus.subscribe("test.event", handler1)
        bus.subscribe("test.event", handler2)
        bus.unsubscribe("test.event", handler1)

        bus.publish("test.event", value=42)

        handler1.assert_not_called()
        handler2.assert_called_once()


class TestEventBusWildcard:
    """Tests for wildcard subscription."""

    def test_wildcard_subscription(self, qt_app, reset_event_bus, handler_factory):
        """Wildcard subscriptions receive matching events."""
        from andor_qt.core.event_bus import get_event_bus

        bus = get_event_bus()
        handler = handler_factory("test_handler")

        bus.subscribe("hardware.*", handler)

        bus.publish("hardware.initialized", status="ready")
        bus.publish("hardware.shutdown", status="done")

        assert handler.call_count == 2

    def test_wildcard_does_not_match_different_prefix(
        self, qt_app, reset_event_bus, handler_factory
    ):
        """Wildcard only matches events with same prefix."""
        from andor_qt.core.event_bus import get_event_bus

        bus = get_event_bus()
        handler = handler_factory("test_handler")

        bus.subscribe("hardware.*", handler)
        bus.publish("ui.updated", data="test")

        handler.assert_not_called()

    def test_wildcard_receives_event_name(
        self, qt_app, reset_event_bus, handler_factory
    ):
        """Wildcard handlers receive the event_name in kwargs."""
        from andor_qt.core.event_bus import get_event_bus

        bus = get_event_bus()
        handler = handler_factory("test_handler")

        bus.subscribe("hardware.*", handler)
        bus.publish("hardware.temperature_changed", temp=-60)

        handler.assert_called_once()
        call_args = handler.call_args
        assert call_args.kwargs["event_name"] == "hardware.temperature_changed"
        assert call_args.kwargs["temp"] == -60

    def test_exact_and_wildcard_both_receive(
        self, qt_app, reset_event_bus, handler_factory
    ):
        """Both exact and wildcard subscribers receive matching events."""
        from andor_qt.core.event_bus import get_event_bus

        bus = get_event_bus()
        exact_handler = handler_factory("exact_handler")
        wildcard_handler = handler_factory("wildcard_handler")

        bus.subscribe("hardware.initialized", exact_handler)
        bus.subscribe("hardware.*", wildcard_handler)

        bus.publish("hardware.initialized", status="ready")

        exact_handler.assert_called_once()
        wildcard_handler.assert_called_once()


class TestEventBusSignal:
    """Tests for the Qt signal integration."""

    def test_event_emitted_signal(self, qt_app, reset_event_bus, handler_factory):
        """event_emitted signal is emitted on publish."""
        from andor_qt.core.event_bus import get_event_bus

        bus = get_event_bus()
        signal_handler = handler_factory("signal_handler")

        bus.event_emitted.connect(signal_handler)
        bus.publish("test.event", value=42)

        signal_handler.assert_called_once()
        args = signal_handler.call_args[0]
        assert args[0] == "test.event"
        assert args[1]["value"] == 42


class TestEventBusClear:
    """Tests for clearing subscriptions."""

    def test_clear_event(self, qt_app, reset_event_bus, handler_factory):
        """clear_event removes all subscribers for an event."""
        from andor_qt.core.event_bus import get_event_bus

        bus = get_event_bus()
        handler1 = handler_factory("handler1")
        handler2 = handler_factory("handler2")

        bus.subscribe("test.event", handler1)
        bus.subscribe("test.event", handler2)
        bus.clear_event("test.event")

        bus.publish("test.event", value=42)

        handler1.assert_not_called()
        handler2.assert_not_called()

    def test_clear_all(self, qt_app, reset_event_bus, handler_factory):
        """clear_all removes all subscribers for all events."""
        from andor_qt.core.event_bus import get_event_bus

        bus = get_event_bus()
        handler1 = handler_factory("handler1")
        handler2 = handler_factory("handler2")

        bus.subscribe("event.a", handler1)
        bus.subscribe("event.b", handler2)
        bus.clear_all()

        bus.publish("event.a", value=1)
        bus.publish("event.b", value=2)

        handler1.assert_not_called()
        handler2.assert_not_called()
