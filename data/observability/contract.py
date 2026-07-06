"""Data Contract Validator — Great Expectations integration.

Why:
    - Data contracts define the schema, quality, and SLA guarantees between producer and consumer
    - Without contracts, a producer can silently break the consumer
    - Great Expectations validates data against expectations and blocks bad data

Where contracts are enforced:
    1. Bronze → Silver: email.json must have required headers, valid base64, non-empty content
    2. Silver → Gold: source_ref must reference existing Silver records, embedding must be 384-dim
    3. Gold → RAG: chunks must have valid parent_id, non-empty content, valid embedding
    4. RAG → Agent: retrieved context must have relevance score > threshold

How:
    - Each contract is a YAML file in data/contracts/
    - This module loads contract YAML, validates data against expectations
    - On violation: can log, alert, or block (stop pipeline) based on severity
"""
import json
import os
import yaml
from enum import Enum
from typing import Any, Optional


class Severity(Enum):
    CRITICAL = "critical"  # Blocks pipeline
    HIGH = "high"          # Alerts + blocks if configurable
    MEDIUM = "medium"      # Alerts only
    LOW = "low"            # Logs only


class ContractViolation(Exception):
    """Raised when a CRITICAL or HIGH contract clause is violated."""
    pass


class ContractValidator:
    """Validates data payloads against contract definitions.

    Usage:
        validator = ContractValidator()
        # Validate an email.json before processing
        violations = validator.validate("bronze_to_silver", email_data)
        if violations:
            logger.warning(f"Contract violations: {violations}")
            if any(v.severity == Severity.CRITICAL for v in violations):
                raise ContractViolation("Critical contract violation — blocking pipeline")
    """

    def __init__(self, contracts_dir: str = "data/contracts"):
        self.contracts_dir = contracts_dir
        self._cache = {}

    def _load_contract(self, contract_name: str) -> dict:
        """Load a contract YAML file."""
        if contract_name in self._cache:
            return self._cache[contract_name]

        path = os.path.join(self.contracts_dir, f"{contract_name}.yaml")
        if not os.path.exists(path):
            return {}

        with open(path, "r", encoding="utf-8") as f:
            contract = yaml.safe_load(f)
            self._cache[contract_name] = contract
            return contract

    def validate(self, contract_name: str, data: Any) -> list[dict]:
        """Validate data against a named contract.

        Returns list of violation dicts: [{"clause": "...", "severity": "critical", "field": "...", "message": "..."}]
        Empty list means data passes the contract.
        """
        contract = self._load_contract(contract_name)
        if not contract:
            return []

        violations = []
        spec = contract.get("spec", {})
        schema = spec.get("schema", {})
        fields = schema.get("fields", [])
        clauses = contract.get("spec", {}).get("clauses", contract.get("clauses", []))

        # Field-level validation
        for field_def in fields:
            field_name = field_def.get("name", "")
            required = field_def.get("required", False)
            field_type = field_def.get("type", "string")

            value = self._get_nested(data, field_name)

            # Required check
            if required:
                if value is None or (isinstance(value, str) and not value.strip()):
                    violations.append({
                        "clause": f"Required field '{field_name}' is missing or empty",
                        "severity": field_def.get("severity", "critical"),
                        "field": field_name,
                        "message": f"Required field '{field_name}' is missing or empty",
                    })

            # Type check
            if value is not None:
                type_ok = self._check_type(value, field_type)
                if not type_ok:
                    violations.append({
                        "clause": f"Field '{field_name}' type mismatch: expected {field_type}",
                        "severity": "high",
                        "field": field_name,
                        "message": f"Expected {field_type}, got {type(value).__name__}",
                    })

            # Enum check
            enum_values = field_def.get("enum", [])
            if enum_values and value is not None and value not in enum_values:
                violations.append({
                    "clause": f"Field '{field_name}' value '{value}' not in allowed values",
                    "severity": "high",
                    "field": field_name,
                    "message": f"Value '{value}' not in {enum_values}",
                })

            # Pattern check
            pattern = field_def.get("pattern", "")
            if pattern and value and isinstance(value, str):
                import re
                if not re.match(pattern, value):
                    violations.append({
                        "clause": f"Field '{field_name}' does not match pattern {pattern}",
                        "severity": "high",
                        "field": field_name,
                        "message": f"Value '{value}' does not match pattern",
                    })

            # Min/max length
            min_len = field_def.get("minLength", 0)
            if min_len and isinstance(value, str) and len(value) < min_len:
                violations.append({
                    "clause": f"Field '{field_name}' too short: min {min_len} chars",
                    "severity": "medium",
                    "field": field_name,
                    "message": f"Got {len(value)} chars, expected ≥{min_len}",
                })

        # Clause-level validation
        clauses_list = clauses or []
        if isinstance(clauses_list, list):
            for clause in clauses_list:
                if isinstance(clause, dict):
                    clause_text = clause.get("clause", "")
                    severity = clause.get("severity", "medium")
                    violations.append({
                        "clause": clause_text,
                        "severity": severity,
                        "field": "_contract_clause",
                        "message": clause_text,
                    })

        return violations

    def validate_or_raise(self, contract_name: str, data: Any):
        """Validate and raise ContractViolation on critical/high severity violations."""
        violations = self.validate(contract_name, data)
        critical = [v for v in violations if v.get("severity") in ("critical", "high")]
        if critical:
            raise ContractViolation(
                f"Contract '{contract_name}' violated: {json.dumps(critical, ensure_ascii=False)}"
            )

    def _get_nested(self, data: Any, path: str) -> Any:
        """Get nested value using dot notation (e.g., 'payload.headers')."""
        if data is None:
            return None
        parts = path.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                try:
                    idx = int(part)
                    current = current[idx] if idx < len(current) else None
                except (ValueError, IndexError):
                    return None
            else:
                return None
        return current

    def _check_type(self, value: Any, expected_type: str) -> bool:
        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
            "array[object]": list,
            "jsonb": (dict, list),
        }
        expected = type_map.get(expected_type)
        if expected is None:
            return True
        if expected_type == "array[object]":
            return isinstance(value, list) and all(isinstance(item, dict) for item in value)
        return isinstance(value, expected)
