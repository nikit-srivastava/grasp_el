#!/usr/bin/env python3
"""Pipeline wrapper: launch llama-server, run annotation, then clean up.

Manages the full lifecycle so each SLURM job (or local run) gets its own
isolated llama-server instance on a free port.

Sample usage (local / Docker):
  python scripts/run_annotation_pipeline.py \
      data/chunk_00.jsonl data/chunk_00_annotated.jsonl \
      --sparql-endpoint http://enexa1.cs.uni-paderborn.de:9080/sparql \
      --model qwen-3.6-27b --progress

Sample usage (SLURM — set SLURM_ACTIVE=true in the job script):
  SLURM_ACTIVE=true python scripts/run_annotation_pipeline.py \
      data/chunk_00.jsonl data/chunk_00_annotated.jsonl \
      --sparql-endpoint http://enexa1.cs.uni-paderborn.de:9080/sparql \
      --model qwen-3.6-27b --progress
"""

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
_CONTROL_SCRIPT = os.path.join(_SCRIPT_DIR, "..", "llama-server", "llama_server_control.sh")
_DEFAULT_PORT = 9292


# --------------------------------------------------------------------------- #
# Port utilities
# --------------------------------------------------------------------------- #

def find_free_port(preferred: int | None = None) -> int:
    """Return an available TCP port.  Try *preferred* first, then any free."""
    if preferred:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", preferred))
                return preferred
            except OSError:
                pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_server(base_url: str, timeout: int = 300, interval: float = 3.0) -> None:
    """Block until the OpenAI-compatible /v1/models endpoint responds.

    *base_url* is the server root (e.g. http://localhost:9292), so the probe
    hits /v1/models.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(f"{base_url}/v1/models")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, OSError, ConnectionError):
            pass
        time.sleep(interval)
    raise TimeoutError(
        f"llama-server did not become ready at {base_url} within {timeout}s"
    )


# --------------------------------------------------------------------------- #
# Server lifecycle
# --------------------------------------------------------------------------- #

def start_server(port: int, slurm_active: bool) -> subprocess.Popen:
    """Start the llama-server control script in the background."""
    env = os.environ.copy()
    if slurm_active:
        env["SLURM_ACTIVE"] = "true"

    cmd = ["bash", _CONTROL_SCRIPT, "start", str(port)]
    print(f"[pipeline] Starting llama-server on port {port} …", file=sys.stderr)
    proc = subprocess.Popen(cmd, env=env, cwd=_PROJECT_ROOT)
    return proc


def stop_server(port: int, slurm_active: bool) -> None:
    """Stop the llama-server instance on *port*."""
    env = os.environ.copy()
    if slurm_active:
        env["SLURM_ACTIVE"] = "true"

    print(f"[pipeline] Stopping llama-server on port {port} …", file=sys.stderr)
    try:
        subprocess.run(
            ["bash", _CONTROL_SCRIPT, "stop", str(port)],
            env=env,
            cwd=_PROJECT_ROOT,
            check=False,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        print("[pipeline] Warning: stop timed out", file=sys.stderr)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Launch llama-server, annotate questions, then clean up.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("input", help="Input JSONL file")
    parser.add_argument("output", help="Output JSONL file")
    parser.add_argument(
        "--port",
        type=int,
        default=_DEFAULT_PORT,
        help="Host port for llama-server (0 = auto-detect free port)",
    )
    parser.add_argument(
        "--slurm-active",
        action="store_true",
        default=False,
        help="Use Apptainer/SLURM mode (also set by SLURM_ACTIVE env var)",
    )
    parser.add_argument(
        "--server-timeout",
        type=int,
        default=300,
        help="Seconds to wait for llama-server to become ready",
    )
    parser.add_argument("--no-server", action="store_true", help="Skip server management (server already running)")
    # Passthrough arguments forwarded to annotate_entities.py
    parser.add_argument("--sparql-endpoint", required=True)
    parser.add_argument("--index-dir", default=None)
    parser.add_argument("--openai-base-url", default=None)
    parser.add_argument("--openai-api-key", default=None)
    parser.add_argument("--model", default="qwen-3.6-27b")
    parser.add_argument("--field", default="question")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--progress", action="store_true")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    slurm_active = args.slurm_active or os.environ.get("SLURM_ACTIVE", "").lower() == "true"
    port = args.port

    # Resolve actual port (0 → auto-detect)
    if port == 0:
        port = find_free_port()
    else:
        # Verify the preferred port is actually free before we start
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
            except OSError:
                print(
                    f"[pipeline] Port {port} is already in use, finding free port …",
                    file=sys.stderr,
                )
                port = find_free_port(preferred=port + 1)

    # NOTE: do NOT append "/v1" here — the OpenAI Python client prepends
    # "/v1" itself, so the base URL must point at the server root.
    base_url = f"http://localhost:{port}"
    annotate_script = os.path.join(_SCRIPT_DIR, "annotate_entities.py")

    server_proc: subprocess.Popen | None = None

    # ------------------------------------------------------------------ #
    # Phase 1 — start server (unless --no-server)
    # ------------------------------------------------------------------ #
    if not args.no_server:
        server_proc = start_server(port, slurm_active)
        try:
            wait_for_server(base_url, timeout=args.server_timeout)
        except TimeoutError as exc:
            print(f"[pipeline] {exc}", file=sys.stderr)
            stop_server(port, slurm_active)
            sys.exit(1)
        print(f"[pipeline] llama-server ready at {base_url}", file=sys.stderr)

    # ------------------------------------------------------------------ #
    # Phase 2 — run annotation
    # ------------------------------------------------------------------ #
    annotate_args: list[str] = [
        sys.executable, annotate_script,
        args.input, args.output,
        "--sparql-endpoint", args.sparql_endpoint,
        "--openai-base-url", base_url,
        "--openai-api-key", args.openai_api_key or "nokeyrequired",
        "--model", args.model,
        "--field", args.field,
        "--k", str(args.k),
        "--max-steps", str(args.max_steps),
    ]
    if args.index_dir:
        annotate_args.extend(["--index-dir", args.index_dir])
    if args.overwrite:
        annotate_args.append("--overwrite")
    if args.progress:
        annotate_args.append("--progress")

    print(f"[pipeline] Running annotation …", file=sys.stderr)
    ret = subprocess.run(annotate_args, cwd=_PROJECT_ROOT)

    # ------------------------------------------------------------------ #
    # Phase 3 — stop server
    # ------------------------------------------------------------------ #
    if not args.no_server:
        stop_server(port, slurm_active)
        if server_proc:
            server_proc.wait()

    sys.exit(ret.returncode)


if __name__ == "__main__":
    main()
