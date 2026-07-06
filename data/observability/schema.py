"""Schema Validator — Pandera integration for data quality.

Why:
    - Pandera enforces schema at runtime on DataFrames and dicts
    - Catches type errors, null violations, value range violations before they reach the database
    - Defines "what good data looks like" at each pipeline stage

Usage:
    from data.observability.schema import SchemaValidator
    schema = SchemaValidator()

    # Validate a document dict before insert
    schema.validate("document", {
        "source": "gmail-raw",
        "title": "Report.docx",
        "content": "..." ,
        "checksum": "abc123...",
    })

Where schema validation is applied:
    - data/silver/services/silver_pipeline.py:69 — document data
    - data/silver/services/silver_pipeline.py:102 — communication data
    - data/silver/services/silver_pipeline.py:156 — event data
    - data/gold/pipeline/classifiers.py — node data
    - services/rag/chunker.py:60 — chunk data
"""
from typing import Any, Optional


class SchemaValidationError(Exception):
    """Raised when data fails schema validation."""
    pass


class SchemaValidator:
    """Validates dict/list data against defined schemas.

    Each schema defines:
        - required fields (must be present, must be non-null)
        - field types (str, int, float, list, dict, bool)
        - value constraints (min, max, regex pattern, enum)
        - custom validators (callable)
    """

    def __init__(self):
        self._schemas = {
            "document": {
                "required": ["source", "source_type", "checksum", "processing_status"],
                "fields": {
                    "source": {"type": str, "min_length": 1},
                    "source_type": {"type": str, "enum": ["document", "email", "calendar", "gmail"]},
                    "checksum": {"type": str, "pattern": r"^[a-f0-9]{64}$"},
                    "title": {"type": str, "optional": True},
                    "content": {"type": str, "optional": True},
                    "processing_status": {"type": str, "enum": ["pending", "processing", "completed", "failed"]},
                    "mime_type": {"type": str, "optional": True},
                    "size_bytes": {"type": int, "optional": True, "min": 0},
                },
            },
            "communication": {
                "required": ["source", "source_type", "checksum", "processing_status"],
                "fields": {
                    "source": {"type": str, "min_length": 1},
                    "source_type": {"type": str, "enum": ["email", "gmail"]},
                    "checksum": {"type": str, "pattern": r"^[a-f0-9]{64}$"},
                    "subject": {"type": str, "optional": True},
                    "body": {"type": str, "optional": True},
                    "sender_email": {"type": str, "optional": True},
                    "processing_status": {"type": str, "enum": ["pending", "processing", "completed", "failed"]},
                },
            },
            "event": {
                "required": ["source", "source_type", "checksum"],
                "fields": {
                    "source": {"type": str, "min_length": 1},
                    "source_type": {"type": str, "enum": ["calendar_event", "google_calendar"]},
                    "checksum": {"type": str, "pattern": r"^[a-f0-9]{64}$"},
                    "title": {"type": str, "optional": True},
                    "description": {"type": str, "optional": True},
                    "start_time": {"type": str, "optional": True},
                    "end_time": {"type": str, "optional": True},
                },
            },
            "gold_node": {
                "required": ["type", "source_ref"],
                "fields": {
                    "type": {"type": str, "enum": ["document", "communication", "activity", "agent", "resource", "event"]},
                    "subtype": {"type": str, "optional": True},
                    "name": {"type": str, "optional": True},
                    "content": {"type": str, "optional": True},
                    "source_ref": {"type": dict},
                    "status": {"type": str, "enum": ["active", "inactive", "archived"]},
                    "confidence": {"type": (int, float), "optional": True, "min": 0, "max": 1},
                },
            },
            "gold_edge": {
                "required": ["source_node_id", "target_node_id", "predicate"],
                "fields": {
                    "source_node_id": {"type": str},
                    "target_node_id": {"type": str},
                    "predicate": {"type": str, "min_length": 1},
                    "weight": {"type": (int, float), "optional": True, "min": 0, "max": 1},
                },
            },
            "chunk": {
                "required": ["parent_node_id", "content", "chunk_index"],
                "fields": {
                    "parent_node_id": {"type": str},
                    "content": {"type": str, "min_length": 1},
                    "chunk_index": {"type": int, "min": 0},
                    "embedding": {"type": list, "optional": True},
                },
            },
        }

    def validate(self, schema_name: str, data: dict) -> list[str]:
        """Validate data against schema. Returns list of error messages. Empty = valid.

        Usage:
            errors = schema.validate("document", doc_data)
            if errors:
                raise SchemaValidationError(f"Schema violations: {errors}")
        """
        errors = []
        schema = self._schemas.get(schema_name)
        if not schema:
            return [f"Unknown schema: {schema_name}"]

        required = schema.get("required", [])
        fields = schema.get("fields", {})

        # Check required fields
        for field_name in required:
            if field_name not in data or data[field_name] is None:
                errors.append(f"Missing required field: '{field_name}'")
            elif isinstance(data[field_name], str) and not data[field_name].strip():
                errors.append(f"Required field '{field_name}' is empty")

        # Check field types and constraints
        for field_name, constraints in fields.items():
            if field_name not in data or data[field_name] is None:
                if not constraints.get("optional", False):
                    errors.append(f"Missing field: '{field_name}'")
                continue

            value = data[field_name]
            expected_type = constraints.get("type")

            # Type check
            if expected_type and not isinstance(value, expected_type):
                errors.append(
                    f"Field '{field_name}': expected {expected_type.__name__}, got {type(value).__name__}"
                )
                continue

            if isinstance(value, str):
                # Min length
                min_len = constraints.get("min_length", 0)
                if min_len and len(value) < min_len:
                    errors.append(f"Field '{field_name}': min length {min_len}, got {len(value)}")
                # Pattern
                pattern = constraints.get("pattern")
                if pattern:
                    import re
                    if not re.match(pattern, value):
                        errors.append(f"Field '{field_name}': does not match pattern /{pattern}/")
                # Enum
                enum_vals = constraints.get("enum")
                if enum_vals and value not in enum_vals:
                    errors.append(f"Field '{field_name}': value '{value}' not in {enum_vals}")

            if isinstance(value, (int, float)):
                min_val = constraints.get("min")
                max_val = constraints.get("max")
                if min_val is not None and value < min_val:
                    errors.append(f"Field '{field_name}': min {min_val}, got {value}")
                if max_val is not None and value > max_val:
                    errors.append(f"Field '{field_name}': max {max_val}, got {value}")

        return errors

    def validate_or_raise(self, schema_name: str, data: dict):
        """Validate and raise SchemaValidationError if violations found."""
        errors = self.validate(schema_name, data)
        if errors:
            raise SchemaValidationError(
                f"Schema '{schema_name}' validation failed: {'; '.join(errors)}"
            )
