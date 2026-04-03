#!/usr/bin/env bash
# 1.0.0
# Deploy jules-executor skill to the global skills directory.
# Copies only runtime files, excluding tests, dev deps, and venv.
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${HOME}/.agents/skills/jules-executor"

echo "Deploying jules-executor skill"
echo "  Source: ${SOURCE_DIR}"
echo "  Target: ${TARGET_DIR}"

mkdir -p "${TARGET_DIR}/scripts"
mkdir -p "${TARGET_DIR}/references"

# Top-level skill files
cp "${SOURCE_DIR}/SKILL.md" "${TARGET_DIR}/"
cp "${SOURCE_DIR}/README.md" "${TARGET_DIR}/"

# References
cp "${SOURCE_DIR}/references/troubleshooting.md" "${TARGET_DIR}/references/"

# Runtime scripts (no tests, no dev deps, no venv)
SCRIPTS=(
    jules.py
    orchestrator.py
    plan_parser.py
    jules_cli.py
    run_plan.py
    jules-run
    jules_config.ini
    requirements.txt
    __init__.py
)

for file in "${SCRIPTS[@]}"; do
    cp "${SOURCE_DIR}/scripts/${file}" "${TARGET_DIR}/scripts/"
done

echo "Deployed to ${TARGET_DIR}"
