"""Command-line entry point for Phase 1 dataset generation."""

from __future__ import annotations

import argparse
from pathlib import Path

from .generator import SCENARIOS, generate_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Pygenic Arc synthetic evidence")
    parser.add_argument("--scenario", choices=SCENARIOS, default="BAD_DEPLOY")
    parser.add_argument("--severity", choices=("low", "high"), default="high")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output", default=str(Path(__file__).parents[2] / "data"))
    args = parser.parse_args()
    truth = generate_dataset(args.output, args.scenario, args.severity, args.seed)
    print(f"Generated {args.scenario} ({args.severity}) at {args.output}")
    print(f"Ground truth: {truth.root_cause}; noisy signal: {truth.noisy_signal}")


if __name__ == "__main__":
    main()
