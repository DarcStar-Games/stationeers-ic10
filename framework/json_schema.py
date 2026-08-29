"""Small dependency-free validator for the JSON Schema subset used by this repository."""
from __future__ import annotations

import json
import re
from typing import Any


class SchemaValidationError(ValueError):
    pass


SUPPORTED_KEYWORDS = {
    "$schema", "$id", "$defs", "$ref", "title", "description",
    "type", "const", "enum", "properties", "required",
    "additionalProperties", "items", "minItems", "maxItems",
    "uniqueItems", "minLength", "maxLength", "pattern", "minimum",
    "maximum", "allOf", "anyOf", "oneOf",
}


def validate_schema(schema: dict[str, Any]) -> None:
    """Fail closed when a repository schema uses a keyword we do not implement."""
    errors: list[str] = []

    def walk(rule: Any, path: str) -> None:
        if isinstance(rule, bool):
            return
        if not isinstance(rule, dict):
            errors.append(f"{path}: schema must be an object or boolean")
            return
        unknown = sorted(set(rule) - SUPPORTED_KEYWORDS)
        if unknown:
            errors.append(f"{path}: unsupported schema keyword(s): {', '.join(unknown)}")
        for name, child in rule.get("properties", {}).items():
            walk(child, f"{path}.properties.{name}")
        for name, child in rule.get("$defs", {}).items():
            walk(child, f"{path}.$defs.{name}")
        if isinstance(rule.get("additionalProperties"), dict):
            walk(rule["additionalProperties"], f"{path}.additionalProperties")
        if "items" in rule:
            walk(rule["items"], f"{path}.items")
        for keyword in ("allOf", "anyOf", "oneOf"):
            for index, child in enumerate(rule.get(keyword, [])):
                walk(child, f"{path}.{keyword}[{index}]")

    walk(schema, "$")
    if errors:
        raise SchemaValidationError("\n".join(errors))


def _resolve(root: dict[str, Any], reference: str) -> dict[str, Any]:
    if not reference.startswith("#/"):
        raise SchemaValidationError(f"unsupported non-local $ref: {reference}")
    value: Any = root
    for token in reference[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        value = value[token]
    if not isinstance(value, dict):
        raise SchemaValidationError(f"$ref does not resolve to a schema: {reference}")
    return value


def _type_matches(value: Any, expected: str) -> bool:
    return {
        "null": value is None,
        "boolean": isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "string": isinstance(value, str),
        "array": isinstance(value, list),
        "object": isinstance(value, dict),
    }.get(expected, False)


def validate(instance: Any, schema: dict[str, Any]) -> None:
    """Validate an instance and raise one error containing every discovered violation."""
    validate_schema(schema)
    errors: list[str] = []

    def walk(value: Any, rule: Any, path: str) -> None:
        if isinstance(rule, bool):
            if not rule:
                errors.append(f"{path}: value is forbidden")
            return
        if "$ref" in rule:
            walk(value, _resolve(schema, rule["$ref"]), path)
        if "const" in rule and value != rule["const"]:
            errors.append(f"{path}: expected {rule['const']!r}, got {value!r}")
        if "enum" in rule and value not in rule["enum"]:
            errors.append(f"{path}: {value!r} is not one of {rule['enum']!r}")
        expected = rule.get("type")
        if expected:
            choices = expected if isinstance(expected, list) else [expected]
            if not any(_type_matches(value, choice) for choice in choices):
                errors.append(f"{path}: expected type {expected!r}, got {type(value).__name__}")
                return
        for branch in rule.get("allOf", []):
            walk(value, branch, path)
        for keyword in ("anyOf", "oneOf"):
            if keyword not in rule:
                continue
            branch_errors = []
            for branch in rule[keyword]:
                before = len(errors)
                walk(value, branch, path)
                branch_errors.append(errors[before:])
                del errors[before:]
            matched = sum(not branch for branch in branch_errors)
            if not matched:
                errors.append(f"{path}: no {keyword} branch matched")
            elif keyword == "oneOf" and matched > 1:
                errors.append(f"{path}: {matched} oneOf branches matched, expected exactly one")
        if isinstance(value, dict):
            properties = rule.get("properties", {})
            for name in rule.get("required", []):
                if name not in value:
                    errors.append(f"{path}: missing required property {name!r}")
            for name, child in value.items():
                if name in properties:
                    walk(child, properties[name], f"{path}.{name}")
                elif rule.get("additionalProperties") is False:
                    errors.append(f"{path}: unexpected property {name!r}")
                elif isinstance(rule.get("additionalProperties"), dict):
                    walk(child, rule["additionalProperties"], f"{path}.{name}")
        if isinstance(value, list):
            if len(value) < rule.get("minItems", 0):
                errors.append(f"{path}: expected at least {rule['minItems']} items")
            if "maxItems" in rule and len(value) > rule["maxItems"]:
                errors.append(f"{path}: expected at most {rule['maxItems']} items")
            if rule.get("uniqueItems"):
                encoded = [json.dumps(item, sort_keys=True) for item in value]
                if len(encoded) != len(set(encoded)):
                    errors.append(f"{path}: items are not unique")
            if "items" in rule:
                for index, child in enumerate(value):
                    walk(child, rule["items"], f"{path}[{index}]")
        if isinstance(value, str):
            if len(value) < rule.get("minLength", 0):
                errors.append(f"{path}: string is too short")
            if "maxLength" in rule and len(value) > rule["maxLength"]:
                errors.append(f"{path}: string is too long")
            if "pattern" in rule and re.search(rule["pattern"], value) is None:
                errors.append(f"{path}: {value!r} does not match {rule['pattern']!r}")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in rule and value < rule["minimum"]:
                errors.append(f"{path}: {value} is below {rule['minimum']}")
            if "maximum" in rule and value > rule["maximum"]:
                errors.append(f"{path}: {value} is above {rule['maximum']}")

    walk(instance, schema, "$")
    if errors:
        raise SchemaValidationError("\n".join(errors))
