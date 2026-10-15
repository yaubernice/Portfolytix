from __future__ import annotations

from decimal import Decimal
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.db.models import Fundamental, ResearchFlag, Security
from app.schemas.position import PositionOut
from app.schemas.research import (
    AttentionArea,
    AttentionResponse,
    AttentionStock,
    FlagCreate,
    FlagOut,
    Recommendation,
    RecommendationResponse,
)
from app.services.position_service import PositionService

_DISCLAIMER = (
    "Suggestions compare this portfolio with other stored securities "
    "that have a fundamental snapshot. They are not investment advice "
    "and do not predict prices."
)
_LIMIT = 5


class ResearchService:
    """Portfolio gaps, weak day moves, and the user's own flags."""

    def __init__(
        self,
        session: Session,
        user_id: UUID,
        positions: PositionService,
    ) -> None:
        self.session = session
        self.user_id = user_id
        self.positions = positions

    def recommendations(self, portfolio_id: UUID) -> RecommendationResponse:
        rows = self.positions.list_positions(portfolio_id).positions
        held = {row.security_id for row in rows if row.quantity > 0}
        sector_by_id = self._sectors_for(held)
        weights = _sector_weights(rows, sector_by_id)
        held_sectors = set(sector_by_id.values())
        has_holdings = bool(held)
        candidates: list[tuple[tuple, Recommendation]] = []
        statement = (
            select(Security, Fundamental)
            .join(Fundamental, Fundamental.security_id == Security.id)
            .where(
                Security.is_active.is_(True),
                ~Security.ticker.like("BENCH%"),
            )
            .order_by(Security.ticker)
        )
        for security, fundamental in self.session.execute(statement):
            if security.id in held:
                continue
            weight = weights.get(security.sector, Decimal(0))
            roe = fundamental.roe if fundamental is not None else None
            pe_ratio = fundamental.pe_ratio if fundamental is not None else None
            item = Recommendation(
                security_id=security.id,
                ticker=security.ticker,
                name=security.name,
                sector=security.sector,
                roe=roe,
                pe_ratio=pe_ratio,
                reason=_reason(
                    security.sector,
                    weight,
                    roe,
                    pe_ratio,
                    has_holdings,
                    security.sector in held_sectors,
                ),
            )
            roe_rank = roe if roe is not None else Decimal(0)
            covered = 0 if security.sector not in held_sectors else 1
            candidates.append(((covered, -roe_rank, security.ticker), item))
        candidates.sort(key=lambda pair: pair[0])
        return RecommendationResponse(
            portfolio_id=portfolio_id,
            disclaimer=_DISCLAIMER,
            items=[item for _, item in candidates[:_LIMIT]],
        )

    def attention(self, portfolio_id: UUID) -> AttentionResponse:
        rows = self.positions.list_positions(portfolio_id).positions
        sectors = self._sectors_for(
            {row.security_id for row in rows if row.quantity > 0}
        )
        names = self._names_for(set(sectors))
        stocks: list[AttentionStock] = []
        area_pl: dict[str, Decimal] = {}
        area_weight: dict[str, Decimal] = {}
        for row in rows:
            if row.quantity <= 0:
                continue
            sector = sectors.get(row.security_id, "")
            if row.weight is not None:
                area_weight[sector] = area_weight.get(sector, Decimal(0)) + row.weight
            if row.day_pl is None:
                continue
            area_pl[sector] = area_pl.get(sector, Decimal(0)) + row.day_pl
            if row.day_pl < 0:
                stocks.append(
                    AttentionStock(
                        security_id=row.security_id,
                        ticker=row.ticker,
                        name=names.get(row.security_id, row.ticker),
                        sector=sector,
                        day_pl=row.day_pl,
                        weight=row.weight,
                    )
                )
        stocks.sort(key=lambda item: (item.day_pl, item.ticker))
        areas = [
            AttentionArea(
                sector=sector,
                day_pl=total,
                weight=area_weight.get(sector),
            )
            for sector, total in area_pl.items()
            if sector and total < 0
        ]
        areas.sort(key=lambda item: (item.day_pl, item.sector))
        return AttentionResponse(
            portfolio_id=portfolio_id,
            stocks=stocks,
            areas=areas,
        )

    def list_flags(self) -> list[FlagOut]:
        statement = (
            select(ResearchFlag, Security)
            .outerjoin(Security, Security.id == ResearchFlag.security_id)
            .where(ResearchFlag.user_id == self.user_id)
            .order_by(ResearchFlag.created_at.desc())
        )
        return [
            _flag_out(flag, security)
            for flag, security in self.session.execute(statement)
        ]

    def create_flag(self, payload: FlagCreate) -> FlagOut:
        if payload.target_type == "security":
            assert payload.security_id is not None
            security = self.session.get(Security, payload.security_id)
            if security is None or not security.is_active:
                raise NotFoundError(f"Security {payload.security_id} not found")
            existing = self.session.scalar(
                select(ResearchFlag).where(
                    ResearchFlag.user_id == self.user_id,
                    ResearchFlag.security_id == security.id,
                )
            )
            if existing is not None:
                raise ConflictError(f"{security.ticker} is already flagged")
            flag = ResearchFlag(
                user_id=self.user_id,
                target_type="security",
                security_id=security.id,
                note=payload.note,
            )
            self.session.add(flag)
            self.session.flush()
            return _flag_out(flag, security)
        assert payload.sector is not None
        sector = self._canonical_sector(payload.sector)
        existing = self.session.scalar(
            select(ResearchFlag).where(
                ResearchFlag.user_id == self.user_id,
                func.lower(ResearchFlag.sector) == sector.lower(),
            )
        )
        if existing is not None:
            raise ConflictError(f"{sector} is already flagged")
        flag = ResearchFlag(
            user_id=self.user_id,
            target_type="sector",
            sector=sector,
            note=payload.note,
        )
        self.session.add(flag)
        self.session.flush()
        return _flag_out(flag, None)

    def delete_flag(self, flag_id: UUID) -> None:
        flag = self.session.scalar(
            select(ResearchFlag).where(
                ResearchFlag.id == flag_id,
                ResearchFlag.user_id == self.user_id,
            )
        )
        if flag is None:
            raise NotFoundError(f"Flag {flag_id} not found")
        self.session.delete(flag)

    def _sectors_for(self, security_ids: set[UUID]) -> dict[UUID, str]:
        if not security_ids:
            return {}
        rows = self.session.scalars(
            select(Security).where(Security.id.in_(security_ids))
        )
        return {row.id: row.sector for row in rows}

    def _names_for(self, security_ids: set[UUID]) -> dict[UUID, str]:
        if not security_ids:
            return {}
        rows = self.session.scalars(
            select(Security).where(Security.id.in_(security_ids))
        )
        return {row.id: row.name for row in rows}

    def _canonical_sector(self, sector: str) -> str:
        known = self.session.scalar(
            select(Security.sector).where(func.lower(Security.sector) == sector.lower())
        )
        return known or sector


def _sector_weights(
    rows: list[PositionOut],
    sectors: dict[UUID, str],
) -> dict[str, Decimal]:
    weights: dict[str, Decimal] = {}
    for row in rows:
        if row.quantity <= 0 or row.weight is None:
            continue
        sector = sectors.get(row.security_id, "")
        weights[sector] = weights.get(sector, Decimal(0)) + row.weight
    return weights


def _reason(
    sector: str,
    weight: Decimal,
    roe: Decimal | None,
    pe_ratio: Decimal | None,
    has_holdings: bool,
    sector_is_held: bool,
) -> str:
    if not has_holdings:
        opening = "This portfolio has no open positions."
    elif not sector_is_held or weight == 0:
        opening = f"No open position is in {sector}."
    else:
        opening = f"{sector} is {_percent(weight)} of current weight."
    facts = [opening]
    if roe is not None:
        facts.append(f"Stored ROE is {_percent(roe)}.")
    if pe_ratio is not None:
        facts.append(f"Stored P/E is {_number(pe_ratio)}.")
    if roe is None and pe_ratio is None:
        facts.append("No fundamental snapshot is stored for this security.")
    return " ".join(facts)


def _percent(value: Decimal) -> str:
    points = (value * Decimal(100)).quantize(Decimal("0.1"))
    return f"{points}%"


def _number(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def _flag_out(flag: ResearchFlag, security: Security | None) -> FlagOut:
    return FlagOut(
        id=flag.id,
        target_type=cast(Literal["security", "sector"], flag.target_type),
        security_id=flag.security_id,
        ticker=security.ticker if security is not None else None,
        name=security.name if security is not None else None,
        sector=security.sector if security is not None else flag.sector,
        note=flag.note,
        created_at=flag.created_at,
    )
