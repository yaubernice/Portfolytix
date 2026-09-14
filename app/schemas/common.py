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
