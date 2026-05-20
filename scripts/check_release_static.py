#!/usr/bin/env python3
"""Fail a release when packaged static UI still contains stale primary labels."""

from __future__ import annotations

from pathlib import Path
import sys


STATIC_DIR = Path("switchboard/static/app")
STALE_TERMS = [
    "Projects & Environments",
    "Add Project Group",
    "Use Add Service to seed this workspace manually.",
    "Run All Health Checks",
    "Run all health checks",
]


def main() -> int:
    if not STATIC_DIR.exists():
        print(f"missing packaged static app: {STATIC_DIR}", file=sys.stderr)
        return 1

    failures: list[str] = []
    for path in STATIC_DIR.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for term in STALE_TERMS:
            if term in text:
                failures.append(f"{path}: contains {term!r}")

    if failures:
        print("stale packaged UI labels found:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("packaged static UI label gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
