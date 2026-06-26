"""Mode flags, commission tables, risk limits — single source of truth."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict


class OperatingMode(str, Enum):
    PAPER = "PAPER"
    LIVE_MICRO = "LIVE_MICRO"
    LIVE = "LIVE"


# Commission on net winnings per market (Market Base Rate baseline).
COMMISSION_BY_REGION: Dict[str, float] = {
    "NZ": 0.08,
    "AU_NSW": 0.10,
    "AU_VIC": 0.10,
    "AU_QLD": 0.08,
    "AU_SA": 0.09,
    "AU_WA": 0.08,
    "AU_TAS": 0.07,
    "AU_NT": 0.07,
    "DEFAULT": 0.08,
}

# Modeled winner charges for backtest ROI (Premium/Expert + Turnover).
EFFECTIVE_CHARGE_PREMIUM: float = 0.02


@dataclass(frozen=True)
class RiskLimits:
    max_stake_pct_bankroll: float = 0.02
    max_race_exposure_pct: float = 0.04
    max_global_exposure_pct: float = 0.10
    kelly_fraction: float = 0.15
    max_depth_pct: float = 0.25
    drawdown_circuit_breaker_pct: float = 0.20


@dataclass(frozen=True)
class DreamConfig:
    mode: OperatingMode = OperatingMode.PAPER
    region: str = "NZ"
    ev_threshold: float = 0.01
    decision_lead_seconds: int = 120
    human_overlay_max_pct: float = 0.15
    live_micro_stake: float = 2.0
    bankroll: float = 10_000.0
    risk: RiskLimits = field(default_factory=RiskLimits)
    devig_method: str = "proportional"
    model_version: str = "ensemble-v0"
    code_version: str = "0.1.0"

    @property
    def commission(self) -> float:
        return COMMISSION_BY_REGION.get(self.region, COMMISSION_BY_REGION["DEFAULT"])

    @property
    def effective_commission(self) -> float:
        """Commission plus modeled winner charges for conservative ROI."""
        return self.commission + EFFECTIVE_CHARGE_PREMIUM


DEFAULT_CONFIG = DreamConfig()
