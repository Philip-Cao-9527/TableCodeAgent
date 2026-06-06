from __future__ import annotations

from typing import Any


def validate_answer(actual: Any, expected: Any, tolerance: float = 1e-6) -> dict[str, Any]:
    comparable_actual = actual.get("value") if isinstance(actual, dict) and "value" in actual else actual

    if isinstance(comparable_actual, (int, float)) and isinstance(expected, (int, float)):
        diff = abs(float(comparable_actual) - float(expected))
        return {"passed": diff <= tolerance, "actual": comparable_actual, "expected": expected, "diff": diff}

    passed = comparable_actual == expected
    return {"passed": passed, "actual": comparable_actual, "expected": expected, "diff": None}
