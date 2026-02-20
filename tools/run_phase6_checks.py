#!/usr/bin/env python3
"""
Run Phase 6 hardening checks in one command.
"""

import argparse
import subprocess
import sys


DEFAULT_TESTS = [
    "tests.test_overlay_server_policy",
    "tests.test_replay_overlay_trace",
]


def main():
    ap = argparse.ArgumentParser(description="Run Phase 6 checks.")
    ap.add_argument(
        "--verbose",
        action="store_true",
        help="Run unittest with verbose output",
    )
    args = ap.parse_args()

    cmd = [sys.executable, "-m", "unittest"]
    if args.verbose:
        cmd.append("-v")
    cmd.extend(DEFAULT_TESTS)

    print("PHASE6: running checks...")
    print("PHASE6: command:", " ".join(cmd))
    result = subprocess.run(cmd)
    if result.returncode == 0:
        print("PHASE6: checks passed")
    else:
        print(f"PHASE6: checks failed (exit={result.returncode})")
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())

