from decimal import Decimal
from typing import Annotated

from pydantic import BeforeValidator, Field, PlainSerializer


def parse_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def decimal_to_json(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


DecimalStr = Annotated[
    Decimal,
    BeforeValidator(parse_decimal),
    PlainSerializer(decimal_to_json, return_type=str),
]

PositiveDecimal = Annotated[
    Decimal,
    BeforeValidator(parse_decimal),
    Field(gt=0),
    PlainSerializer(decimal_to_json, return_type=str),
]


def parse_optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    return parse_decimal(value)


def optional_decimal_to_json(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return decimal_to_json(value)


OptionalDecimalStr = Annotated[
    Decimal | None,
    BeforeValidator(parse_optional_decimal),
    PlainSerializer(optional_decimal_to_json, return_type=str | None),
]
