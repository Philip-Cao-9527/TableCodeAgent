"""真实 API benchmark 入口。非 API 项目代码测试位于 tests/。"""


def run_real_api_benchmark(*args, **kwargs):
    from .benchmark_runner import run_real_api_benchmark as _run_real_api_benchmark

    return _run_real_api_benchmark(*args, **kwargs)

__all__ = ["run_real_api_benchmark"]
