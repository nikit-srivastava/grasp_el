#!/usr/bin/env bash
# Create a virtual environment and install dependencies for annotate_entities.py.
#
# Usage:
#   bash scripts/setup_annotate_env.sh [VENV_DIR]
#
# VENV_DIR defaults to "venv" in the project root. After setup, activate with:
#   source <VENV_DIR>/bin/activate

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${1:-${PROJECT_ROOT}/venv}"

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
info()  { echo "[setup] $*"; }
error() { echo "[setup] ERROR: $*" >&2; exit 1; }

# --------------------------------------------------------------------------- #
# Locate a Python >= 3.12 interpreter
# --------------------------------------------------------------------------- #
find_python() {
    for candidate in python3.13 python3.12 python3 python; do
        if command -v "${candidate}" &>/dev/null; then
            version="$("${candidate}" -c 'import sys; print(sys.version_info[:2])')"
            # version is a tuple like (3, 13) — compare numerically
            ok="$("${candidate}" -c '
import sys
v = sys.version_info
print("ok" if (v.major, v.minor) >= (3, 12) else "no")
')"
            if [[ "${ok}" == "ok" ]]; then
                echo "${candidate}"
                return 0
            fi
        fi
    done
    return 1
}

PYTHON="$(find_python)" || error "Python 3.12+ is required but not found on PATH."
info "Using interpreter: ${PYTHON} ($(${PYTHON} --version))"

# --------------------------------------------------------------------------- #
# Create the virtual environment
# --------------------------------------------------------------------------- #
if [[ -d "${VENV_DIR}" ]]; then
    info "Virtual environment already exists at ${VENV_DIR} — skipping creation."
else
    info "Creating virtual environment at ${VENV_DIR} ..."
    "${PYTHON}" -m venv "${VENV_DIR}"
fi

PIP="${VENV_DIR}/bin/pip"

# Use project root for pip temp files and disable cache to avoid running out
# of space on constrained tmpfs partitions.
export TMPDIR="${PROJECT_ROOT}/.pip-tmp"
mkdir -p "${TMPDIR}"
PIP_EXTRA="--no-cache-dir"

# --------------------------------------------------------------------------- #
# Install the package (editable so local changes are immediately reflected)
# --------------------------------------------------------------------------- #
info "Upgrading pip ..."
"${PIP}" install ${PIP_EXTRA} --quiet --upgrade pip

info "Installing grasp-rdf (editable) from ${PROJECT_ROOT} ..."
"${PIP}" install ${PIP_EXTRA} --quiet -e "${PROJECT_ROOT}"

# sentence-transformers is needed by KgManager.load_models() for embedding
# indices but is an optional dependency of search-rdf, so pin it explicitly.
info "Installing sentence-transformers ..."
"${PIP}" install ${PIP_EXTRA} --quiet "sentence-transformers>=3.0.0"

# --------------------------------------------------------------------------- #
# Cleanup
# --------------------------------------------------------------------------- #
rm -rf "${TMPDIR}"

# --------------------------------------------------------------------------- #
# Done
# --------------------------------------------------------------------------- #
ACTIVATE="${VENV_DIR}/bin/activate"

info "Done. Activate the environment with:"
info "  source ${ACTIVATE}"
info ""
info "Then run:"
info "  python scripts/annotate_entities.py \\"
info "    questions.jsonl annotated.jsonl \\"
info "    --sparql-endpoint <URL> \\"
info "    --openai-base-url <URL> \\"
info "    --model gpt-4o-mini \\"
info "    --progress"
