from collections.abc import Generator

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.ai.factory import build_assistant_model
from app.ai.provider import AssistantModel
from app.ai.tools import SafeToolExecutor
from app.core.cache import CacheBackend, commit_and_invalidate, get_cache
from app.core.exceptions import AuthenticationError
from app.core.security import decode_access_token
from app.db.models import User
from app.db.session import SessionLocal
from app.quotes.store import QuoteStore, build_quote_store
from app.services.analytics_service import AnalyticsService
from app.services.assistant_service import AssistantService
from app.services.auth_service import AuthService
from app.services.job_service import JobService
from app.services.portfolio_service import PortfolioService
from app.services.position_service import PositionService
from app.services.reference_service import ReferenceService
from app.services.screening_service import ScreeningService
from app.services.watchlist_service import WatchlistService

bearer_scheme = HTTPBearer(auto_error=False)


def get_db(
    cache: CacheBackend = Depends(get_cache),
) -> Generator[Session, None, None]: #commit and rollback transactions
    """Yield a request-scoped session. Commit on success, rollback on error."""
    db = SessionLocal()
    try:
        yield db
        commit_and_invalidate(db, cache)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError()
    user_id = decode_access_token(credentials.credentials)
    user = db.get(User, user_id)
    if user is None:
        raise AuthenticationError("Token subject no longer exists")
    return user


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(db)


def get_watchlist_service(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WatchlistService:
    return WatchlistService(db, current_user.id)


def get_portfolio_service(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PortfolioService:
    return PortfolioService(db, current_user.id)


def get_analytics_service( 
    db: Session = Depends(get_db),
    cache: CacheBackend = Depends(get_cache),
    current_user: User = Depends(get_current_user),
) -> AnalyticsService:
    return AnalyticsService(db, current_user.id, cache)


def get_job_service(db: Session = Depends(get_db)) -> JobService:
    return JobService(db)


def get_screening_service(
    db: Session = Depends(get_db),
    cache: CacheBackend = Depends(get_cache),
) -> ScreeningService:
    return ScreeningService(db, cache)


def get_assistant_model() -> AssistantModel:
    # Built without a session. Portfolio reads stay in AnalyticsService.
    return build_assistant_model()


def get_quote_store() -> QuoteStore:
    return build_quote_store()


def get_position_service(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    quotes: QuoteStore = Depends(get_quote_store),
) -> PositionService:
    return PositionService(db, current_user.id, quotes)


def get_reference_service(
    db: Session = Depends(get_db),
    quotes: QuoteStore = Depends(get_quote_store),
) -> ReferenceService:
    return ReferenceService(db, quotes)


def get_assistant_service(
    analytics: AnalyticsService = Depends(get_analytics_service),
    model: AssistantModel = Depends(get_assistant_model),
    quotes: QuoteStore = Depends(get_quote_store),
) -> AssistantService:
    return AssistantService(analytics, model, quotes)


def get_safe_tool_executor(
    analytics: AnalyticsService = Depends(get_analytics_service),
    screening: ScreeningService = Depends(get_screening_service),
    reference: ReferenceService = Depends(get_reference_service),
    quotes: QuoteStore = Depends(get_quote_store),
) -> SafeToolExecutor:
    """Authenticated application services only; no database handle reaches a model."""
    return SafeToolExecutor(
        analytics=analytics,
        screening=screening,
        reference=reference,
        quotes=quotes,
    )
