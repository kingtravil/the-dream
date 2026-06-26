"""Select execution backend by operating mode."""

from __future__ import annotations

from the_dream.config import DreamConfig, OperatingMode
from the_dream.execution.base import Executor
from the_dream.execution.live import LiveExecutor
from the_dream.execution.micro import MicroExecutor
from the_dream.execution.paper import PaperExecutor


def get_executor(cfg: DreamConfig) -> Executor:
    if cfg.mode == OperatingMode.PAPER:
        return PaperExecutor()
    if cfg.mode == OperatingMode.LIVE_MICRO:
        return MicroExecutor(cfg=cfg)
    return LiveExecutor()
