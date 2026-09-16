"""Validate contract JSON and its positive/negative examples without network access."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


CONTRACT_FILES = (
    "query.schema.json",
    "answer.schema.json",
    "transcript.schema.json",
    "websocket-client-events.schema.json",
    "websocket-server-events.schema.json",
)


class ContractValidationError(ValueError):
    pass


def _pointer(root: Any, fragment: str) -> Any:
    value = root
    for token in fragment.removeprefix("#/").split("/") if fragment not in ("", "#") else ():
        value = value[token.replace("~1", "/").replace("~0", "~")]
    return value


def _resolve_ref(ref: str, schema: dict[str, Any], schemas: dict[str, dict[str, Any]]) -> tuple[Any, dict[str, Any]]:
    if ref.startswith("#"):
        return _pointer(schema, ref), schema
    file_name, _, fragment = ref.partition("#")
    target = schemas.get(Path(file_name).name)
    if target is None:
        raise ContractValidationError(f"unresolved contract reference: {ref}")
    return _pointer(target, f"#{fragment}" if fragment else "#"), target


def _type_matches(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(expected, True)


def validate_instance(
    value: Any,
    schema: dict[str, Any],
    schemas: dict[str, dict[str, Any]],
    *,
    root_schema: dict[str, Any] | None = None,
    path: str = "$",
) -> None:
    root_schema = root_schema or schema
    if "$ref" in schema:
        target, target_root = _resolve_ref(schema["$ref"], root_schema, schemas)
        return validate_instance(value, target, schemas, root_schema=target_root, path=path)
    if "allOf" in schema:
        for branch in schema["allOf"]:
            validate_instance(value, branch, schemas, root_schema=root_schema, path=path)
    if "oneOf" in schema:
        successes = 0
        for branch in schema["oneOf"]:
            try:
                validate_instance(
                    value,
                    branch,
                    schemas,
                    root_schema=root_schema,
                    path=path,
                )
            except ContractValidationError:
                continue
            successes += 1
        if successes != 1:
            raise ContractValidationError(f"{path}: expected exactly one matching schema, got {successes}")
    expected = schema.get("type")
    if expected is not None:
        types = expected if isinstance(expected, list) else [expected]
        if not any(_type_matches(value, item) for item in types):
            raise ContractValidationError(f"{path}: expected type {expected!r}")
    if "const" in schema and value != schema["const"]:
        raise ContractValidationError(f"{path}: expected {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise ContractValidationError(f"{path}: value is outside enum")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise ContractValidationError(f"{path}: string is too short")
        if schema.get("format") == "date-time" and not re.match(r"^\d{4}-\d{2}-\d{2}T.+(?:Z|[+-]\d{2}:?\d{2})$", value):
            raise ContractValidationError(f"{path}: invalid date-time")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value < schema.get("minimum", value):
            raise ContractValidationError(f"{path}: number is below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise ContractValidationError(f"{path}: number is above maximum")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise ContractValidationError(f"{path}: array has too few items")
        if "items" in schema:
            for index, item in enumerate(value):
                validate_instance(item, schema["items"], schemas, root_schema=root_schema, path=f"{path}[{index}]")
    if isinstance(value, dict):
        required = set(schema.get("required", ()))
        missing = required - value.keys()
        if missing:
            raise ContractValidationError(f"{path}: missing required properties {sorted(missing)}")
        properties = schema.get("properties", {})
        for key, child in properties.items():
            if key in value:
                validate_instance(value[key], child, schemas, root_schema=root_schema, path=f"{path}.{key}")
        if schema.get("additionalProperties") is False:
            extras = set(value) - set(properties)
            if extras:
                raise ContractValidationError(f"{path}: unexpected properties {sorted(extras)}")
        elif isinstance(schema.get("additionalProperties"), dict):
            for key in set(value) - set(properties):
                validate_instance(value[key], schema["additionalProperties"], schemas, root_schema=root_schema, path=f"{path}.{key}")
        if schema.get("unevaluatedProperties") is False and "allOf" in schema:
            allowed: set[str] = set()
            for branch in schema["allOf"]:
                if isinstance(branch, dict):
                    allowed.update(branch.get("properties", {}).keys())
                    if "$ref" in branch:
                        target, _ = _resolve_ref(branch["$ref"], root_schema, schemas)
                        allowed.update(target.get("properties", {}).keys())
            extras = set(value) - allowed
            if extras:
                raise ContractValidationError(f"{path}: unevaluated properties {sorted(extras)}")


def load_contracts(contracts_root: Path) -> dict[str, dict[str, Any]]:
    schemas: dict[str, dict[str, Any]] = {}
    for name in CONTRACT_FILES:
        payload = json.loads((contracts_root / name).read_text(encoding="utf-8"))
        schemas[name] = payload
        schemas[payload["$id"].rsplit("/", 1)[-1]] = payload
    return schemas


def validate_examples(contracts_root: Path, examples_root: Path) -> dict[str, Any]:
    schemas = load_contracts(contracts_root)
    pairs = {
        "query": ("query.valid.json", "query.invalid.json", "query.schema.json"),
        "answer": ("answer.valid.json", "answer.invalid.json", "answer.schema.json"),
        "transcript": ("transcript.valid.json", "transcript.invalid.json", "transcript.schema.json"),
        "websocket-client": ("websocket-client.valid.json", "websocket-client.invalid.json", "websocket-client-events.schema.json"),
        "websocket-server": ("websocket-server.valid.json", "websocket-server.invalid.json", "websocket-server-events.schema.json"),
    }
    report: dict[str, Any] = {}
    for name, (valid_name, invalid_name, schema_name) in pairs.items():
        schema = schemas[schema_name]
        valid = json.loads((examples_root / valid_name).read_text(encoding="utf-8"))
        invalid = json.loads((examples_root / invalid_name).read_text(encoding="utf-8"))
        try:
            validate_instance(valid, schema, schemas)
        except ContractValidationError as error:
            raise ContractValidationError(f"{name} valid example: {error}") from error
        try:
            validate_instance(invalid, schema, schemas)
        except ContractValidationError:
            invalid_rejected = True
        else:
            invalid_rejected = False
            raise ContractValidationError(f"{name}: invalid example was accepted")
        report[name] = {"valid": True, "invalid_rejected": invalid_rejected}
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contracts-root", type=Path, default=Path(__file__).resolve().parents[1] / "00-contracts")
    parser.add_argument("--examples-root", type=Path)
    args = parser.parse_args(argv)
    examples_root = args.examples_root or args.contracts_root / "examples"
    report = validate_examples(args.contracts_root, examples_root)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
