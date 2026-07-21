"""Built-in pool cleaner schedule (replaces YAML helpers + automations)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .config_params import PSState
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
            "enabled": self.enabled,
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
        self._timed_powered_on = False
        self._manual_cycle = False
        self._run_started_at: datetime | None = None
        self._run_ends_at: datetime | None = None
        self._run_duration_minutes: int | None = None

    def add_listener(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    @callback
    def _notify(self) -> None:
        for listener in self._listeners:
            listener()

    def _clear_run_timing(self) -> None:
        self._manual_cycle = False
        self._run_started_at = None
        self._run_ends_at = None
        self._run_duration_minutes = None

    @property
    def timed_run_active(self) -> bool:
        """True while HA owns a STARTUP→sleep→SHUTDOWN timed run."""
        return bool(
            self._timed_powered_on
            and self._timed_task is not None
            and not self._timed_task.done()
        )

    @property
    def run_active(self) -> bool:
        """True while a timed run or manual Power cycle countdown is showing."""
        if self.timed_run_active:
            return True
        return bool(self._manual_cycle and self._run_ends_at is not None)

    @property
    def run_started_at(self) -> datetime | None:
        return self._run_started_at

    @property
    def run_ends_at(self) -> datetime | None:
        return self._run_ends_at

    @property
    def run_duration_minutes(self) -> int | None:
        return self._run_duration_minutes

    def schedule_state(self) -> str:
        """Sensor value: active | scheduled | off."""
        if self.run_active:
            return "active"
        if self.config.enabled:
            return "scheduled"
        return "off"

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

    def _robot_reachable_for_schedule(self) -> bool:
        """Skip STARTUP spam when the last poll clearly failed / no PS_State."""
        data = self._coordinator.data or {}
        if data.get("ps_poll_ok") is False and data.get("ps_state") is None:
            return False
        return True

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
            if not self._robot_reachable_for_schedule():
                _LOGGER.warning(
                    "Maytronics Dolphin schedule %s skipped — robot unreachable "
                    "(last PS_State poll failed; PS may be unplugged)",
                    slot_id,
                )
                continue
            _LOGGER.info(
                "Maytronics Dolphin schedule %s at %s (%s min)",
                slot_id,
                slot_time,
                duration,
            )
            await self.async_run_timed(duration)
            break  # one timed run at a time; next slot waits for next minute

    async def _cancel_timed_task(self) -> None:
        if self._timed_task is None or self._timed_task.done():
            self._timed_task = None
            return
        self._timed_task.cancel()
        with suppress(asyncio.CancelledError):
            await self._timed_task
        self._timed_task = None

    async def _shutdown_timed_power(self) -> None:
        if not self._timed_powered_on:
            self._clear_run_timing()
            return
        try:
            await self._session.async_send_gatt_packet(
                build_bt_command_19(BTCommandType.SHUTDOWN),
                COMMAND_CHAR_UUID,
            )
            await self._coordinator.async_refresh_until_power(False)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Maytronics Dolphin timed run shutdown failed: %s", err)
        finally:
            self._timed_powered_on = False
            self._clear_run_timing()
            self._notify()

    async def async_note_manual_power_on(self, duration_minutes: int) -> None:
        """Display-only countdown for Power switch (PS ends the cycle itself)."""
        if self.timed_run_active:
            return
        minutes = max(1, int(duration_minutes))
        started = dt_util.utcnow()
        self._manual_cycle = True
        self._run_started_at = started
        self._run_duration_minutes = minutes
        self._run_ends_at = started + timedelta(minutes=minutes)
        self._notify()

    async def async_clear_manual_power_timing(self) -> None:
        if not self._manual_cycle:
            return
        self._clear_run_timing()
        self._notify()

    async def async_abort_timed_run(
        self, reason: str = "", *, send_shutdown: bool = False
    ) -> None:
        """Cancel an in-progress timed run (manual stop / PS_State dropped)."""
        if self._manual_cycle and not self.timed_run_active:
            await self.async_clear_manual_power_timing()
            return
        if self._timed_task is None and not self._timed_powered_on:
            return
        _LOGGER.info(
            "Maytronics Dolphin timed run abort (%s)", reason or "unspecified"
        )
        was_on = self._timed_powered_on
        await self._cancel_timed_task()
        if send_shutdown and was_on:
            await self._shutdown_timed_power()
        else:
            self._timed_powered_on = False
            self._clear_run_timing()
            self._notify()

    async def async_watch_power_state(self) -> None:
        """Clear run timing when robot reports OFF while a run/countdown is active."""
        if not self._timed_powered_on and not self._manual_cycle:
            return
        data = self._coordinator.data or {}
        if not data.get("ps_poll_ok"):
            return
        ps: PSState | None = data.get("ps_state")
        if ps == PSState.OFF:
            if self._manual_cycle and not self.timed_run_active:
                await self.async_clear_manual_power_timing()
                return
            await self.async_abort_timed_run(
                "ps_state_off", send_shutdown=False
            )

    async def async_run_timed(self, duration_minutes: int, *, wait: bool = False) -> None:
        """Power on, wait, power off (one run at a time)."""
        minutes = _normalize_duration(duration_minutes, 120)
        if self._timed_task and not self._timed_task.done():
            await self._cancel_timed_task()
            await self._shutdown_timed_power()
        self._timed_task = asyncio.create_task(self._timed_run_impl(minutes))
        if wait:
            await self._timed_task

    async def _timed_run_impl(self, duration_minutes: int) -> None:
        self._timed_powered_on = False
        self._clear_run_timing()
        self._notify()
        try:
            await self._session.async_send_gatt_packet(
                build_bt_command_19(BTCommandType.STARTUP),
                COMMAND_CHAR_UUID,
            )
            confirmed = await self._coordinator.async_refresh_until_power(True)
            if not confirmed:
                _LOGGER.warning(
                    "Maytronics Dolphin schedule STARTUP sent but PS_State did not "
                    "confirm ON — aborting timed run (PS may be unplugged)"
                )
                self._timed_powered_on = False
                self._clear_run_timing()
                self._notify()
                return

            self._timed_powered_on = True
            started = dt_util.utcnow()
            self._run_started_at = started
            self._run_duration_minutes = duration_minutes
            self._run_ends_at = started + timedelta(minutes=duration_minutes)
            self._notify()
            await asyncio.sleep(duration_minutes * 60)
            await self._shutdown_timed_power()
        except asyncio.CancelledError:
            _LOGGER.debug("Maytronics Dolphin timed run cancelled")
            # Caller (abort / replace / shutdown) owns power cleanup.
            raise
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Maytronics Dolphin timed run failed: %s", err)
            await self._shutdown_timed_power()
        finally:
            self._timed_task = None
            self._notify()

    async def async_shutdown(self) -> None:
        await self._cancel_timed_task()
        await self._shutdown_timed_power()
