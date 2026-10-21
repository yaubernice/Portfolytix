from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.auth import RegisterRequest
from app.schemas.portfolio import PortfolioCreate
from app.schemas.transaction import TransactionCreate


def test_register_normalizes_email_and_rejects_short_password() -> None:
    created = RegisterRequest(
        email="USER@Example.com",
        password="password-123",
    )
    assert created.email == "user@example.com"

    with pytest.raises(ValidationError):
        RegisterRequest(email="user@example.com", password="short")
    with pytest.raises(ValidationError):
        RegisterRequest(email="not-an-email", password="password-123")


def test_portfolio_create_rejects_blank_name_and_user_id() -> None:
    with pytest.raises(ValidationError):
        PortfolioCreate(name="")
    with pytest.raises(ValidationError):
        PortfolioCreate(name="Core", user_id="00000000-0000-4000-8000-000000000001")


def test_transaction_create_requires_positive_money_fields() -> None:
    payload = {
        "ticker": "aapl",
        "transaction_type": "BUY",
        "quantity": "10",
        "price": "185.25",
    }
    created = TransactionCreate.model_validate(payload)
    assert created.quantity == Decimal("10")
    assert created.price == Decimal("185.25")
    with pytest.raises(ValidationError):
        TransactionCreate.model_validate({**payload, "quantity": "10.50"})

    for field, value in (("quantity", "0"), ("price", "-1"), ("quantity", "-2")):
        with pytest.raises(ValidationError):
            TransactionCreate.model_validate({**payload, field: value})
    with pytest.raises(ValidationError):
        TransactionCreate.model_validate(
            {**payload, "transaction_type": "DIVIDEND"}
        )
