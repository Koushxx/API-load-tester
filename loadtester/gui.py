"""
Desktop GUI for the API Load Tester (Tkinter, standard library only).

Features for testing teams:
- Full request form (URL, method, concurrency, requests, headers, body, timeout).
- Live progress bar and request counter while the test runs.
- Run in a background thread with a Stop button (UI stays responsive).
- Response-time statistics with a colored PASS/FAIL verdict vs. a threshold.
- Status-code breakdown and error summary.
- Save / load test configurations as JSON profiles (share with the team).
- Export the results report as JSON, CSV, or plain text.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from tkinter import (
    BOTH,
    DISABLED,
    END,
    LEFT,
    NORMAL,
    RIGHT,
    W,
    X,
    Y,
    BooleanVar,
    StringVar,
    Tk,
    filedialog,
    messagebox,
)
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from .core import LoadTestConfig, LoadTestReport, parse_headers, run_load_test

HTTP_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


class LoadTesterApp:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title("API Load Tester")
        self.root.geometry("880x760")
        self.root.minsize(760, 640)

        self._worker: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_report: LoadTestReport | None = None

        self._build_widgets()

    # ------------------------------------------------------------------ UI
    def _build_widgets(self):
        style = ttk.Style()
        try:
            style.theme_use("vista")
        except Exception:  # noqa: BLE001 - theme may not exist on all platforms
            pass

        container = ttk.Frame(self.root, padding=12)
        container.pack(fill=BOTH, expand=True)

        # --- Request settings ---------------------------------------------
        req = ttk.LabelFrame(container, text="Request settings", padding=10)
        req.pack(fill=X)

        # URL + method
        row = ttk.Frame(req)
        row.pack(fill=X, pady=3)
        ttk.Label(row, text="URL:", width=12).pack(side=LEFT)
        self.url_var = StringVar()
        ttk.Entry(row, textvariable=self.url_var).pack(side=LEFT, fill=X, expand=True)

        row = ttk.Frame(req)
        row.pack(fill=X, pady=3)
        ttk.Label(row, text="Method:", width=12).pack(side=LEFT)
        self.method_var = StringVar(value="POST")
        ttk.Combobox(
            row, textvariable=self.method_var, values=HTTP_METHODS,
            state="readonly", width=12,
        ).pack(side=LEFT)

        # Numeric settings
        grid = ttk.Frame(req)
        grid.pack(fill=X, pady=3)
        self.requests_var = StringVar(value="100")
        self.concurrency_var = StringVar(value="100")
        self.timeout_var = StringVar(value="30")
        self.threshold_var = StringVar(value="2000")

        self._labeled_entry(grid, "Total requests:", self.requests_var, 0)
        self._labeled_entry(grid, "Concurrency:", self.concurrency_var, 1)
        self._labeled_entry(grid, "Timeout (s):", self.timeout_var, 2)
        self._labeled_entry(grid, "Threshold (ms):", self.threshold_var, 3)

        self.verify_ssl_var = BooleanVar(value=True)
        ttk.Checkbutton(
            req, text="Verify SSL certificate (uncheck for self-signed certs)",
            variable=self.verify_ssl_var,
        ).pack(anchor=W, pady=(4, 0))

        # Headers + body side by side
        panes = ttk.Frame(container)
        panes.pack(fill=BOTH, expand=True, pady=(8, 0))

        headers_frame = ttk.LabelFrame(panes, text="Headers (one per line: Key: Value)", padding=6)
        headers_frame.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 4))
        self.headers_text = ScrolledText(headers_frame, height=6, width=30, wrap="none")
        self.headers_text.pack(fill=BOTH, expand=True)
        self.headers_text.insert(END, "Content-Type: application/json")

        body_frame = ttk.LabelFrame(panes, text="Request body", padding=6)
        body_frame.pack(side=LEFT, fill=BOTH, expand=True, padx=(4, 0))
        self.body_text = ScrolledText(body_frame, height=6, width=30, wrap="none")
        self.body_text.pack(fill=BOTH, expand=True)
        self.body_text.insert(END, '{\n  "name": "test"\n}')

        # --- Controls ------------------------------------------------------
        controls = ttk.Frame(container)
        controls.pack(fill=X, pady=8)

        self.run_btn = ttk.Button(controls, text="▶  Run test", command=self.on_run)
        self.run_btn.pack(side=LEFT)
        self.stop_btn = ttk.Button(controls, text="■  Stop", command=self.on_stop, state=DISABLED)
        self.stop_btn.pack(side=LEFT, padx=(6, 0))

        ttk.Button(controls, text="Save config…", command=self.on_save_config).pack(side=RIGHT)
        ttk.Button(controls, text="Load config…", command=self.on_load_config).pack(side=RIGHT, padx=(0, 6))
        ttk.Button(controls, text="Export report…", command=self.on_export).pack(side=RIGHT, padx=(0, 6))

        # --- Progress ------------------------------------------------------
        prog = ttk.Frame(container)
        prog.pack(fill=X)
        self.progress = ttk.Progressbar(prog, mode="determinate")
        self.progress.pack(side=LEFT, fill=X, expand=True)
        self.progress_label = ttk.Label(prog, text="0 / 0", width=16, anchor="e")
        self.progress_label.pack(side=RIGHT, padx=(6, 0))

        # --- Verdict banner ------------------------------------------------
        self.verdict_var = StringVar(value="Ready.")
        self.verdict_label = ttk.Label(
            container, textvariable=self.verdict_var, anchor="center",
            font=("Segoe UI", 11, "bold"), padding=6,
        )
        self.verdict_label.pack(fill=X, pady=(8, 4))

        # --- Results -------------------------------------------------------
        results_frame = ttk.LabelFrame(container, text="Results", padding=6)
        results_frame.pack(fill=BOTH, expand=True)
        self.results_text = ScrolledText(results_frame, height=12, state=DISABLED, wrap="word")
        self.results_text.pack(fill=BOTH, expand=True)

    def _labeled_entry(self, parent, label, var, col):
        cell = ttk.Frame(parent)
        cell.grid(row=0, column=col, padx=4, sticky=W)
        ttk.Label(cell, text=label).pack(anchor=W)
        ttk.Entry(cell, textvariable=var, width=12).pack()

    # ------------------------------------------------------------- helpers
    def _collect_config(self) -> LoadTestConfig:
        url = self.url_var.get().strip()
        if not url:
            raise ValueError("Please enter a target URL.")
        if not (url.lower().startswith("http://") or url.lower().startswith("https://")):
            raise ValueError("URL must start with http:// or https://")

        try:
            requests_n = int(self.requests_var.get())
            concurrency = int(self.concurrency_var.get())
            timeout = float(self.timeout_var.get())
        except ValueError:
            raise ValueError("Requests, concurrency, and timeout must be numbers.")

        if requests_n < 1 or concurrency < 1:
            raise ValueError("Requests and concurrency must be at least 1.")

        threshold_raw = self.threshold_var.get().strip()
        threshold = float(threshold_raw) if threshold_raw else None

        headers = parse_headers(self.headers_text.get("1.0", END).splitlines())
        body = self.body_text.get("1.0", END).strip() or None

        return LoadTestConfig(
            url=url,
            method=self.method_var.get(),
            concurrency=concurrency,
            requests=requests_n,
            body=body,
            headers=headers,
            timeout=timeout,
            verify_ssl=self.verify_ssl_var.get(),
            threshold_ms=threshold,
        )

    def _set_running(self, running: bool):
        self.run_btn.config(state=DISABLED if running else NORMAL)
        self.stop_btn.config(state=NORMAL if running else DISABLED)

    def _write_results(self, text: str):
        self.results_text.config(state=NORMAL)
        self.results_text.delete("1.0", END)
        self.results_text.insert(END, text)
        self.results_text.config(state=DISABLED)

    # -------------------------------------------------------------- actions
    def on_run(self):
        try:
            config = self._collect_config()
        except ValueError as exc:
            messagebox.showerror("Invalid input", str(exc))
            return

        self._stop_event.clear()
        self._set_running(True)
        self.progress.config(value=0, maximum=config.requests)
        self.progress_label.config(text=f"0 / {config.requests}")
        self.verdict_var.set("Running…")
        self.verdict_label.config(background="", foreground="")
        self._write_results("Test in progress…\n")

        self._worker = threading.Thread(target=self._run_worker, args=(config,), daemon=True)
        self._worker.start()

    def _run_worker(self, config: LoadTestConfig):
        def progress(done, total):
            self.root.after(0, self._on_progress, done, total)

        try:
            report = run_load_test(config, progress_callback=progress, stop_event=self._stop_event)
        except Exception as exc:  # noqa: BLE001
            self.root.after(0, self._on_error, str(exc))
            return
        self.root.after(0, self._on_done, report)

    def _on_progress(self, done, total):
        self.progress.config(value=done)
        self.progress_label.config(text=f"{done} / {total}")

    def _on_error(self, message: str):
        self._set_running(False)
        self.verdict_var.set("Error")
        self.verdict_label.config(background="#c0392b", foreground="white")
        self._write_results(f"Error: {message}")

    def _on_done(self, report: LoadTestReport):
        self._set_running(False)
        self._last_report = report
        self._write_results(self._format_report(report))

        stopped = self._stop_event.is_set()
        verdict = report.passed
        if stopped:
            self.verdict_var.set("STOPPED (partial results)")
            self.verdict_label.config(background="#7f8c8d", foreground="white")
        elif verdict is True:
            self.verdict_var.set("RESULT: PASS")
            self.verdict_label.config(background="#27ae60", foreground="white")
        elif verdict is False:
            self.verdict_var.set("RESULT: FAIL")
            self.verdict_label.config(background="#c0392b", foreground="white")
        else:
            self.verdict_var.set("Done (no threshold set)")
            self.verdict_label.config(background="#2c3e50", foreground="white")

    def on_stop(self):
        self._stop_event.set()
        self.verdict_var.set("Stopping…")

    def _format_report(self, report: LoadTestReport) -> str:
        c = report.config
        lines = []
        lines.append(f"Target        : {c.method} {c.url}")
        lines.append(f"Total requests: {c.requests}")
        lines.append(f"Concurrency   : {c.concurrency}")
        if c.threshold_ms is not None:
            lines.append(f"Threshold     : {c.threshold_ms:.0f} ms")
        lines.append("-" * 56)
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
        lines.append("-" * 56)
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

    # ----------------------------------------------------------- config I/O
    def on_save_config(self):
        try:
            config = self._collect_config()
        except ValueError as exc:
            messagebox.showerror("Invalid input", str(exc))
            return
        path = filedialog.asksaveasfilename(
            title="Save test configuration",
            defaultextension=".json",
            filetypes=[("JSON config", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        data = {
            "url": config.url,
            "method": config.method,
            "requests": config.requests,
            "concurrency": config.concurrency,
            "timeout": config.timeout,
            "threshold_ms": config.threshold_ms,
            "verify_ssl": config.verify_ssl,
            "headers": config.headers,
            "body": config.body,
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        messagebox.showinfo("Saved", f"Configuration saved to:\n{path}")

    def on_load_config(self):
        path = filedialog.askopenfilename(
            title="Load test configuration",
            filetypes=[("JSON config", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            messagebox.showerror("Load failed", str(exc))
            return

        self.url_var.set(data.get("url", ""))
        self.method_var.set(data.get("method", "POST"))
        self.requests_var.set(str(data.get("requests", 100)))
        self.concurrency_var.set(str(data.get("concurrency", 100)))
        self.timeout_var.set(str(data.get("timeout", 30)))
        threshold = data.get("threshold_ms")
        self.threshold_var.set("" if threshold is None else str(threshold))
        self.verify_ssl_var.set(bool(data.get("verify_ssl", True)))

        self.headers_text.delete("1.0", END)
        headers = data.get("headers", {})
        self.headers_text.insert(END, "\n".join(f"{k}: {v}" for k, v in headers.items()))

        self.body_text.delete("1.0", END)
        self.body_text.insert(END, data.get("body") or "")

    # -------------------------------------------------------------- export
    def on_export(self):
        if self._last_report is None:
            messagebox.showinfo("Nothing to export", "Run a test first.")
            return
        path = filedialog.asksaveasfilename(
            title="Export report",
            defaultextension=".json",
            filetypes=[
                ("JSON report", "*.json"),
                ("CSV summary", "*.csv"),
                ("Text report", "*.txt"),
            ],
        )
        if not path:
            return
        report = self._last_report
        lower = path.lower()
        try:
            if lower.endswith(".csv"):
                self._export_csv(path, report)
            elif lower.endswith(".txt"):
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(self._format_report(report))
            else:
                self._export_json(path, report)
        except OSError as exc:
            messagebox.showerror("Export failed", str(exc))
            return
        messagebox.showinfo("Exported", f"Report saved to:\n{path}")

    def _report_dict(self, report: LoadTestReport) -> dict:
        c = report.config
        return {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "target": {"method": c.method, "url": c.url},
            "requests": c.requests,
            "concurrency": c.concurrency,
            "threshold_ms": c.threshold_ms,
            "total_seconds": round(report.total_wall_seconds, 3),
            "throughput_rps": round(report.throughput, 2),
            "success": report.success,
            "failed": report.failed,
            "status_codes": report.status_counts,
            "errors": report.errors,
            "response_time_ms": {
                "min": round(report.min_ms, 1),
                "avg": round(report.avg_ms, 1),
                "median": round(report.median_ms, 1),
                "p90": round(report.percentile(90), 1),
                "p95": round(report.percentile(95), 1),
                "p99": round(report.percentile(99), 1),
                "max": round(report.max_ms, 1),
            },
            "verdict": (
                "PASS" if report.passed is True
                else "FAIL" if report.passed is False
                else "N/A"
            ),
        }

    def _export_json(self, path, report):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self._report_dict(report), fh, indent=2)

    def _export_csv(self, path, report):
        import csv

        d = self._report_dict(report)
        rt = d["response_time_ms"]
        with open(path, "w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow([
                "timestamp", "method", "url", "requests", "concurrency",
                "threshold_ms", "total_seconds", "throughput_rps",
                "success", "failed", "min_ms", "avg_ms", "median_ms",
                "p90_ms", "p95_ms", "p99_ms", "max_ms", "verdict",
            ])
            writer.writerow([
                d["timestamp"], d["target"]["method"], d["target"]["url"],
                d["requests"], d["concurrency"], d["threshold_ms"],
                d["total_seconds"], d["throughput_rps"], d["success"],
                d["failed"], rt["min"], rt["avg"], rt["median"],
                rt["p90"], rt["p95"], rt["p99"], rt["max"], d["verdict"],
            ])


def main():
    root = Tk()
    LoadTesterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
