# Entity Linking Annotation Pipeline

This pipeline annotates natural language questions with knowledge graph entity and property links. It uses an LLM with tool-calling to identify mentions in text, searches a local KG index for candidates, and outputs structured annotations.

## Overview

```
questions.jsonl ──► annotate_entities.py ──► annotated.jsonl
                        │
                    llama-server (local LLM)
                        │
                    KG index + SPARQL endpoint
```

Each input record must contain a text field (default: `question`). The output adds an `annotations` array:

```json
{
  "question": "What is the capital of Germany?",
  "annotations": [
    {"span": "Germany", "identifier": "wd:Q183", "label": "Germany", "type": "entity"},
    {"span": "capital", "identifier": "wdt:P36", "label": "capital of", "type": "property"}
  ]
}
```

## Quick Start (SLURM)

### Prerequisites

- Access to a SLURM cluster with GPU nodes and Apptainer support
- Models directory (GGUF files) accessible at a known path
- SPARQL endpoint URL for the target knowledge graph
- GRASP KG index built (see [Index Setup](#index-setup) below)

### Step 1: Set up the environment

```bash
bash scripts/setup_annotate_env.sh
```

This creates a Python virtual environment at `venv/` and installs `grasp-rdf` + dependencies.

### Step 2: Export required environment variables

```bash
export LLAMA_CACHE="/path/to/your/model/files"
```

`LLAMA_CACHE` must point to a directory containing the downloaded GGUF model files.

### Step 3: Split input data into chunks

```bash
python scripts/split_jsonl.py data/questions_for_annotation.jsonl data/chunks/ 100
```

This produces `data/chunks/chunk_0000.jsonl … chunk_0099.jsonl`. Use `--shuffle --seed 42` to randomize record order before splitting.

### Step 4: Submit SLURM annotation jobs

```bash
bash scripts/slurm_submit_annotations.sh \
    --input-glob "data/chunks/chunk_*.jsonl" \
    --output-dir "data/annotated_chunks" \
    --sparql-endpoint "http://enexa1.cs.uni-paderborn.de:9080/sparql" \
    --model qwen-3.6-27b \
    --array
```

Each job launches its own llama-server on a dedicated GPU via Apptainer, annotates one chunk, then tears down the server.

**Submission modes:**

| Mode | Flag | Description |
|------|------|-------------|
| Individual jobs | (default) | One `sbatch` per input file |
| Array job | `--array` | Single SLURM array job; one task per file |
| Batch-limited | `--concurrency N` | Submit at most N jobs at a time, wait for completion before next batch |

**SLURM resource options (all optional):**

| Flag | Default | Description |
|------|---------|-------------|
| `--partition` | `gpu` | SLURM partition |
| `--time-limit` | `05:00:00` | Max job runtime |
| `--gres` | `gpu:h100:1` | GPU resource specification |
| `--cpus-per-task` | `8` | CPUs per job |
| `--mem-per-cpu` | `15G` | Memory per CPU |

Use `--dry-run` to preview what would be submitted without actually submitting.

### Step 5: Combine results

```bash
python scripts/combine_jsonl.py data/annotated_chunks/ data/annotated_combined.jsonl
```

This merges all per-chunk output files into a single JSONL.

## Available Models

The following models are configured in `llama-server/llama_server_models.ini`:

| Model | HuggingFace Source | Quantization |
|-------|-------------------|--------------|
| `qwen-3.6-27b` | unsloth/Qwen3.6-27B-GGUF | UD-Q4_K_XL |
| `gpt-oss-120b` | unsloth/gpt-oss-120b-GGUF | Q8_0 |
| `nemotron-3-super-120B-a12b` | unsloth/NVIDIA-Nemotron-3-Super-120B-A12B-GGUF | UD-IQ4_NL |
| `gemma-4-31b` | unsloth/gemma-4-31B-it-GGUF | UD-Q8_K_XL |

Pass the model name with `--model` to the submit script.

## Local / Docker Mode

If you don't have SLURM, you can run the pipeline locally with Docker.

### Prerequisites

- Docker with GPU support (`nvidia-container-toolkit`)
- Models directory with GGUF files
- Python 3.12+

### Setup

```bash
bash scripts/setup_annotate_env.sh
source venv/bin/activate
export LLAMA_CACHE="/path/to/your/model/files"
```

### Run

```bash
python scripts/run_annotation_pipeline.py \
    data/questions_for_annotation.jsonl data/annotated.jsonl \
    --sparql-endpoint http://enexa1.cs.uni-paderborn.de:9080/sparql \
    --model qwen-3.6-27b \
    --progress
```

This script handles the full lifecycle:

1. Starts llama-server in a Docker container on a free port
2. Runs annotation against the local server
3. Stops the server when done

**Pipeline options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--port` | `9292` | Host port for llama-server (`0` = auto-detect) |
| `--server-timeout` | `300` | Seconds to wait for server readiness |
| `--no-server` | off | Skip server management (use an already-running server) |
| `--openai-base-url` | auto | Override the LLM endpoint URL |
| `--openai-api-key` | `nokeyrequired` | API key for the LLM endpoint |
| `--index-dir` | `data/kg-index` | Path to KG index directory |
| `--field` | `question` | JSONL field containing text to annotate |
| `--k` | `5` | Search candidates per query |
| `--max-steps` | `12` | Max tool-call iterations per question |
| `--overwrite` | off | Re-annotate already-done records |
| `--progress` | off | Show a progress bar |

When using `--no-server`, you must also pass `--openai-base-url` pointing to your running llama-server.

## Index Setup

The pipeline requires a pre-built KG index. If you don't have one, build it with the GRASP CLI:

```bash
source venv/bin/activate
export GRASP_INDEX_DIR=data/kg-index

# Fetch index data from the SPARQL endpoint
grasp data wikidata --endpoint http://enexa1.cs.uni-paderborn.de:9080/sparql

# Build the search index
grasp index wikidata
```

## Running annotate_entities.py Directly

For fine-grained control, you can skip the pipeline wrapper and invoke the annotator directly against any OpenAI-compatible API:

```bash
source venv/bin/activate
python scripts/annotate_entities.py \
    data/sample_questions.jsonl data/sample_annotated.jsonl \
    --sparql-endpoint http://enexa1.cs.uni-paderborn.de:9080/sparql \
    --openai-base-url http://localhost:9292/v1 \
    --openai-api-key nokeyrequired \
    --model qwen-3.6-27b \
    --progress
```

The annotator supports automatic resume: if the output file already exists, it skips records that were successfully annotated. Use `--overwrite` to force re-annotation.

## File Layout

```
scripts/
├── setup_annotate_env.sh        # Environment setup
├── split_jsonl.py               # Split input into chunks
├── slurm_submit_annotations.sh  # SLURM job submission
├── run_annotation_pipeline.py   # Pipeline wrapper (server + annotate + cleanup)
├── annotate_entities.py         # Core annotation logic
└── combine_jsonl.py             # Merge chunk outputs

llama-server/
├── llama_server_control.sh      # Start/stop llama-server (Docker or Apptainer)
└── llama_server_models.ini      # Model configuration

data/kg-index/                   # Pre-built KG search indices
data_dir/
├── llama-server-logs/           # Per-job server logs
├── slurm-logs/                  # SLURM output/error logs
└── slurm-job-scripts/           # Generated job scripts
```

## Troubleshooting

- **`LLAMA_CACHE is not set`**: Export `LLAMA_CACHE` pointing to your models directory before running.
- **`Virtual environment not found`**: Run `bash scripts/setup_annotate_env.sh` first.
- **Server fails to start**: Check logs under `data_dir/llama-server-logs/`. The server auto-restarts up to 50 times on unexpected exit.
- **Port already in use**: The pipeline auto-detects conflicts and picks an alternative port. Use `--port 0` for full auto-detection.
- **Jobs stuck in queue**: Check with `squeue -u $(whoami)`. Use `--concurrency N` to limit concurrent submissions.
- **No search indices found**: Build the KG index first (see [Index Setup](#index-setup)).
