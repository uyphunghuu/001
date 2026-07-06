"""Simple validation result and interface."""
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class BaseValidator:
    def validate(self, data: dict) -> ValidationResult:
        result = ValidationResult()
        if not data.get("checksum"):
            result.is_valid = False
            result.errors.append("Missing checksum")
        if not data.get("source"):
            result.is_valid = False
            result.errors.append("Missing source")
        return result
