"""Small dependency-free validator for the JSON Schema subset used by this repository."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any


class SchemaValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One path-aware instance validation failure."""

    path: str
    reason: str

    def __str__(self) -> str:
        return f"{self.path}: {self.reason}"


@dataclass(slots=True)
class ValidationContext:
    """Root schema and collected issues for one validation traversal."""

    root_schema: dict[str, Any]
    issues: list[ValidationIssue] = field(default_factory=list)

    def add(self, path: str, reason: str) -> None:
        self.issues.append(ValidationIssue(path, reason))

    def branch(self) -> ValidationContext:
        """Return an isolated collection that shares only the root schema."""
        return ValidationContext(self.root_schema)

    def evaluate(
        self, value: Any, rule: Any, path: str = "$"
    ) -> tuple[ValidationIssue, ...]:
        """Evaluate a rule without changing this context's collected issues."""
        branch = self.branch()
        branch.walk(value, rule, path)
        return tuple(branch.issues)

    def walk(self, value: Any, rule: Any, path: str = "$") -> None:
        """Apply one schema rule and recursively dispatch its supported keywords."""
        if isinstance(rule, bool):
            if not rule:
                self.add(path, "value is forbidden")
            return

        _validate_reference(self, value, rule, path)
        if not _validate_scalar(self, value, rule, path):
            return
        _validate_combinators(self, value, rule, path)
        _validate_object(self, value, rule, path)
        _validate_array(self, value, rule, path)
        _validate_string(self, value, rule, path)
        _validate_numeric(self, value, rule, path)


SUPPORTED_KEYWORDS = {
    "$schema", "$id", "$defs", "$ref", "title", "description",
    "type", "const", "enum", "properties", "required",
    "additionalProperties", "items", "minItems", "maxItems",
    "uniqueItems", "minLength", "maxLength", "pattern", "minimum",
    "maximum", "allOf", "anyOf", "oneOf",
}


def _walk_schema(rule: Any, path: str, errors: list[str]) -> None:
    if isinstance(rule, bool):
        return
    if not isinstance(rule, dict):
        errors.append(f"{path}: schema must be an object or boolean")
        return
    unknown = sorted(set(rule) - SUPPORTED_KEYWORDS)
    if unknown:
        errors.append(f"{path}: unsupported schema keyword(s): {', '.join(unknown)}")
    for name, child in rule.get("properties", {}).items():
        _walk_schema(child, f"{path}.properties.{name}", errors)
    for name, child in rule.get("$defs", {}).items():
        _walk_schema(child, f"{path}.$defs.{name}", errors)
    if isinstance(rule.get("additionalProperties"), dict):
        _walk_schema(rule["additionalProperties"], f"{path}.additionalProperties", errors)
    if "items" in rule:
        _walk_schema(rule["items"], f"{path}.items", errors)
    for keyword in ("allOf", "anyOf", "oneOf"):
        for index, child in enumerate(rule.get(keyword, [])):
            _walk_schema(child, f"{path}.{keyword}[{index}]", errors)


def validate_schema(schema: dict[str, Any]) -> None:
    """Fail closed when a repository schema uses a keyword we do not implement."""
    errors: list[str] = []
    _walk_schema(schema, "$", errors)
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


def _validate_reference(
    context: ValidationContext, value: Any, rule: dict[str, Any], path: str
) -> None:
    if "$ref" in rule:
        context.walk(value, _resolve(context.root_schema, rule["$ref"]), path)


def _validate_scalar(
    context: ValidationContext, value: Any, rule: dict[str, Any], path: str
) -> bool:
    """Validate value-wide constraints and return whether typed checks may continue."""
    if "const" in rule and value != rule["const"]:
        context.add(path, f"expected {rule['const']!r}, got {value!r}")
    if "enum" in rule and value not in rule["enum"]:
        context.add(path, f"{value!r} is not one of {rule['enum']!r}")
    expected = rule.get("type")
    if expected:
        choices = expected if isinstance(expected, list) else [expected]
        if not any(_type_matches(value, choice) for choice in choices):
            context.add(path, f"expected type {expected!r}, got {type(value).__name__}")
            return False
    return True


def _validate_combinators(
    context: ValidationContext, value: Any, rule: dict[str, Any], path: str
) -> None:
    for branch in rule.get("allOf", []):
        context.walk(value, branch, path)
    for keyword in ("anyOf", "oneOf"):
        if keyword not in rule:
            continue
        branch_results = [
            context.evaluate(value, branch, path) for branch in rule[keyword]
        ]
        matched = sum(not branch_issues for branch_issues in branch_results)
        if not matched:
            context.add(path, f"no {keyword} branch matched")
        elif keyword == "oneOf" and matched > 1:
            context.add(path, f"{matched} oneOf branches matched, expected exactly one")


def _validate_object(
    context: ValidationContext, value: Any, rule: dict[str, Any], path: str
) -> None:
    if not isinstance(value, dict):
        return
    properties = rule.get("properties", {})
    for name in rule.get("required", []):
        if name not in value:
            context.add(path, f"missing required property {name!r}")
    for name, child in value.items():
        if name in properties:
            context.walk(child, properties[name], f"{path}.{name}")
        elif rule.get("additionalProperties") is False:
            context.add(path, f"unexpected property {name!r}")
        elif isinstance(rule.get("additionalProperties"), dict):
            context.walk(child, rule["additionalProperties"], f"{path}.{name}")


def _validate_array(
    context: ValidationContext, value: Any, rule: dict[str, Any], path: str
) -> None:
    if not isinstance(value, list):
        return
    if len(value) < rule.get("minItems", 0):
        context.add(path, f"expected at least {rule['minItems']} items")
    if "maxItems" in rule and len(value) > rule["maxItems"]:
        context.add(path, f"expected at most {rule['maxItems']} items")
    if rule.get("uniqueItems"):
        encoded = [json.dumps(item, sort_keys=True) for item in value]
        if len(encoded) != len(set(encoded)):
            context.add(path, "items are not unique")
    if "items" in rule:
        for index, child in enumerate(value):
            context.walk(child, rule["items"], f"{path}[{index}]")


def _validate_string(
    context: ValidationContext, value: Any, rule: dict[str, Any], path: str
) -> None:
    if not isinstance(value, str):
        return
    if len(value) < rule.get("minLength", 0):
        context.add(path, "string is too short")
    if "maxLength" in rule and len(value) > rule["maxLength"]:
        context.add(path, "string is too long")
    if "pattern" in rule and re.search(rule["pattern"], value) is None:
        context.add(path, f"{value!r} does not match {rule['pattern']!r}")


def _validate_numeric(
    context: ValidationContext, value: Any, rule: dict[str, Any], path: str
) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return
    if "minimum" in rule and value < rule["minimum"]:
        context.add(path, f"{value} is below {rule['minimum']}")
    if "maximum" in rule and value > rule["maximum"]:
        context.add(path, f"{value} is above {rule['maximum']}")


def validate(instance: Any, schema: dict[str, Any]) -> None:
    """Validate an instance and raise one error containing every discovered violation."""
    validate_schema(schema)
    context = ValidationContext(schema)
    context.walk(instance, schema)
    if context.issues:
        raise SchemaValidationError("\n".join(map(str, context.issues)))
