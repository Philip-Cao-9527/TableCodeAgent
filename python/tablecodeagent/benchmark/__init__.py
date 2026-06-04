"""Benchmark runner for TableCodeAgent tasks."""


def run_benchmark(*args, **kwargs):
    from .runner import run_benchmark as _run_benchmark

    return _run_benchmark(*args, **kwargs)

__all__ = ["run_benchmark"]
