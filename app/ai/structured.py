"""JSON schemas sent to a chat API. They describe filters, not SQL."""

from __future__ import annotations

from app.schemas.screening import CRITERIA_FIELDS

SCREEN_FIELDS = CRITERIA_FIELDS


def screen_json_schema() -> dict:
    """Strict object. Pagination is not a model field."""
    properties = {name: {"type": ["string", "null"]} for name in SCREEN_FIELDS}
    return {
        "type": "object",
        "properties": properties,
        "required": list(SCREEN_FIELDS),
        "additionalProperties": False,
    }


def explain_json_schema() -> dict:
    fields = ["what", "formula", "example", "yours", "watch"]
    return {
        "type": "object",
        "properties": {name: {"type": "string"} for name in fields},
        "required": fields,
        "additionalProperties": False,
    }


def interpretation_json_schema() -> dict:
    return {
        "type": "object",
        "properties": {"interpretation": {"type": "string"}},
        "required": ["interpretation"],
        "additionalProperties": False,
    }
