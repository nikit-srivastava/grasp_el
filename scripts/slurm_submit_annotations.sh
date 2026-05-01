#!/usr/bin/env bash
# Submit parallel annotation jobs to a SLURM cluster.
#
# Each job launches its own llama-server (via apptainer) on a dedicated GPU,
# annotates one input JSONL file, then tears down the server.
#
# Sample usage:
#   # Annotate all files matching a glob:
#   bash scripts/slurm_submit_annotations.sh \
#       --input-glob "data/chunks/chunk_*.jsonl" \
#       --output-dir "data/annotated_chunks" \
#       --sparql-endpoint "http://enexa1.cs.uni-paderborn.de:9080/sparql" \
#       --model qwen-3.6-27b \
#       --partition gpu_a100 \
#       --gres gpu:1
#
#   # Annotate files listed in a manifest (one path per line):
#   bash scripts/slurm_submit_annotations.sh \
#       --input-manifest data/file_list.txt \
#       --output-dir "data/annotated_chunks" \
#       --sparql-endpoint "http://enexa1.cs.uni-paderborn.de:9080/sparql" \
#       --model qwen-3.6-27b
#
#   # Dry-run to see what would be submitted:
#   bash scripts/slurm_submit_annotations.sh \
#       --input-glob "data/chunks/chunk_*.jsonl" \
#       --output-dir "data/annotated_chunks" \
#       --dry-run

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# --------------------------------------------------------------------------- #
# Defaults
# --------------------------------------------------------------------------- #
PARTITION="gpu"
TIME_LIMIT="24:00:00"
GRES="gpu:1"
CPUS_PER_TASK=8
MEM_PER_CPU="4G"
MODEL="qwen-3.6-27b"
SPARQL_ENDPOINT=""
INPUT_GLOB=""
INPUT_MANIFEST=""
OUTPUT_DIR=""
DRY_RUN=false
ARRAY=false
VENV=""
EXTRA_ANNOTATE_ARGS=""

# --------------------------------------------------------------------------- #
# Argument parsing
# --------------------------------------------------------------------------- #
while [[ $# -gt 0 ]]; do
  case "$1" in
    --partition)        PARTITION="$2";       shift 2 ;;
    --time-limit)       TIME_LIMIT="$2";      shift 2 ;;
    --gres)             GRES="$2";            shift 2 ;;
    --cpus-per-task)    CPUS_PER_TASK="$2";   shift 2 ;;
    --mem-per-cpu)      MEM_PER_CPU="$2";     shift 2 ;;
    --model)            MODEL="$2";           shift 2 ;;
    --sparql-endpoint)  SPARQL_ENDPOINT="$2"; shift 2 ;;
    --input-glob)       INPUT_GLOB="$2";      shift 2 ;;
    --input-manifest)   INPUT_MANIFEST="$2";  shift 2 ;;
    --output-dir)       OUTPUT_DIR="$2";      shift 2 ;;
    --venv)             VENV="$2";            shift 2 ;;
    --extra-args)       EXTRA_ANNOTATE_ARGS="$2"; shift 2 ;;
    --dry-run)          DRY_RUN=true;         shift   ;;
    --array)            ARRAY=true;           shift   ;;
    --help|-h)
      head -20 "$0" | grep "^#" | sed 's/^# *\??//'
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
if [[ -z "$SPARQL_ENDPOINT" ]]; then
  echo "ERROR: --sparql-endpoint is required." >&2
  exit 1
fi

if [[ -z "$INPUT_GLOB" && -z "$INPUT_MANIFEST" ]]; then
  echo "ERROR: Provide either --input-glob or --input-manifest." >&2
  exit 1
fi

if [[ -z "$OUTPUT_DIR" ]]; then
  echo "ERROR: --output-dir is required." >&2
  exit 1
fi

if [[ -z "$VENV" ]]; then
  VENV="${PROJECT_ROOT}/venv"
fi

if [[ ! -d "$VENV" ]]; then
  echo "ERROR: Virtual environment not found at ${VENV}. Run scripts/setup_annotate_env.sh first." >&2
  exit 1
fi

# --------------------------------------------------------------------------- #
# Collect input files
# --------------------------------------------------------------------------- #
INPUT_FILES=()

if [[ -n "$INPUT_GLOB" ]]; then
  # shellcheck disable=SC2206
  INPUT_FILES=($INPUT_GLOB)
fi

if [[ -n "$INPUT_MANIFEST" ]]; then
  while IFS= read -r f || [[ -n "$f" ]]; do
    [[ -z "$f" || "$f" == \#* ]] && continue
    INPUT_FILES+=("$f")
  done < "$INPUT_MANIFEST"
fi

if [[ ${#INPUT_FILES[@]} -eq 0 ]]; then
  echo "ERROR: No input files found." >&2
  exit 1
fi

echo "[slurm-submit] Found ${#INPUT_FILES[@]} input file(s)."

# --------------------------------------------------------------------------- #
# Resolve output filename for each input
# --------------------------------------------------------------------------- #
resolve_output() {
  local input_file="$1"
  local basename="$(basename "$input_file" .jsonl)"
  echo "${OUTPUT_DIR}/${basename}_annotated.jsonl"
}

# --------------------------------------------------------------------------- #
# Generate a single SLURM job script
# --------------------------------------------------------------------------- #
generate_job_script() {
  local input_file="$1"
  local output_file="$2"
  local job_script="$3"

  cat > "$job_script" <<SLURM_EOF
#!/usr/bin/env bash
#SBATCH --job-name=annotate-$(basename "$input_file" .jsonl)
#SBATCH --partition=${PARTITION}
#SBATCH --time=${TIME_LIMIT}
#SBATCH --gres=${GRES}
#SBATCH --cpus-per-task=${CPUS_PER_TASK}
#SBATCH --mem-per-cpu=${MEM_PER_CPU}
#SBATCH --output=data_dir/slurm-logs/annotate-%x-%A-%a.out
#SBATCH --error=data_dir/slurm-logs/annotate-%x-%A-%a.err

set -euo pipefail

export SLURM_ACTIVE=true
export PROJECT_ROOT="${PROJECT_ROOT}"

# Activate virtual environment
source "${VENV}/bin/activate"

# Run the annotation pipeline
python scripts/run_annotation_pipeline.py \
    "${input_file}" "${output_file}" \
    --sparql-endpoint "${SPARQL_ENDPOINT}" \
    --model "${MODEL}" \
    --slurm-active \
    --progress \
    ${EXTRA_ANNOTATE_ARGS}
SLURM_EOF
  chmod +x "$job_script"
}

# --------------------------------------------------------------------------- #
# Submit jobs
# --------------------------------------------------------------------------- #
mkdir -p "${OUTPUT_DIR}"
mkdir -p "${PROJECT_ROOT}/data_dir/slurm-logs"

if [[ "$ARRAY" == true ]]; then
  # --- Array job mode: one SLURM job with array indices ---
  # Write an index file mapping array index → input/output pairs
  TMPDIR_SUBMIT="$(mktemp -d)"
  INDEX_FILE="${TMPDIR_SUBMIT}/job_index.txt"

  idx=0
  for input_file in "${INPUT_FILES[@]}"; do
    output_file="$(resolve_output "$input_file")"
    echo "${input_file}|${output_file}" >> "$INDEX_FILE"
    idx=$((idx + 1))
  done

  ARRAY_RANGE="0-$((idx - 1))"

  # Generate the array job script
  ARRAY_SCRIPT="${TMPDIR_SUBMIT}/annotate_array.sh"
  cat > "$ARRAY_SCRIPT" <<ARRAY_EOF
#!/usr/bin/env bash
#SBATCH --job-name=annotate-array
#SBATCH --partition=${PARTITION}
#SBATCH --time=${TIME_LIMIT}
#SBATCH --gres=${GRES}
#SBATCH --cpus-per-task=${CPUS_PER_TASK}
#SBATCH --mem-per-cpu=${MEM_PER_CPU}
#SBATCH --output=data_dir/slurm-logs/annotate-array-%A-%a.out
#SBATCH --error=data_dir/slurm-logs/annotate-array-%A-%a.err

set -euo pipefail

export SLURM_ACTIVE=true
export PROJECT_ROOT="${PROJECT_ROOT}"

source "${VENV}/bin/activate"

# Read the indexed pair for this array task
LINE=\$(sed -n "$(( \${SLURM_ARRAY_TASK_ID} + 1 ))p" "${INDEX_FILE}")
INPUT_FILE=\$(echo "\$LINE" | cut -d'|' -f1)
OUTPUT_FILE=\$(echo "\$LINE" | cut -d'|' -f2)

echo "[array-job \${SLURM_ARRAY_TASK_ID}] Processing: \$INPUT_FILE -> \$OUTPUT_FILE"

python scripts/run_annotation_pipeline.py \
    "\$INPUT_FILE" "\$OUTPUT_FILE" \
    --sparql-endpoint "${SPARQL_ENDPOINT}" \
    --model "${MODEL}" \
    --slurm-active \
    --progress \
    ${EXTRA_ANNOTATE_ARGS}
ARRAY_EOF
  chmod +x "$ARRAY_SCRIPT"

  if [[ "$DRY_RUN" == true ]]; then
    echo "[slurm-submit] [DRY-RUN] Would submit array job:"
    echo "  sbatch --array=${ARRAY_RANGE} ${ARRAY_SCRIPT}"
    echo ""
    echo "  Index file (${INDEX_FILE}):"
    cat "$INDEX_FILE"
    echo ""
    echo "  Job script:"
    cat "$ARRAY_SCRIPT"
    rm -rf "$TMPDIR_SUBMIT"
    exit 0
  fi

  echo "[slurm-submit] Submitting array job (range: ${ARRAY_RANGE}) …"
  JOB_ID=$(sbatch --array="${ARRAY_RANGE}" "$ARRAY_SCRIPT" | awk '{print $4}')
  echo "[slurm-submit] Array job submitted: ${JOB_ID}"
  echo "[slurm-submit] Track with: squeue -j ${JOB_ID}"

  # Keep the temp files so SLURM can read them (clean up after jobs finish)
  echo "[slurm-submit] Job index stored at: ${INDEX_FILE}"
else
  # --- Individual job mode: one sbatch per file ---
  JOB_SCRIPTS_DIR="${PROJECT_ROOT}/data_dir/slurm-job-scripts"
  mkdir -p "$JOB_SCRIPTS_DIR"

  job_count=0
  for input_file in "${INPUT_FILES[@]}"; do
    output_file="$(resolve_output "$input_file")"
    job_name="$(basename "$input_file" .jsonl)"
    job_script="${JOB_SCRIPTS_DIR}/annotate_${job_name}.sh"

    generate_job_script "$input_file" "$output_file" "$job_script"

    if [[ "$DRY_RUN" == true ]]; then
      echo "[slurm-submit] [DRY-RUN] Would submit: ${job_script}"
      echo "  Input:  ${input_file}"
      echo "  Output: ${output_file}"
      echo ""
    else
      echo "[slurm-submit] Submitting: ${job_name} (${job_count} …)"
      JOB_ID=$(sbatch "$job_script" | awk '{print $4}')
      echo "  → Job ID: ${JOB_ID}"
      job_count=$((job_count + 1))
    fi
  done

  if [[ "$DRY_RUN" == true ]]; then
    echo "[slurm-submit] [DRY-RUN] Total jobs that would be submitted: ${#INPUT_FILES[@]}"
  else
    echo "[slurm-submit] Submitted ${job_count} job(s)."
    echo "[slurm-submit] Track with: squeue -u \$(whoami)"
  fi
fi
