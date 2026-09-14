from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Stable constraint names make Alembic diffs readable and keep
# ON CONFLICT targets explicit in seed / ingestion SQL.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base shared by models and Alembic.

    Schema changes go through Alembic revisions. Application startup
    never calls ``Base.metadata.create_all()``.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
