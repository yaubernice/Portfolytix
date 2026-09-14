from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.db.models.transaction import TransactionType
from app.schemas.holding import HoldingOut


@dataclass(frozen=True, slots=True)
class PositionLeg:
    security_id: UUID
    ticker: str
    transaction_type: str
    quantity: Decimal


def aggregate_positions(legs: list[PositionLeg]) -> list[HoldingOut]:
    """Net quantity per security: BUY adds, SELL subtracts.

    Zero positions are omitted (sold out). A negative net quantity is kept
    so a corrupted ledger is visible instead of silently dropped.
    """
    quantities: dict[UUID, Decimal] = {}
    tickers: dict[UUID, str] = {}
    for leg in legs:
        tickers[leg.security_id] = leg.ticker
        delta = leg.quantity
        if leg.transaction_type == TransactionType.SELL:
            delta = -leg.quantity
        current = quantities.get(leg.security_id, Decimal("0"))
        quantities[leg.security_id] = current + delta

    holdings = [
        HoldingOut(
            security_id=security_id,
            ticker=tickers[security_id],
            quantity=qty,
        )
        for security_id, qty in quantities.items()
        if qty != 0
    ]
    holdings.sort(key=lambda row: row.ticker)
    return holdings


def quantity_held(holdings: list[HoldingOut], security_id: UUID) -> Decimal:
    for holding in holdings:
        if holding.security_id == security_id:
            return holding.quantity
    return Decimal("0")
