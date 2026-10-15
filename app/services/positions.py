from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.db.models.transaction import TransactionType


@dataclass(frozen=True, slots=True)
class CostFill:
    security_id: UUID
    ticker: str
    transaction_type: str
    quantity: Decimal
    price: Decimal


@dataclass(frozen=True, slots=True)
class AverageCost:
    security_id: UUID
    ticker: str
    quantity: Decimal
    avg_cost: Decimal | None


def average_cost_positions(fills: list[CostFill]) -> list[AverageCost]:
    """Average-cost ledger. A sell reduces cost by the current average."""
    quantity: dict[UUID, Decimal] = {}
    cost: dict[UUID, Decimal] = {}
    tickers: dict[UUID, str] = {}
    for fill in fills:
        tickers[fill.security_id] = fill.ticker
        held = quantity.get(fill.security_id, Decimal("0"))
        booked = cost.get(fill.security_id, Decimal("0"))
        if fill.transaction_type == TransactionType.SELL.value:
            if held > 0:
                booked -= (booked / held) * fill.quantity
            held -= fill.quantity
        else:
            booked += fill.quantity * fill.price
            held += fill.quantity
        if held == 0:
            booked = Decimal("0")
        quantity[fill.security_id] = held
        cost[fill.security_id] = booked

    rows: list[AverageCost] = []
    for security_id, held in quantity.items():
        if held == 0:
            continue
        booked = cost[security_id]
        avg = booked / held if held > 0 else None
        rows.append(
            AverageCost(
                security_id=security_id,
                ticker=tickers[security_id],
                quantity=held,
                avg_cost=avg,
            )
        )
    rows.sort(key=lambda row: row.ticker)
    return rows
