from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError
from app.db.models import Fundamental, ResearchFlag, Security
from app.market_data.yahoo_fundamentals import fetch_latest_quotes, fetch_snapshots
from app.quotes.provider_marks import provider_quotes
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

logger = logging.getLogger(__name__)

_DISCLAIMER = (
    "Suggestions compare this portfolio with stored figures for companies "
    "of different sizes. They are not investment advice and do not predict prices."
)
_LIVE_DISCLAIMER = (
    "Each price is Yahoo's latest published quote. Company size and "
    "reported profit stay the latest stored snapshot. That quote can lag "
    "the exchange and is not a trade-by-trade feed. These ideas are not "
    "investment advice and do not predict prices."
)
_LIMIT = 6
_FILL_LIMIT = 8
_SMALL = Decimal("2000000000")
_MID = Decimal("10000000000")


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
        self._fill_missing_snapshots(held)
        sector_by_id = self._sectors_for(held)
        weights = _sector_weights(rows, sector_by_id)
        held_sectors = set(sector_by_id.values())
        has_holdings = bool(held)
        bands: dict[str, list] = {"small": [], "mid": [], "large": []}
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
            roe = fundamental.roe
            pe_ratio = fundamental.pe_ratio
            market_cap = fundamental.market_cap
            points = _points(
                security.sector,
                weight,
                roe,
                pe_ratio,
                market_cap,
                has_holdings,
                security.sector in held_sectors,
            )
            item = Recommendation(
                security_id=security.id,
                ticker=security.ticker,
                name=security.name,
                sector=security.sector,
                roe=roe,
                pe_ratio=pe_ratio,
                market_cap=market_cap,
                reason=" ".join(points),
                points=points,
            )
            missing = 0 if security.sector not in held_sectors else 1
            bands[_band(market_cap)].append(
                (
                    (missing, security.ticker),
                    item,
                    weight,
                    security.sector in held_sectors,
                )
            )
        for band in bands.values():
            band.sort(key=lambda pair: pair[0])
        picked: list = []
        while len(picked) < _LIMIT and any(bands.values()):
            for name in ("small", "mid", "large"):
                if bands[name] and len(picked) < _LIMIT:
                    picked.append(bands[name].pop(0))
        items = [row[1] for row in picked]
        disclaimer = _DISCLAIMER
        if settings.ideas_live_quotes and items:
            items, used_live = _apply_latest_quotes(picked, has_holdings)
            if used_live:
                disclaimer = _LIVE_DISCLAIMER
        return RecommendationResponse(
            portfolio_id=portfolio_id,
            disclaimer=disclaimer,
            items=items,
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

    def _fill_missing_snapshots(self, held: set[UUID]) -> None:
        """Store a few Yahoo snapshots so suggestions are not only the giants."""
        if self._has_size_mix():
            return
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        start = datetime.now(UTC).day % len(letters)
        order = letters[start:] + letters[:start]
        tickers: list[str] = []
        for letter in order:
            if len(tickers) >= _FILL_LIMIT:
                break
            filters = [
                Security.is_active.is_(True),
                Security.ticker.like(f"{letter}%"),
                func.length(Security.ticker).between(2, 4),
                ~Security.ticker.like("BENCH%"),
                ~Security.id.in_(select(Fundamental.security_id)),
            ]
            if held:
                filters.append(~Security.id.in_(held))
            security = self.session.scalar(
                select(Security)
                .where(*filters)
                .order_by(Security.ticker)
                .offset(datetime.now(UTC).day % 8)
                .limit(1)
            )
            if security is not None:
                tickers.append(security.ticker)
        if not tickers:
            return
        try:
            snapshots = fetch_snapshots(tickers)
        except Exception:
            logger.warning("suggestion_snapshot_failed")
            return
        for ticker, snapshot in snapshots.items():
            security = self.session.scalar(
                select(Security).where(Security.ticker == ticker)
            )
            if security is None:
                continue
            self.session.add(
                Fundamental(
                    security_id=security.id,
                    as_of=datetime.now(UTC).date(),
                    roe=snapshot["roe"],
                    pe_ratio=snapshot["pe_ratio"],
                    revenue_growth=snapshot["revenue_growth"],
                    market_cap=snapshot["market_cap"],
                    provider="yahoo",
                )
            )
            if not security.sector and snapshot["sector"]:
                security.sector = snapshot["sector"]
        self.session.flush()

    def _has_size_mix(self) -> bool:
        caps = self.session.scalars(
            select(Fundamental.market_cap)
            .join(Security, Security.id == Fundamental.security_id)
            .where(Security.is_active.is_(True), ~Security.ticker.like("BENCH%"))
        )
        bands = {_band(cap) for cap in caps}
        return "small" in bands and "mid" in bands

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


def _latest_quote_rows(tickers: list[str]) -> dict[str, dict]:
    """Chart fields the suggestion copy expects. Yahoo marks reuse the quote cache."""
    if settings.provider_marks:
        return {
            ticker: {
                "price": quote.price,
                "market_cap": None,
                "pe_ratio": None,
                "quoted_at": quote.provider_timestamp,
            }
            for ticker, quote in provider_quotes(tickers).items()
        }
    return fetch_latest_quotes(tickers)


def _apply_latest_quotes(
    picked: list,
    has_holdings: bool,
) -> tuple[list[Recommendation], bool]:
    try:
        quotes = _latest_quote_rows([row[1].ticker for row in picked])
    except Exception:
        logger.warning("suggestion_quote_failed")
        return [row[1] for row in picked], False
    items: list[Recommendation] = []
    used = False
    for _key, item, weight, sector_is_held in picked:
        quote = quotes.get(item.ticker)
        if not quote:
            items.append(item)
            continue
        used = True
        market_cap = quote["market_cap"] or item.market_cap
        pe_ratio = (
            quote["pe_ratio"] if quote["pe_ratio"] is not None else item.pe_ratio
        )
        points = _points(
            item.sector,
            weight,
            item.roe,
            pe_ratio,
            market_cap,
            has_holdings,
            sector_is_held,
        )
        points.insert(1, f"Yahoo's latest price is {_money(quote['price'])}.")
        items.append(
            item.model_copy(
                update={
                    "market_cap": market_cap,
                    "pe_ratio": pe_ratio,
                    "price": quote["price"],
                    "quoted_at": quote["quoted_at"],
                    "points": points,
                    "reason": " ".join(points),
                }
            )
        )
    return items, used


def _points(
    sector: str,
    weight: Decimal,
    roe: Decimal | None,
    pe_ratio: Decimal | None,
    market_cap: Decimal | None,
    has_holdings: bool,
    sector_is_held: bool,
) -> list[str]:
    label = sector or "this sector"
    if not has_holdings:
        opening = "This portfolio has no open positions yet."
    elif not sector_is_held or weight == 0:
        opening = f"No open position is in {label}."
    else:
        opening = f"{label} is already {_percent(weight)} of this portfolio."
    points = [opening]
    if market_cap is not None:
        points.append(
            f"It is a {_size_word(market_cap)} company, "
            f"worth about {_cap_words(market_cap)}."
        )
    if roe is not None and pe_ratio is not None:
        points.append(
            f"It earned {_percent(roe)} on shareholder money, "
            f"and the price is {_number(pe_ratio)} times earnings."
        )
    points.append("A reason to look, not a promise the price will rise.")
    return points


def _band(market_cap: Decimal | None) -> str:
    if market_cap is None or market_cap < _SMALL:
        return "small"
    if market_cap < _MID:
        return "mid"
    return "large"


def _size_word(market_cap: Decimal) -> str:
    return {"small": "smaller", "mid": "mid-size", "large": "large"}[_band(market_cap)]


def _cap_words(value: Decimal) -> str:
    if value >= Decimal("1000000000000"):
        amount = (value / Decimal("1000000000000")).quantize(Decimal("0.1"))
        unit = "trillion"
    elif value >= Decimal("1000000000"):
        amount = (value / Decimal("1000000000")).quantize(Decimal("0.1"))
        unit = "billion"
    elif value >= Decimal("1000000"):
        amount = (value / Decimal("1000000")).quantize(Decimal("0.1"))
        unit = "million"
    else:
        return f"${value.quantize(Decimal('1'))}"
    return f"${amount} {unit}"


def _percent(value: Decimal) -> str:
    points = (value * Decimal(100)).quantize(Decimal("0.1"))
    return f"{points}%"


def _number(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def _money(value: Decimal) -> str:
    return f"${format(value.quantize(Decimal('0.01')), ',f')}"


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
