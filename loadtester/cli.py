"""
Command-line front-end for the API Load Tester.

Sends concurrent requests to an endpoint and prints response-time statistics.
When run with no arguments (e.g. a double-clicked .exe) it switches to an
interactive prompt and keeps the window open.
"""
from __future__ import annotations

import argparse
import sys

from .core import LoadTestConfig, LoadTestReport, parse_headers, run_load_test
from . import __version__


def _format_report(report: LoadTestReport) -> str:
    c = report.config
    lines = []
    lines.append(f"Target        : {c.method} {c.url}")
    lines.append(f"Total requests: {c.requests}")
    lines.append(f"Concurrency   : {c.concurrency}")
    if c.threshold_ms is not None:
        lines.append(f"Threshold     : {c.threshold_ms:.0f} ms")
    lines.append("-" * 60)
    lines.append(f"Completed in  : {report.total_wall_seconds:.2f} s")
    lines.append(f"Throughput    : {report.throughput:.1f} req/s")
    lines.append(f"Success (<400): {report.success}")
    lines.append(f"Failed        : {report.failed}")
    if report.status_counts:
        pretty = ", ".join(f"{code}:{n}" for code, n in sorted(report.status_counts.items()))
        lines.append(f"Status codes  : {pretty}")
    if report.errors:
        lines.append("Errors        :")
        for msg, n in sorted(report.errors.items(), key=lambda kv: -kv[1]):
            lines.append(f"    {n:>4} x {msg}")
    lines.append("-" * 60)
    if report.latencies_ms:
        lines.append("Response time (ms):")
        lines.append(f"    min   : {report.min_ms:.1f}")
        lines.append(f"    avg   : {report.avg_ms:.1f}")
        lines.append(f"    median: {report.median_ms:.1f}")
        lines.append(f"    p90   : {report.percentile(90):.1f}")
        lines.append(f"    p95   : {report.percentile(95):.1f}")
        lines.append(f"    p99   : {report.percentile(99):.1f}")
        lines.append(f"    max   : {report.max_ms:.1f}")
    else:
        lines.append("No successful responses to measure.")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="load_test",
        description="Send concurrent requests to an API and report response-time stats.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("url", nargs="?", help="Target API endpoint URL.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-X", "--method", default="POST", help="HTTP method.")
    parser.add_argument("-c", "--concurrency", type=int, default=100, help="Concurrent workers.")
    parser.add_argument("-n", "--requests", type=int, default=100, help="Total requests.")
    parser.add_argument("-d", "--data", default=None, help="Inline request body.")
    parser.add_argument("--data-file", default=None, help="Read request body from a file.")
    parser.add_argument("-H", "--header", action="append", default=[], help="'Key: Value' header. Repeatable.")
    parser.add_argument("-t", "--timeout", type=float, default=30.0, help="Per-request timeout (s).")
    parser.add_argument("--threshold-ms", type=float, default=None, help="Max acceptable response time (ms).")
    parser.add_argument("--no-verify-ssl", dest="verify_ssl", action="store_false", help="Disable TLS verification.")
    parser.add_argument("--ca-cert", default=None, help="Path to a custom CA bundle (PEM) to trust the server cert.")
    parser.add_argument("--client-cert", default=None, help="Path to client certificate (PEM) for mutual TLS.")
    parser.add_argument("--client-key", default=None, help="Path to client private key (PEM). Omit if key is in --client-cert.")
    parser.add_argument("--key-password", default=None, help="Password for an encrypted client private key.")
    parser.add_argument("--gui", action="store_true", help="Launch the graphical interface.")
    parser.set_defaults(verify_ssl=True)
    return parser


def prompt_interactive() -> list[str]:
    print("=" * 60)
    print(f" API Load Tester v{__version__} - interactive mode")
    print("=" * 60)
    print("(Press Enter to accept the [default] shown in brackets.)\n")

    url = ""
    while not url.strip():
        url = input("Target API URL: ").strip()
        if not url:
            print("  A URL is required.")

    method = input("HTTP method [POST]: ").strip() or "POST"
    requests_n = input("Total requests [100]: ").strip() or "100"
    concurrency = input("Concurrency [100]: ").strip() or "100"
    data = input("Request body (JSON, optional): ").strip()
    threshold = input("Acceptable max response time in ms (optional): ").strip()

    argv = [url, "--method", method, "--requests", requests_n, "--concurrency", concurrency]
    if data:
        argv += ["--data", data]
    if threshold:
        argv += ["--threshold-ms", threshold]
    print()
    return argv


def main(argv=None) -> int:
    interactive = False
    if argv is None and len(sys.argv) == 1:
        # No arguments: assume a double-click -> interactive prompt.
        try:
            argv = prompt_interactive()
            interactive = True
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.")
            return 130

    args = build_parser().parse_args(argv)

    if args.gui:
        from .gui import main as gui_main
        gui_main()
        return 0

    if not args.url:
        build_parser().print_help()
        return 2
    if args.requests < 1 or args.concurrency < 1:
        print("--requests and --concurrency must be >= 1", file=sys.stderr)
        return 2

    body = args.data
    if args.data_file:
        try:
            with open(args.data_file, "r", encoding="utf-8") as fh:
                body = fh.read()
        except OSError as exc:
            print(f"Cannot read data file: {exc}", file=sys.stderr)
            return 2

    try:
        headers = parse_headers(args.header)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if body is not None and not any(h.lower() == "content-type" for h in headers):
        headers["Content-Type"] = "application/json"

    config = LoadTestConfig(
        url=args.url,
        method=args.method,
        concurrency=args.concurrency,
        requests=args.requests,
        body=body,
        headers=headers,
        timeout=args.timeout,
        verify_ssl=args.verify_ssl,
        threshold_ms=args.threshold_ms,
        client_cert=args.client_cert,
        client_key=args.client_key,
        client_key_password=args.key_password,
        ca_cert=args.ca_cert,
    )

    print(f"Target        : {config.method} {config.url}")
    print(f"Total requests: {config.requests}")
    print(f"Concurrency   : {config.concurrency}")
    print("-" * 60)

    report = run_load_test(config)
    print(_format_report(report))

    exit_code = 0
    if report.passed is True:
        print("-" * 60)
        print(f"RESULT: PASS (max {report.max_ms:.1f} ms <= {config.threshold_ms:.0f} ms, no failures)")
    elif report.passed is False:
        print("-" * 60)
        reasons = []
        if report.max_ms > (config.threshold_ms or 0):
            reasons.append(f"max {report.max_ms:.1f} ms > {config.threshold_ms:.0f} ms")
        if report.failed:
            reasons.append(f"{report.failed} failed requests")
        print(f"RESULT: FAIL ({'; '.join(reasons)})")
        exit_code = 1
    elif report.failed:
        exit_code = 1

    if interactive:
        try:
            input("\nPress Enter to close...")
        except (KeyboardInterrupt, EOFError):
            pass

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
