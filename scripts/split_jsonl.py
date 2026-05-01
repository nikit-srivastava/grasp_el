#!/usr/bin/env python3
"""Split a JSONL file into N roughly equal chunks.

Usage:
  python scripts/split_jsonl.py data/questions.jsonl data/chunks/ 100
  # → produces data/chunks/chunk_0000.jsonl … chunk_0099.jsonl

With --shuffle, records are randomly permuted before splitting.
"""

import argparse
import json
import os
import random
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Split a JSONL file into N chunks.")
    parser.add_argument("input", help="Input JSONL file")
    parser.add_argument("output_dir", help="Directory to write chunk files into")
    parser.add_argument("n_chunks", type=int, help="Number of chunks to produce")
    parser.add_argument(
        "--shuffle",
        action="store_true",
        help="Randomly shuffle records before splitting",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for --shuffle (default: 42)",
    )
    parser.add_argument(
        "--prefix",
        default="chunk",
        help="Output filename prefix (default: chunk)",
    )
    args = parser.parse_args()

    # Read all records
    with open(args.input) as f:
        records = [json.loads(line) for line in f if line.strip()]

    total = len(records)
    if total == 0:
        print("Input file is empty.", file=sys.stderr)
        sys.exit(1)

    if args.shuffle:
        random.seed(args.seed)
        random.shuffle(records)

    # Split
    os.makedirs(args.output_dir, exist_ok=True)
    chunk_size = (total + args.n_chunks - 1) // args.n_chunks  # ceiling division
    num = len(f"{args.n_chunks}")

    written = 0
    for i in range(args.n_chunks):
        start = i * chunk_size
        end = min(start + chunk_size, total)
        if start >= total:
            break

        fname = f"{args.prefix}_{i:0{num}d}.jsonl"
        fpath = os.path.join(args.output_dir, fname)
        with open(fpath, "w") as out:
            for rec in records[start:end]:
                out.write(json.dumps(rec) + "\n")
        written += end - start
        print(f"  {fname}: {end - start} records", file=sys.stderr)

    print(
        f"Split {total} records into {i + 1} chunk(s) under {args.output_dir}/",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
