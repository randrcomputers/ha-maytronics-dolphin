"""Stabilize ``working_status`` so brief BLE read gaps do not flap to ``unknown``."""

from __future__ import annotations

import time
from dataclasses import dataclass

from .config_params import PSState
from .const import (
    WORKING_STATUS_AT_WORK_HOLD_SEC,
    WORKING_STATUS_FINISHED_HOLD_SEC,
    WORKING_STATUS_UNKNOWN_AFTER_MISSES,
)
from .status_params import WorkingStatus


@dataclass
class WorkingStatusTracker:
    """Hold last confirmed working status through short poll/read failures."""

    stable: WorkingStatus | None = None
    last_confirmed_monotonic: float = 0.0
    miss_streak: int = 0

    def _hold_limit_sec(self, status: WorkingStatus) -> float:
        if status == WorkingStatus.FINISHED:
            return float(WORKING_STATUS_FINISHED_HOLD_SEC)
        return float(WORKING_STATUS_AT_WORK_HOLD_SEC)

    def update(
        self,
        raw: WorkingStatus | None,
        ps: PSState | None,
        *,
        now: float | None = None,
    ) -> WorkingStatus | None:
        """Return stable working status for entities/automations."""
        ts = time.monotonic() if now is None else now

        if ps is None:
            if self.stable is not None:
                return self.stable
            return None

        if ps == PSState.OFF:
            self.stable = None
            self.last_confirmed_monotonic = 0.0
            self.miss_streak = 0
            return None

        if ps == PSState.HOLD:
            self.stable = WorkingStatus.FINISHED
            self.last_confirmed_monotonic = ts
            self.miss_streak = 0
            return WorkingStatus.FINISHED

        if raw is not None and raw != WorkingStatus.UNKNOWN:
            self.stable = raw
            self.last_confirmed_monotonic = ts
            self.miss_streak = 0
            return raw

        self.miss_streak += 1

        if self.miss_streak >= WORKING_STATUS_UNKNOWN_AFTER_MISSES:
            self.stable = None
            return None

        if self.stable is not None:
            age = ts - self.last_confirmed_monotonic
            if age > self._hold_limit_sec(self.stable):
                self.stable = None
                return None
            return self.stable

        return None

    @property
    def is_held(self) -> bool:
        return self.miss_streak > 0 and self.stable is not None
