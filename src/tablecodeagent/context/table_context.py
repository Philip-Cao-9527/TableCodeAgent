from __future__ import annotations

from pathlib import Path
from typing import Any

from tablecodeagent.table_tools.core import load_table, profile_table


def build_table_context_package(
    tables: dict[str, str | Path],
    *,
    join_clues: list[dict[str, Any]] | None = None,
    field_semantics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    table_packages: dict[str, Any] = {}
    for name, path in tables.items():
        table = load_table(path, preview_rows=5)
        profile = profile_table(path)
        table_packages[name] = {
            "path": str(path),
            "format": table.get("format"),
            "columns": table["columns"],
            "row_count": table["row_count"],
            "preview_rows": table["preview_rows"],
            "column_profiles": profile["column_profiles"],
            "quality_flags": profile["quality_flags"],
            "duplicate_row_count": profile["duplicate_row_count"],
        }
    return {
        "compression_goal": "preserve field semantics and join evidence before reducing tokens",
        "tables": table_packages,
        "join_clues": join_clues or [],
        "field_semantics": field_semantics or {},
        "evidence_policy": {
            "preserve": [
                "field_names",
                "field_meanings",
                "units",
                "primary_keys",
                "join_keys",
                "time_windows",
                "filters",
                "quality_flags",
                "trace_evidence",
            ],
            "do_not_summarize_away": [
                "duplicate_keys",
                "row_expansion",
                "missing_values",
                "outliers",
                "time_window_mismatch",
            ],
        },
    }

