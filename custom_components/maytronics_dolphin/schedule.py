"""Built-in pool cleaner schedule (replaces YAML helpers + automations)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .connection import DolphinBleConnection
from .const import COMMAND_CHAR_UUID, DOMAIN
from .coordinator import DolphinCoordinator
from .protocol import BTCommandType, build_bt_command_19

_LOGGER = logging.getLogger(__name__)

STORE_VERSION = 1

ATTR_DAYS = "days"  # legacy; migrated to run1_days / run2_days
ATTR_RUN1_DAYS = "run1_days"
ATTR_RUN2_DAYS = "run2_days"
ATTR_RUN1_TIME = "run1_time"
ATTR_RUN1_DURATION_MINUTES = "run1_duration_minutes"
ATTR_RUN2_ENABLED = "run2_enabled"
ATTR_RUN2_TIME = "run2_time"
ATTR_RUN2_DURATION_MINUTES = "run2_duration_minutes"


@dataclass
class ScheduleConfig:
    """Persisted schedule for one Dolphin config entry."""

    enabled: bool = False
    run1_days: list[int] = field(default_factory=lambda: list(range(7)))
    run1_time: str = "09:00"
    run1_duration_minutes: int = 120
    run2_enabled: bool = False
    run2_days: list[int] = field(default_factory=lambda: list(range(7)))
    run2_time: str = "17:00"
    run2_duration_minutes: int = 60

    def as_attributes(self) -> dict[str, Any]:
        return {
            ATTR_RUN1_DAYS: ",".join(str(d) for d in sorted(set(self.run1_days))),
            ATTR_RUN2_DAYS: ",".join(str(d) for d in sorted(set(self.run2_days))),
            ATTR_RUN1_TIME: self.run1_time,
            ATTR_RUN1_DURATION_MINUTES: self.run1_duration_minutes,
            ATTR_RUN2_ENABLED: self.run2_enabled,
            ATTR_RUN2_TIME: self.run2_time,
            ATTR_RUN2_DURATION_MINUTES: self.run2_duration_minutes,
        }


def _normalize_time(value: str | None, default: str = "09:00") -> str:
    if not value or value in ("unknown", "unavailable"):
        return default
    raw = str(value).strip()
    if " " in raw:
        raw = raw.split(" ")[-1]
    parts = raw.split(":")
    if len(parts) < 2:
        return default
    try:
        h = max(0, min(23, int(parts[0])))
        m = max(0, min(59, int(parts[1])))
    except ValueError:
        return default
    return f"{h:02d}:{m:02d}"


def _normalize_duration(minutes: int | str | None, default: int = 120) -> int:
    if minutes in (60, "60", "1 hour", 1):
        return 60
    if minutes in (120, "120", "2 hours", 2):
        return 120
    try:
        n = int(minutes)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return 60 if n <= 90 else 120


def _normalize_days(raw: Any) -> list[int]:
    if raw is None:
        return list(range(7))
    if isinstance(raw, (list, tuple, set)):
        items = raw
    else:
        items = str(raw).split(",")
    out: list[int] = []
    for item in items:
        try:
            d = int(str(item).strip())
        except ValueError:
            continue
        if 0 <= d <= 6:
            out.append(d)
    return sorted(set(out)) if out else list(range(7))


class DolphinScheduleManager:
    """Minute scheduler + timed run for one config entry."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        session: DolphinBleConnection,
        coordinator: DolphinCoordinator,
    ) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self._session = session
        self._coordinator = coordinator
        self._store = Store[dict[str, Any]](
            hass, STORE_VERSION, f"{DOMAIN}.schedule.{entry_id}"
        )
        self.config = ScheduleConfig()
        self._listeners: list[Callable[[], None]] = []
        self._last_fire: set[str] = set()
        self._timed_task: asyncio.Task[None] | None = None

    def add_listener(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    @callback
    def _notify(self) -> None:
        for listener in self._listeners:
            listener()

    async def async_load(self) -> None:
        stored = await self._store.async_load()
        if not stored:
            return
        legacy_days = stored.get("days")
        self.config = ScheduleConfig(
            enabled=bool(stored.get("enabled", False)),
            run1_days=_normalize_days(stored.get("run1_days", legacy_days)),
            run1_time=_normalize_time(stored.get("run1_time"), "09:00"),
            run1_duration_minutes=_normalize_duration(
                stored.get("run1_duration_minutes"), 120
            ),
            run2_enabled=bool(stored.get("run2_enabled", False)),
            run2_days=_normalize_days(stored.get("run2_days", legacy_days)),
            run2_time=_normalize_time(stored.get("run2_time"), "17:00"),
            run2_duration_minutes=_normalize_duration(
                stored.get("run2_duration_minutes"), 60
            ),
        )

    async def async_save(self) -> None:
        await self._store.async_save(asdict(self.config))
        self._notify()

    async def async_update(self, **kwargs: Any) -> None:
        cfg = self.config
        if "enabled" in kwargs and kwargs["enabled"] is not None:
            cfg.enabled = bool(kwargs["enabled"])
        if "days" in kwargs and kwargs["days"] is not None:
            normalized = _normalize_days(kwargs["days"])
            cfg.run1_days = normalized
            cfg.run2_days = normalized
        if "run1_days" in kwargs and kwargs["run1_days"] is not None:
            cfg.run1_days = _normalize_days(kwargs["run1_days"])
        if "run2_days" in kwargs and kwargs["run2_days"] is not None:
            cfg.run2_days = _normalize_days(kwargs["run2_days"])
        if "run1_time" in kwargs and kwargs["run1_time"] is not None:
            cfg.run1_time = _normalize_time(kwargs["run1_time"], cfg.run1_time)
        if "run1_duration_minutes" in kwargs and kwargs["run1_duration_minutes"] is not None:
            cfg.run1_duration_minutes = _normalize_duration(
                kwargs["run1_duration_minutes"], cfg.run1_duration_minutes
            )
        if "run2_enabled" in kwargs and kwargs["run2_enabled"] is not None:
            cfg.run2_enabled = bool(kwargs["run2_enabled"])
        if "run2_time" in kwargs and kwargs["run2_time"] is not None:
            cfg.run2_time = _normalize_time(kwargs["run2_time"], cfg.run2_time)
        if "run2_duration_minutes" in kwargs and kwargs["run2_duration_minutes"] is not None:
            cfg.run2_duration_minutes = _normalize_duration(
                kwargs["run2_duration_minutes"], cfg.run2_duration_minutes
            )
        await self.async_save()

    def _time_matches(self, slot_time: str, now: datetime) -> bool:
        parts = slot_time.split(":")
        try:
            return now.hour == int(parts[0]) and now.minute == int(parts[1])
        except (IndexError, ValueError):
            return False

    def _day_matches(self, days: list[int], now: datetime) -> bool:
        return now.weekday() in days

    async def async_check_and_run(self, now: datetime) -> None:
        """Fire scheduled runs once per matching minute."""
        cfg = self.config
        if not cfg.enabled:
            return

        slots: list[tuple[str, str, int, list[int]]] = [
            ("run1", cfg.run1_time, cfg.run1_duration_minutes, cfg.run1_days),
        ]
        if cfg.run2_enabled:
            slots.append(
                ("run2", cfg.run2_time, cfg.run2_duration_minutes, cfg.run2_days)
            )

        for slot_id, slot_time, duration, days in slots:
            if not self._day_matches(days, now):
                continue
            if not self._time_matches(slot_time, now):
                continue
            key = f"{now.date().isoformat()}-{now.hour:02d}{now.minute:02d}-{slot_id}"
            if key in self._last_fire:
                continue
            self._last_fire.add(key)
            if len(self._last_fire) > 48:
                self._last_fire = set(list(self._last_fire)[-24:])
            _LOGGER.info(
                "Maytronics Dolphin schedule %s at %s (%s min)",
                slot_id,
                slot_time,
                duration,
            )
            await self.async_run_timed(duration)

    async def async_run_timed(self, duration_minutes: int) -> None:
        """Power on, wait, power off (restarts if already running)."""
        minutes = _normalize_duration(duration_minutes, 120)
        if self._timed_task and not self._timed_task.done():
            self._timed_task.cancel()
            with asyncio.suppress(asyncio.CancelledError):
                await self._timed_task
        self._timed_task = asyncio.create_task(self._timed_run_impl(minutes))

    async def _timed_run_impl(self, duration_minutes: int) -> None:
        try:
            await self._session.async_send_gatt_packet(
                build_bt_command_19(BTCommandType.STARTUP),
                COMMAND_CHAR_UUID,
            )
            await self._coordinator.async_refresh_until_power(True)
            await asyncio.sleep(duration_minutes * 60)
            await self._session.async_send_gatt_packet(
                build_bt_command_19(BTCommandType.SHUTDOWN),
                COMMAND_CHAR_UUID,
            )
            await self._coordinator.async_refresh_until_power(False)
        except asyncio.CancelledError:
            _LOGGER.debug("Maytronics Dolphin timed run cancelled")
            raise
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Maytronics Dolphin timed run failed: %s", err)

    async def async_shutdown(self) -> None:
        if self._timed_task and not self._timed_task.done():
            self._timed_task.cancel()
            with asyncio.suppress(asyncio.CancelledError):
                await self._timed_task
