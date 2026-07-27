#!/usr/bin/env python3
"""Unified host entry point for the Blender MCP Docker test suites.

Works from Windows, WSL, and Linux. Calls docker compose internally.

Usage:
    python scripts/run_blender_mcp_docker_tests.py --suite full --rebuild
    python scripts/run_blender_mcp_docker_tests.py --suite unit
    python scripts/run_blender_mcp_docker_tests.py --suite blender-integration
    python scripts/run_blender_mcp_docker_tests.py --suite e2e
    python scripts/run_blender_mcp_docker_tests.py --suite acceptance
    python scripts/run_blender_mcp_docker_tests.py --suite gpu   # optional

The mandatory full suite must pass without a GPU and without external credentials.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = REPO_ROOT / "docker-compose.mcp-test.yml"
ARTIFACTS = REPO_ROOT / "artifacts" / "docker-tests"

# Mandatory suites (run by --suite full in order).
MANDATORY_SUITES = [
    "test-unit",
    "test-blender-integration",
    "test-e2e",
    "test-render",
    "test-vision",
    "test-asset",
    "test-failure",
    "test-acceptance",
    "test-soak",
]

OPTIONAL_SUITES = ["test-gpu"]

SUITE_ALIASES = {
    "unit": ["test-unit"],
    "blender-integration": ["test-blender-integration"],
    "e2e": ["test-e2e"],
    "render": ["test-render"],
    "vision": ["test-vision"],
    "asset": ["test-asset"],
    "failure": ["test-failure"],
    "acceptance": ["test-acceptance"],
    "soak": ["test-soak"],
    "gpu": ["test-gpu"],
    "full": MANDATORY_SUITES,
}


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print(">>>", " ".join(cmd), flush=True)
    return subprocess.run(cmd, **kwargs)


def compose(*args: str, rebuild: bool = False) -> int:
    cmd = ["docker", "compose", "-f", str(COMPOSE_FILE)]
    if rebuild:
        cmd += ["build", "--pull"]
        return run(cmd).returncode
    cmd += list(args)
    return run(cmd).returncode


def run_suite(service: str) -> dict:
    print(f"\n=== Running suite: {service} ===", flush=True)
    started = time.time()
    proc = run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "run", "--rm", service],
    )
    duration = time.time() - started
    return {
        "suite": service,
        "exit_code": proc.returncode,
        "duration_s": round(duration, 2),
        "passed": proc.returncode == 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite",
        default="full",
        choices=list(SUITE_ALIASES.keys()),
        help="Which suite to run.",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Rebuild the image before running.",
    )
    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Skip docker compose down at the end (useful when iterating).",
    )
    args = parser.parse_args(argv)

    if not shutil.which("docker"):
        print("ERROR: docker is not installed or not on PATH.", file=sys.stderr)
        return 127

    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    if args.rebuild:
        rc = compose("build", "--pull", rebuild=True)
        if rc != 0:
            print("ERROR: image build failed.", file=sys.stderr)
            return rc

    services = SUITE_ALIASES[args.suite]
    results = []
    overall_rc = 0
    for svc in services:
        result = run_suite(svc)
        results.append(result)
        if not result["passed"]:
            overall_rc = 1
            # Continue running the rest so we get full evidence, but mark failure.

    # Write machine-readable status.
    status = {
        "suite_alias": args.suite,
        "services": results,
        "overall_passed": overall_rc == 0,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    status_path = ARTIFACTS / "latest" / "status.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(f"\nStatus written to {status_path}", flush=True)
    print(json.dumps(status, indent=2), flush=True)

    if not args.no_cleanup:
        print("\n=== Cleaning up ===", flush=True)
        run(["docker", "compose", "-f", str(COMPOSE_FILE), "down", "-v", "--remove-orphans"])

    return overall_rc


if __name__ == "__main__":
    raise SystemExit(main())
