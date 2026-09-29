#!/usr/bin/env python3
"""
Entry point for the API Load Tester command-line interface.

    python load_test.py https://your-api.com --concurrency 100 --requests 100

Run with no arguments for an interactive prompt, or --gui to open the app.
"""
import sys

from loadtester.cli import main

if __name__ == "__main__":
    sys.exit(main())
