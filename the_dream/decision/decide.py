"""
⭐ PURE function — the heart, shared by live + backtest.

No I/O, no clock, no globals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from the_dream.config import DreamConfig
from the_dream.normalize.schema import HumanSignal
from the_dream.risk.exposure import RiskCheck


class DecisionType(str, Enum):
    BET = "BET"
    NO_BET = "NO_BET"


class BetStrength(str, Enum):
    STRONG = "STRONG"
    NORMAL = "NORMAL"
    REDUCED = "REDUCED"
    REVIEW = "REVIEW"


@dataclass(frozen=True)
class Decision:
    decision: DecisionType
    strength: Optional[BetStrength] = None
    stake: float = 0.0
    reason: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "decision": self.decision.value,
            "strength": self.strength.value if self.strength else None,
            "stake": round(self.stake, 2),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class DecisionContext:
    runner_id: str
    race_id: str
    p_model: float
    p_market: float
    price: float
    ev_net: float
    confidence: float
    cfg: DreamConfig
    risk: RiskCheck
    human: Optional[HumanSignal] = None
    proposed_stake: float = 0.0


def decide(ctx: DecisionContext) -> Decision:
    """Single pure decision function — live and backtest must call this."""
    reasons: List[str] = []

    if ctx.ev_net <= ctx.cfg.ev_threshold:
        return Decision(
            DecisionType.NO_BET,
            reason=["ev below threshold"],
        )

    if not ctx.risk.passes:
        return Decision(
            DecisionType.NO_BET,
            reason=[ctx.risk.reason or "risk check failed"],
        )

    if ctx.human and ctx.human.veto:
        return Decision(
            DecisionType.NO_BET,
            reason=["human veto"],
        )

    reasons.append("ev_net>threshold")
    reasons.append("liquidity_ok")

    stake = ctx.risk.adjusted_stake if ctx.risk.adjusted_stake > 0 else ctx.proposed_stake

    if ctx.human and ctx.human.agrees:
        reasons.append("human_agree")
        return Decision(
            DecisionType.BET,
            strength=BetStrength.STRONG,
            stake=stake,
            reason=reasons,
        )

    if ctx.human and ctx.human.disagrees:
        reasons.append("human_disagree")
        return Decision(
            DecisionType.BET,
            strength=BetStrength.REDUCED,
            stake=stake * 0.5,
            reason=reasons,
        )

    reasons.append("model_only")
    return Decision(
        DecisionType.BET,
        strength=BetStrength.NORMAL,
        stake=stake,
        reason=reasons,
    )


def format_output(ctx: DecisionContext, decision: Decision) -> dict:
    """System output format per spec §16."""
    return {
        "runner_id": ctx.runner_id,
        "model_prob": round(ctx.p_model, 4),
        "market_prob": round(ctx.p_market, 4),
        "price": round(ctx.price, 2),
        "ev_net": round(ctx.ev_net, 4),
        "confidence": round(ctx.confidence, 2),
        "stake": round(decision.stake, 2),
        "decision": decision.decision.value,
        "strength": decision.strength.value if decision.strength else None,
        "reason": decision.reason,
    }
