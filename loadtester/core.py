"""
Core load-testing engine.

Framework-agnostic logic shared by the CLI and GUI front-ends. Sends
concurrent HTTP requests to a target endpoint and aggregates response-time
statistics. Uses only the Python standard library.
"""
from __future__ import annotations

import ssl
import statistics
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


@dataclass
class LoadTestConfig:
    """All settings needed to run a load test."""

    url: str
    method: str = "POST"
    concurrency: int = 100
    requests: int = 100
    body: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    timeout: float = 30.0
    verify_ssl: bool = True
    threshold_ms: Optional[float] = None


@dataclass
class RequestResult:
    """Outcome of a single request."""

    elapsed_ms: float
    status: Optional[int]
    error: Optional[str]


@dataclass
class LoadTestReport:
    """Aggregated results across all requests."""

    config: LoadTestConfig
    total_wall_seconds: float
    latencies_ms: List[float]
    status_counts: Dict[int, int]
    errors: Dict[str, int]
    success: int
    failed: int

    @property
    def throughput(self) -> float:
        if self.total_wall_seconds <= 0:
            return 0.0
        return self.config.requests / self.total_wall_seconds

    @property
    def min_ms(self) -> float:
        return min(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def max_ms(self) -> float:
        return max(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def avg_ms(self) -> float:
        return statistics.mean(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def median_ms(self) -> float:
        return statistics.median(self.latencies_ms) if self.latencies_ms else 0.0

    def percentile(self, pct: float) -> float:
        return percentile(sorted(self.latencies_ms), pct)

    @property
    def passed(self) -> Optional[bool]:
        """PASS/FAIL verdict if a threshold was set, else None."""
        if self.config.threshold_ms is None or not self.latencies_ms:
            return None
        return self.max_ms <= self.config.threshold_ms and self.failed == 0


def percentile(sorted_values: List[float], pct: float) -> float:
    """Return the pct-th percentile (0-100) using the nearest-rank method."""
    if not sorted_values:
        return 0.0
    rank = max(1, int(round(pct / 100.0 * len(sorted_values))))
    return sorted_values[min(rank, len(sorted_values)) - 1]


def parse_headers(header_lines: List[str]) -> Dict[str, str]:
    """Convert ['Key: Value', ...] lines into a dict."""
    headers: Dict[str, str] = {}
    for item in header_lines or []:
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            raise ValueError(f"Invalid header (expected 'Key: Value'): {item!r}")
        key, value = item.split(":", 1)
        headers[key.strip()] = value.strip()
    return headers


def _send_one(config: LoadTestConfig, body_bytes: Optional[bytes]) -> RequestResult:
    """Send a single request and time it."""
    context = None
    if config.url.lower().startswith("https") and not config.verify_ssl:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(url=config.url, data=body_bytes, method=config.method.upper())
    for key, value in config.headers.items():
        req.add_header(key, value)

    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=config.timeout, context=context) as resp:
            resp.read()
            elapsed = (time.perf_counter() - start) * 1000.0
            return RequestResult(elapsed, resp.status, None)
    except urllib.error.HTTPError as exc:
        elapsed = (time.perf_counter() - start) * 1000.0
        return RequestResult(elapsed, exc.code, None)
    except Exception as exc:  # noqa: BLE001 - report any transport error
        elapsed = (time.perf_counter() - start) * 1000.0
        return RequestResult(elapsed, None, str(exc))


def run_load_test(
    config: LoadTestConfig,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    stop_event: Optional[threading.Event] = None,
) -> LoadTestReport:
    """
    Execute the load test.

    Args:
        config: Test settings.
        progress_callback: Optional fn(completed, total) called as requests finish.
        stop_event: Optional threading.Event; if set, remaining requests are skipped.
    """
    body_bytes = config.body.encode("utf-8") if config.body else None

    results: List[RequestResult] = []
    overall_start = time.perf_counter()
    completed = 0

    with ThreadPoolExecutor(max_workers=config.concurrency) as executor:
        futures = [
            executor.submit(_send_one, config, body_bytes)
            for _ in range(config.requests)
        ]
        for future in as_completed(futures):
            if stop_event is not None and stop_event.is_set():
                # Cancel any not-yet-started work and stop collecting.
                for f in futures:
                    f.cancel()
                break
            results.append(future.result())
            completed += 1
            if progress_callback is not None:
                progress_callback(completed, config.requests)

    total_wall = time.perf_counter() - overall_start

    latencies_ms: List[float] = []
    status_counts: Dict[int, int] = {}
    errors: Dict[str, int] = {}
    success = 0
    failed = 0

    for result in results:
        if result.error is not None:
            failed += 1
            errors[result.error] = errors.get(result.error, 0) + 1
            continue
        latencies_ms.append(result.elapsed_ms)
        if result.status is not None:
            status_counts[result.status] = status_counts.get(result.status, 0) + 1
        if result.status is not None and result.status < 400:
            success += 1
        else:
            failed += 1

    return LoadTestReport(
        config=config,
        total_wall_seconds=total_wall,
        latencies_ms=latencies_ms,
        status_counts=status_counts,
        errors=errors,
        success=success,
        failed=failed,
    )
