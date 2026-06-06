from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any


def _pd():
    try:
        import pandas as pd
        return pd
    except ImportError as error:
        raise ImportError("TableCodeAgent pandas backend requires pandas.") from error


def _np():
    try:
        import numpy as np
        return np
    except ImportError as error:
        raise ImportError("Reading .npy/.npz files requires numpy.") from error


def _map_frame(frame: Any, func: Any) -> Any:
    mapper = getattr(frame, "map", None)
    return mapper(func) if mapper else frame.applymap(func)


def _stringify_cell(value: Any) -> str:
    pd = _pd()
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    if value is None:
        return ""
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _stringify_series(series: Any) -> Any:
    return series.map(_stringify_cell)


def _stringify_frame(frame: Any) -> Any:
    return _map_frame(frame, _stringify_cell)


def _make_unique_columns(columns: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    unique: list[str] = []
    for idx, column in enumerate(columns, start=1):
        base = str(column).strip() or f"column_{idx}"
        count = seen.get(base, 0) + 1
        seen[base] = count
        unique.append(base if count == 1 else f"{base}_{count}")
    return unique


def _collapse_header_parts(values: Any) -> str:
    parts = [str(value).strip() for value in values if str(value).strip()]
    compact = [part for idx, part in enumerate(parts) if idx == 0 or part != parts[idx - 1]]
    return "__".join(compact)


def _columns_from_header(header_frame: Any) -> list[str]:
    if header_frame.empty:
        return []
    text = _stringify_frame(header_frame)
    filled = text.mask(text.eq("")).ffill(axis=1).fillna("")
    columns = filled.T.apply(_collapse_header_parts, axis=1).tolist()
    return _make_unique_columns(columns)


def _frame_from_raw(raw: Any, header_rows: int) -> Any:
    pd = _pd()
    if header_rows < 1:
        raise ValueError("header_rows must be >= 1.")
    if raw.shape[0] < header_rows:
        return pd.DataFrame()

    columns = _columns_from_header(raw.iloc[:header_rows])
    data = raw.iloc[header_rows:, :len(columns)].copy()
    data.columns = columns
    non_empty = _stringify_frame(data).ne("").any(axis=1)
    return data.loc[non_empty].reset_index(drop=True)


def _read_xlsx_raw(
    path: Path,
    sheet_name: str | None = None,
    fill_merged_cells: bool = False,
) -> tuple[Any, str, list[str]]:
    pd = _pd()
    try:
        excel = pd.ExcelFile(path)
    except ImportError as error:
        raise ImportError("Reading .xlsx files requires a pandas-compatible Excel engine.") from error

    actual_sheet = sheet_name or excel.sheet_names[0]
    raw = pd.read_excel(
        excel,
        sheet_name=actual_sheet,
        header=None,
        dtype=object,
        keep_default_na=False,
    )

    if fill_merged_cells:
        blank = raw.isna() | raw.astype("string").apply(lambda column: column.str.strip().eq(""))
        raw = raw.mask(blank).ffill(axis=0).ffill(axis=1).fillna("")

    return raw, actual_sheet, excel.sheet_names


def _frame_from_array(value: Any, *, prefix: str = "value") -> Any:
    pd = _pd()
    np = _np()
    array = np.asarray(value)
    if array.ndim == 0:
        return pd.DataFrame({prefix: [array.item()]})
    if array.ndim == 1:
        return pd.DataFrame({prefix: array})
    if array.ndim == 2:
        return pd.DataFrame(array, columns=[f"column_{idx + 1}" for idx in range(array.shape[1])])
    flat = array.reshape((array.shape[0], -1))
    return pd.DataFrame(flat, columns=[f"column_{idx + 1}" for idx in range(flat.shape[1])])


def read_table_frame(
    table_path: str | Path,
    *,
    sheet_name: str | None = None,
    header_rows: int = 1,
    fill_merged_cells: bool = False,
) -> tuple[Any, dict[str, Any]]:
    pd = _pd()
    path = Path(table_path)
    suffix = path.suffix.lower()
    metadata: dict[str, Any] = {"path": str(path), "format": suffix.lstrip(".") or "csv"}

    if suffix in ("", ".csv"):
        raw = pd.read_csv(path, header=None, dtype=object, keep_default_na=False)
        frame = _frame_from_raw(raw, header_rows)
    elif suffix == ".xlsx":
        raw, actual_sheet, sheet_names = _read_xlsx_raw(path, sheet_name, fill_merged_cells)
        frame = _frame_from_raw(raw, header_rows)
        metadata["sheet_name"] = actual_sheet
        metadata["sheet_names"] = sheet_names
        metadata["fill_merged_cells"] = fill_merged_cells
    elif suffix == ".feather":
        try:
            frame = pd.read_feather(path)
        except ImportError as error:
            raise ImportError("Reading .feather files requires pyarrow.") from error
    elif suffix == ".npy":
        frame = _frame_from_array(_np().load(path, allow_pickle=False))
    elif suffix == ".npz":
        loaded = _np().load(path, allow_pickle=False)
        parts = [
            _frame_from_array(loaded[name], prefix=name).add_prefix(f"{name}__")
            for name in loaded.files
        ]
        frame = pd.concat(parts, axis=1) if parts else pd.DataFrame()
    else:
        raise ValueError(f"Unsupported table format: {suffix}")

    frame = frame.copy().reset_index(drop=True)
    frame.columns = _make_unique_columns([_stringify_cell(column) for column in frame.columns])
    metadata["header_rows"] = header_rows
    return frame, metadata


def _frame_to_rows(frame: Any) -> list[dict[str, str]]:
    return _stringify_frame(frame).to_dict(orient="records")


def _read_table(
    table_path: str | Path,
    *,
    sheet_name: str | None = None,
    header_rows: int = 1,
    fill_merged_cells: bool = False,
) -> tuple[list[str], list[dict[str, str]], dict[str, Any]]:
    frame, metadata = read_table_frame(
        table_path,
        sheet_name=sheet_name,
        header_rows=header_rows,
        fill_merged_cells=fill_merged_cells,
    )
    return list(frame.columns), _frame_to_rows(frame), metadata


def _read_rows(
    csv_path: str | Path,
    *,
    sheet_name: str | None = None,
    header_rows: int = 1,
    fill_merged_cells: bool = False,
) -> list[dict[str, str]]:
    return _read_table(
        csv_path,
        sheet_name=sheet_name,
        header_rows=header_rows,
        fill_merged_cells=fill_merged_cells,
    )[1]


def _missing_frame(frame: Any) -> Any:
    blank = frame.astype("string").apply(lambda column: column.str.strip().eq(""))
    return frame.isna() | blank.fillna(False)


def _numeric_frame(frame: Any) -> Any:
    pd = _pd()
    normalized = frame.mask(_missing_frame(frame), pd.NA)
    return normalized.apply(pd.to_numeric, errors="coerce")


def _numeric_series(series: Any) -> Any:
    pd = _pd()
    blank = series.astype("string").str.strip().eq("").fillna(False)
    normalized = series.mask(series.isna() | blank, pd.NA)
    return pd.to_numeric(normalized, errors="coerce")


def _to_number(value: Any) -> float | None:
    pd = _pd()
    result = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(result) else float(result)


def _infer_type(series: Any, numeric: Any | None = None) -> str:
    pd = _pd()
    present = _stringify_series(series).str.strip()
    present = present[present.ne("")]
    if present.empty:
        return "empty"

    numeric = pd.to_numeric(present, errors="coerce") if numeric is None else numeric.loc[present.index]
    if numeric.notna().all():
        return "integer" if numeric.mod(1).eq(0).all() else "number"

    date_like = present.str.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?$").all()
    if date_like and pd.to_datetime(present, errors="coerce").notna().all():
        return "date"
    return "string"


def _numeric_stats(frame: Any) -> dict[str, dict[str, float | int]]:
    numeric = _numeric_frame(frame)
    stats = numeric.agg(["count", "min", "max", "mean", "sum"]).T
    stats = stats.loc[stats["count"] > 0]
    stats["count"] = stats["count"].astype(int)
    records = stats.to_dict(orient="index")
    return {
        column: {
            "count": int(values["count"]),
            "min": float(values["min"]),
            "max": float(values["max"]),
            "mean": float(values["mean"]),
            "sum": float(values["sum"]),
        }
        for column, values in records.items()
    }


def load_table(
    csv_path: str | Path,
    preview_rows: int = 5,
    sheet_name: str | None = None,
    header_rows: int = 1,
    fill_merged_cells: bool = False,
) -> dict[str, Any]:
    frame, metadata = read_table_frame(
        csv_path,
        sheet_name=sheet_name,
        header_rows=header_rows,
        fill_merged_cells=fill_merged_cells,
    )
    preview_size = max(0, preview_rows)
    preview = frame.head(preview_size)
    return {
        **metadata,
        "columns": list(frame.columns),
        "row_count": int(len(frame)),
        "preview_row_count": int(len(preview)),
        "preview_rows": _frame_to_rows(preview),
    }


def profile_table(
    csv_path: str | Path,
    sheet_name: str | None = None,
    header_rows: int = 1,
    fill_merged_cells: bool = False,
) -> dict[str, Any]:
    frame, metadata = read_table_frame(
        csv_path,
        sheet_name=sheet_name,
        header_rows=header_rows,
        fill_merged_cells=fill_merged_cells,
    )
    columns = list(frame.columns)
    missing_frame = _missing_frame(frame)
    missing_counts = missing_frame.sum().astype(int)
    missing_rates = missing_frame.mean().fillna(0.0)
    missing = missing_counts.to_dict()
    duplicate_row_count = int(_stringify_frame(frame).duplicated().sum())

    numeric_stats = _numeric_stats(frame)
    numeric_values = _numeric_frame(frame)
    column_profiles = {
        column: {
            "missing_count": int(missing[column]),
            "missing_rate": float(missing_rates[column]),
            "unique_count": int(frame.loc[~missing_frame[column], column].nunique(dropna=True)),
            "inferred_type": _infer_type(frame[column], numeric_values[column]),
            "numeric_stats": numeric_stats.get(column),
            "flags": [
                flag
                for flag, enabled in (
                    ("has_missing", bool(len(frame) and missing[column])),
                    ("all_missing", bool(len(frame) and missing[column] == len(frame))),
                )
                if enabled
            ],
        }
        for column in columns
    }

    quality_flags: list[str] = []
    if frame.empty:
        quality_flags.append("empty_table")
    if duplicate_row_count:
        quality_flags.append("duplicate_rows")
    if any(count > 0 for count in missing.values()):
        quality_flags.append("columns_with_missing")

    return {
        **metadata,
        "row_count": int(len(frame)),
        "column_count": int(len(columns)),
        "columns": columns,
        "missing_values": missing,
        "numeric_stats": numeric_stats,
        "column_profiles": column_profiles,
        "duplicate_row_count": duplicate_row_count,
        "quality_flags": quality_flags,
    }


def _normalize_filters(filters: Any) -> list[dict[str, Any]]:
    if not filters:
        return []
    if isinstance(filters, str):
        try:
            filters = json.loads(filters)
        except json.JSONDecodeError as error:
            raise ValueError("filters string must be valid JSON.") from error
    if isinstance(filters, dict):
        if {"column", "op", "value"}.issubset(filters):
            return [filters]
        return [{"column": key, "op": "eq", "value": value} for key, value in filters.items()]
    if isinstance(filters, list):
        normalized = []
        for item in filters:
            if not isinstance(item, dict):
                raise ValueError("Each filter must be an object.")
            if "column" not in item or "value" not in item:
                raise ValueError("Each filter must include column and value.")
            normalized.append({
                "column": item["column"],
                "op": item.get("op", "eq"),
                "value": item["value"],
            })
        return normalized
    raise ValueError("filters must be an object or a list of objects.")


def _filter_series(frame: Any, column: str) -> Any:
    pd = _pd()
    if column in frame.columns:
        return frame[column]
    return pd.Series([""] * len(frame), index=frame.index, dtype=object)


def _apply_filters(frame: Any, filters: list[dict[str, Any]]) -> Any:
    pd = _pd()
    mask = pd.Series(True, index=frame.index)
    for condition in filters:
        column = condition["column"]
        op = condition.get("op", "eq")
        expected = condition["value"]
        series = _filter_series(frame, column)
        text = _stringify_series(series)

        if op in ("eq", "=="):
            current = text.eq(str(expected))
        elif op in ("ne", "!="):
            current = text.ne(str(expected))
        elif op == "contains":
            current = text.str.contains(str(expected), regex=False, na=False)
        else:
            actual_num = pd.to_numeric(text.replace("", pd.NA), errors="coerce")
            expected_num = _to_number(expected)
            if expected_num is None:
                raise ValueError(f"Filter {op} requires numeric values for column: {column}")
            if op in ("gt", ">"):
                current = actual_num.gt(expected_num)
            elif op in ("gte", ">="):
                current = actual_num.ge(expected_num)
            elif op in ("lt", "<"):
                current = actual_num.lt(expected_num)
            elif op in ("lte", "<="):
                current = actual_num.le(expected_num)
            else:
                raise ValueError(f"Unsupported filter op: {op}")
            current = current.fillna(False)

        mask &= current.fillna(False)
    return frame.loc[mask]


def _metric_value(frame: Any, metric: str, column: str | None = None) -> Any:
    if metric == "count":
        return int(len(frame))
    if not column:
        raise ValueError(f"metric {metric} requires column.")

    nums = _numeric_series(_filter_series(frame, column)).dropna()
    if metric == "sum":
        return float(nums.sum()) if not nums.empty else 0
    if metric == "mean":
        return float(nums.mean()) if not nums.empty else None
    if metric == "max":
        return float(nums.max()) if not nums.empty else None
    if metric == "min":
        return float(nums.min()) if not nums.empty else None
    raise ValueError(f"Unsupported metric: {metric}")


def query_table(
    csv_path: str | Path,
    metric: str,
    column: str | None = None,
    filters: Any = None,
    sheet_name: str | None = None,
    header_rows: int = 1,
    fill_merged_cells: bool = False,
) -> dict[str, Any]:
    frame, _metadata = read_table_frame(
        csv_path,
        sheet_name=sheet_name,
        header_rows=header_rows,
        fill_merged_cells=fill_merged_cells,
    )
    normalized_filters = _normalize_filters(filters)
    matched = _apply_filters(frame, normalized_filters)
    value = _metric_value(matched, metric, column)

    return {
        "value": value,
        "metric": metric,
        "column": column,
        "matched_row_count": int(len(matched)),
        "total_row_count": int(len(frame)),
        "filters": normalized_filters,
        "basis": {
            "operation": metric,
            "target_column": column,
            "filter_count": len(normalized_filters),
        },
    }


def _table_spec_path(spec: dict[str, Any]) -> str:
    return spec.get("path") or spec.get("csv_path") or spec.get("table_path")


def _read_named_table_frame(spec: dict[str, Any]) -> tuple[str, Any]:
    name = spec["name"]
    path = _table_spec_path(spec)
    if not path:
        raise ValueError(f"Table spec {name} must include path.")
    frame, _metadata = read_table_frame(
        path,
        sheet_name=spec.get("sheet_name"),
        header_rows=int(spec.get("header_rows", 1)),
        fill_merged_cells=bool(spec.get("fill_merged_cells", False)),
    )
    return name, frame


def _read_named_table(spec: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    name, frame = _read_named_table_frame(spec)
    return name, _frame_to_rows(frame)


def query_multi_table(
    tables: list[dict[str, Any]],
    join: dict[str, Any],
    metric: str,
    column: str | None = None,
    filters: Any = None,
) -> dict[str, Any]:
    if len(tables) != 2:
        raise ValueError("query_multi_table currently supports exactly two tables.")

    left_name, left = _read_named_table_frame(tables[0])
    right_name, right = _read_named_table_frame(tables[1])
    left_key = join["left_key"]
    right_key = join["right_key"]
    left_join_key = f"{left_name}.{left_key}"
    right_join_key = f"{right_name}.{right_key}"

    left_prefixed = left.add_prefix(f"{left_name}.")
    right_prefixed = right.add_prefix(f"{right_name}.")
    joined = left_prefixed.merge(
        right_prefixed,
        left_on=left_join_key,
        right_on=right_join_key,
        how="inner",
    )

    normalized_filters = _normalize_filters(filters)
    matched = _apply_filters(joined, normalized_filters)
    value = _metric_value(matched, metric, column)

    return {
        "value": value,
        "metric": metric,
        "column": column,
        "matched_row_count": int(len(matched)),
        "joined_row_count": int(len(joined)),
        "filters": normalized_filters,
        "basis": {
            "operation": metric,
            "target_column": column,
            "filter_count": len(normalized_filters),
            "join": {
                "left_table": left_name,
                "right_table": right_name,
                "left_key": left_key,
                "right_key": right_key,
            },
        },
    }
