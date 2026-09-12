from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for future SQLAlchemy models.

    Phase 1 has no domain models. Alembic uses ``Base.metadata`` so later
    models register automatically when they inherit from this class.
    """
