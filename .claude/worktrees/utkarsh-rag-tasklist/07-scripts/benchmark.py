"""Run EchoQuery contract, latency, and end-to-end benchmark commands."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("contracts", help="validate contract examples")
    latency = subparsers.add_parser("latency", help="aggregate latency samples")
    latency.add_argument("--input", type=Path, required=True, help="JSON list of milliseconds")
    latency.add_argument("--output", type=Path)
    end_to_end = subparsers.add_parser("end-to-end", help="benchmark an indexed fixture pipeline")
    end_to_end.add_argument("--queries", type=Path, required=True)
    end_to_end.add_argument("--index", type=Path, required=True)
    end_to_end.add_argument("--answer", default="Fixture answer; replace with the configured model in production.")
    end_to_end.add_argument("--fetch-k", type=int, default=20)
    end_to_end.add_argument("--relevance-floor", type=float, default=0.0)
    end_to_end.add_argument("--output", type=Path)
    args, remaining = parser.parse_known_args(argv)
    if args.command == "contracts":
        return _load("validate_contracts", ROOT / "07-scripts" / "validate_contracts.py").main([])
    if args.command == "latency":
        module = _load("latency_metrics", ROOT / "06-evaluation" / "metrics" / "latency.py")
        report = module.percentile_report(json.loads(args.input.read_text(encoding="utf-8")))
        serialized = json.dumps(report, indent=2, sort_keys=True)
        if args.output:
            args.output.write_text(serialized + "\n", encoding="utf-8")
        print(serialized)
        return 0
    module = _load("end_to_end_benchmark", ROOT / "06-evaluation" / "benchmarks" / "end_to_end.py")
    forwarded = ["--queries", str(args.queries), "--index", str(args.index), "--answer", args.answer, "--fetch-k", str(args.fetch_k), "--relevance-floor", str(args.relevance_floor)]
    if args.output:
        forwarded.extend(["--output", str(args.output)])
    return module.main(forwarded + remaining)


if __name__ == "__main__":
    raise SystemExit(main())
