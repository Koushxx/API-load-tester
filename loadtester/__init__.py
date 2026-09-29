"""API Load Tester - a dependency-free tool to load-test HTTP APIs."""

__version__ = "1.0.0"

from .core import (
    LoadTestConfig,
    LoadTestReport,
    RequestResult,
    parse_headers,
    percentile,
    run_load_test,
)

__all__ = [
    "LoadTestConfig",
    "LoadTestReport",
    "RequestResult",
    "parse_headers",
    "percentile",
    "run_load_test",
    "__version__",
]
