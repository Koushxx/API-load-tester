# API Load Tester

A lightweight, **dependency-free** tool for load-testing HTTP APIs. It fires
many concurrent requests at an endpoint and reports response-time statistics
so testing teams can verify performance under load.

It ships in two forms:

- **Desktop GUI** — a friendly window for entering settings and viewing results.
- **Command-line / interactive tool** — great for scripts and CI pipelines.

Built entirely on the Python standard library — no `pip install` needed to run.

Designed for test cases like:

> **41076 - Response time under high load**
> Precondition: Load generation tool available.
> Send 100 concurrent POST requests.
> Expected: System responds within acceptable response time.

---

## Features

- Configure URL, HTTP method, total requests, and concurrency.
- Custom headers and request body.
- Per-request timeout and optional TLS verification toggle (self-signed certs).
- **Live progress bar** and request counter (GUI).
- **Run in background with a Stop button** — the GUI stays responsive.
- Response-time stats: min / avg / median / **p90 / p95 / p99** / max.
- Throughput (requests per second) and status-code breakdown.
- **PASS/FAIL verdict** against an acceptable response-time threshold.
- **Save / load test configurations** as JSON — share presets across the team.
- **Export reports** to JSON, CSV, or plain text.

---

## Quick start (no build needed)

Requires Python 3.8+.

```powershell
# Desktop GUI
python load_test_gui.py

# Command line
python load_test.py https://your-api.com/endpoint --concurrency 100 --requests 100 --threshold-ms 2000

# Interactive prompt
python load_test.py
```

---

## Command-line usage

```powershell
python load_test.py <URL> [options]
```

| Option | Default | Description |
| --- | --- | --- |
| `url` | (required) | Target API endpoint. |
| `-X`, `--method` | `POST` | HTTP method. |
| `-c`, `--concurrency` | `100` | Number of concurrent workers. |
| `-n`, `--requests` | `100` | Total requests to send. |
| `-d`, `--data` | none | Inline request body (e.g. JSON string). |
| `--data-file` | none | Read request body from a file. |
| `-H`, `--header` | none | `Key: Value` header (repeatable). |
| `-t`, `--timeout` | `30` | Per-request timeout (seconds). |
| `--threshold-ms` | none | Max acceptable response time for PASS/FAIL. |
| `--no-verify-ssl` | off | Skip TLS verification (self-signed certs). |
| `--gui` | — | Launch the desktop GUI instead. |

### Example: the 41076 scenario

```powershell
python load_test.py https://your-api.com/endpoint `
    --method POST `
    --concurrency 100 `
    --requests 100 `
    --data '{"name": "test"}' `
    --header "Content-Type: application/json" `
    --threshold-ms 2000
```

Exit code is `0` on PASS and `1` on FAIL, so it plugs straight into CI.

---

## Building standalone .exe files (to share with the team)

Team members without Python can run a pre-built executable.

```powershell
pip install -r requirements.txt
./build.ps1
```

This produces, in the `dist/` folder:

- `LoadTesterGUI.exe` — double-click desktop app (no console window).
- `load_test.exe` — command-line / interactive tool.

Share either `.exe`; no installation or Python required on the target machine.

---

## Understanding the results

| Field | Meaning |
| --- | --- |
| **Throughput** | Requests handled per second (higher is faster). |
| **Success (<400)** | Requests that returned a status below 400. |
| **Failed** | Requests that errored or returned a 4xx/5xx status. |
| **min / avg / median** | Fastest / average / middle response time. |
| **p90 / p95 / p99** | 90/95/99% of requests were at least this fast. |
| **max** | Slowest single response (worst case). |
| **RESULT** | PASS if the slowest response is within the threshold and nothing failed. |

> The **percentiles (p90/p95/p99)** best reflect what most users experience
> under load; `max` reveals the worst outlier.

---

## Project structure

```
load-tester/
├── loadtester/
│   ├── __init__.py      # package exports
│   ├── core.py          # load-test engine (shared logic)
│   ├── cli.py           # command-line front-end
│   └── gui.py           # Tkinter desktop UI
├── load_test.py         # CLI entry point
├── load_test_gui.py     # GUI entry point
├── build.ps1            # builds the standalone .exe files
├── requirements.txt     # build-time dependency (PyInstaller)
├── LICENSE
└── README.md
```

---

## License

Released under the [MIT License](LICENSE).
