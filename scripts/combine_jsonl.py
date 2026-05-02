#!/usr/bin/env python3
"""Combine multiple JSONL files into a single file.

Usage:
  python scripts/combine_jsonl.py data/chunks/chunk_*.jsonl data/combined.jsonl
  python scripts/combine_jsonl.py data/chunks/ data/combined.jsonl   # all .jsonl in dir

With --shuffle, records are randomly permuted before writing.
"""

import argparse
import glob
import json
import os
import random
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Combine multiple JSONL files.")
    parser.add_argument("inputs", nargs="+", help="Input JSONL files or directories")
    parser.add_argument("output", help="Output JSONL file")
    parser.add_argument(
        "--shuffle",
        action="store_true",
        help="Randomly shuffle records before writing",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for --shuffle (default: 42)",
    )
    args = parser.parse_args()

    # Resolve inputs: expand directories and glob patterns
    paths = []
    for inp in args.inputs:
        if os.path.isdir(inp):
            paths.extend(sorted(glob.glob(os.path.join(inp, "*.jsonl"))))
        else:
            paths.extend(glob.glob(inp))

    if not paths:
        print("No input files found.", file=sys.stderr)
        sys.exit(1)

    # Read all records
    records = []
    for path in paths:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        print(f"  {os.path.basename(path)}: {len(records)} records so far", file=sys.stderr)

    total = len(records)
    if total == 0:
        print("No records found in input files.", file=sys.stderr)
        sys.exit(1)

    if args.shuffle:
        random.seed(args.seed)
        random.shuffle(records)

    # Write combined output
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w") as out:
        for rec in records:
            out.write(json.dumps(rec) + "\n")

    print(f"Combined {len(paths)} file(s) into {total} records → {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
