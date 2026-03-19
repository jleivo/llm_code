# GPU_config Developer Guide

How to write a new script — bash or Python — running on the host that
uses the shared GPU configuration to restrict CUDA access to specific GPUs.

---

## Concepts

### The config file

`/etc/llm_code/GPU_config` (deployed from `update_scripts/GPU_config`) maps
stable logical names `GPU0`–`GPU4` to NVIDIA GPU UUIDs. See
`docs/gpu-config-architecture.md` for the full data-flow.

### GPU selection

Both bash container scripts and Python host scripts control GPU visibility
through the `CUDA_VISIBLE_DEVICES` environment variable. The value is a
comma-separated list of GPU UUIDs. CUDA ignores any device not in the list.

### When to load GPU config

Only load GPU config when the script actually uses a GPU. CPU-only scripts must
not touch it.

---

## Bash — container update scripts

These scripts manage Docker containers via `lib/container_utils.sh`.

### Quick-start checklist

1. Source `lib/container_utils.sh`.
2. Call `source_gpu_config` (only if the container needs GPU access).
3. Build a `GPU_OPTS` array from the variables.
4. Pass `"${GPU_OPTS[@]}"` to `register_container`.
5. Call `run_updates` at the end.

### Step-by-step

#### 1. Source the library

Always use `$(dirname "$0")` so the script works from any working directory.

```bash
# shellcheck source=lib/container_utils.sh
source "$(dirname "$0")/lib/container_utils.sh"
```

#### 2. Load GPU config

```bash
# shellcheck disable=SC2119  # no arg is intentional
source_gpu_config
```

After this call `$GPU0` through `$GPU4` are available in the script.

#### 3. Select GPUs for the container

```bash
# All GPUs
GPU_OPTS=(--gpus=all -e "CUDA_VISIBLE_DEVICES=$GPU0,$GPU1,$GPU2,$GPU3,$GPU4")

# Heavy model: 24 GB cards only
GPU_OPTS=(--gpus=all -e "CUDA_VISIBLE_DEVICES=$GPU0,$GPU3,$GPU4")

# Single card
GPU_OPTS=(--gpus=all -e "CUDA_VISIBLE_DEVICES=$GPU2")
```

`--gpus=all` makes all GPU devices visible to Docker. `CUDA_VISIBLE_DEVICES`
then restricts CUDA to the listed UUIDs. Both are required; using
`CUDA_VISIBLE_DEVICES` alone without `--gpus=all` has no effect inside a
container.

#### 4. Register and run

```bash
register_container "myapp" "vendor/myapp:${APP_VERSION}" \
    "${GPU_OPTS[@]}" \
    -p 8080:8080 \
    --restart always

run_updates
```

### Complete minimal bash example

```bash
#!/usr/bin/env bash
#
# Author: Juha Leivo
# Version: 1.0.0
# Date: YYYY-MM-DD
#
# History
#   1.0.0 - YYYY-MM-DD,     Initial release
#
set -euo pipefail

# shellcheck source=lib/container_utils.sh
source "$(dirname "$0")/lib/container_utils.sh"

# shellcheck disable=SC2119
source_gpu_config

APP_VERSION="1.0.0"
GPU_OPTS=(--gpus=all -e "CUDA_VISIBLE_DEVICES=$GPU0,$GPU2,$GPU3,$GPU4")

register_container "myapp" "vendor/myapp:${APP_VERSION}" \
    "${GPU_OPTS[@]}" \
    -p 8080:8080 \
    --restart always

run_updates
```

### Bash testing

Never depend on `/etc/llm_code/GPU_config` in tests — pass an explicit fixture
path to `source_gpu_config`, or override `_GPU_CONFIG_FILE`:

```bash
# Explicit path
tmpfile="$(mktemp)"
echo 'GPU0="GPU-aaaaaaaa-0000-0000-0000-000000000000"' > "$tmpfile"
source lib/container_utils.sh
source_gpu_config "$tmpfile"
rm -f "$tmpfile"

# Override default path
export _GPU_CONFIG_FILE="$tmpfile"
source lib/container_utils.sh
source_gpu_config   # reads $tmpfile
```

BATS pattern:

```bash
@test "my container uses correct GPUs" {
    local cfg
    cfg="$(mktemp)"
    echo 'GPU0="GPU-test-uuid"' > "$cfg"

    run bash -c "
        source '${BATS_TEST_DIRNAME}/../lib/container_utils.sh'
        source_gpu_config '$cfg'
        echo \$GPU0
    "
    [ "$status" -eq 0 ]
    [ "$output" = "GPU-test-uuid" ]
    rm -f "$cfg"
}
```

### Refactoring an existing bash script

| Before | After |
|---|---|
| `source ./GPU_config` | `source_gpu_config` |
| `source /etc/llm_code/GPU_config` | `source_gpu_config` |
| Hardcoded UUID in `CUDA_VISIBLE_DEVICES` | `$GPU0`, `$GPU2`, … |

Bump the version (Y+1 for behaviour change, Z+1 for equivalent refactor) and
add a history entry.

---

## Python — host scripts

Python scripts running directly on the host (not inside Docker) use the same
`/etc/llm_code/GPU_config` file. Because Python cannot source bash files, the
script parses the file itself and sets `CUDA_VISIBLE_DEVICES` in
`os.environ` before importing any CUDA library.

### Critical rule: set `CUDA_VISIBLE_DEVICES` before CUDA imports

CUDA reads `CUDA_VISIBLE_DEVICES` exactly once, at the moment the library is
first loaded. Setting it after `import torch` (or any other CUDA library) has
no effect.

**Correct order:**

```python
import os
# 1. Parse config and set env var
# 2. Only then import CUDA libraries
import torch
```

**Wrong:**

```python
import torch          # CUDA already initialised — too late
import os
os.environ["CUDA_VISIBLE_DEVICES"] = ...
```

### Parsing GPU_config in Python

Use this inline parser. It reads only `GPUn="<uuid>"` lines and ignores
comments and blank lines.

```python
import re

_GPU_CONFIG_PATH = "/etc/llm_code/GPU_config"
_GPU_LINE = re.compile(r'^(GPU\d+)="([^"]+)"')


def load_gpu_config(path: str = _GPU_CONFIG_PATH) -> dict[str, str]:
    """Return {GPU0: uuid, GPU1: uuid, …} parsed from GPU_config."""
    gpus: dict[str, str] = {}
    with open(path) as fh:
        for line in fh:
            m = _GPU_LINE.match(line.strip())
            if m:
                gpus[m.group(1)] = m.group(2)
    if not gpus:
        raise ValueError(f"No GPU entries found in {path}")
    return gpus
```

### Selecting GPUs and applying the restriction

```python
import os

gpus = load_gpu_config()

# All GPUs
os.environ["CUDA_VISIBLE_DEVICES"] = ",".join(gpus.values())

# Specific cards by logical name
os.environ["CUDA_VISIBLE_DEVICES"] = f"{gpus['GPU0']},{gpus['GPU2']}"

# Single card
os.environ["CUDA_VISIBLE_DEVICES"] = gpus["GPU2"]

# Now safe to import CUDA libraries
import torch
```

Choose GPUs based on VRAM requirements (see the variable semantics table in
`docs/gpu-config-architecture.md`).

### Complete minimal Python example

```python
#!/usr/bin/env python3
# 1.0.0
"""Example GPU-restricted host script."""

import os
import re
import sys

_GPU_CONFIG_PATH = "/etc/llm_code/GPU_config"
_GPU_LINE = re.compile(r'^(GPU\d+)="([^"]+)"')


def load_gpu_config(path: str = _GPU_CONFIG_PATH) -> dict[str, str]:
    gpus: dict[str, str] = {}
    with open(path) as fh:
        for line in fh:
            m = _GPU_LINE.match(line.strip())
            if m:
                gpus[m.group(1)] = m.group(2)
    if not gpus:
        raise ValueError(f"No GPU entries found in {path}")
    return gpus


def main() -> None:
    gpus = load_gpu_config()
    # Use the 24 GB cards; exclude GPU1 (8 GB) and GPU2 (12 GB)
    os.environ["CUDA_VISIBLE_DEVICES"] = f"{gpus['GPU0']},{gpus['GPU3']},{gpus['GPU4']}"

    import torch  # noqa: PLC0415 — intentional late import
    print(f"Visible CUDA devices: {torch.cuda.device_count()}")


if __name__ == "__main__":
    main()
```

### Python testing

Pass a fixture file path to `load_gpu_config` — never rely on
`/etc/llm_code/GPU_config` in tests.

```python
import os
import tempfile
import pytest


@pytest.fixture()
def gpu_config(tmp_path):
    cfg = tmp_path / "GPU_config"
    cfg.write_text(
        'GPU0="GPU-aaaaaaaa-0000-0000-0000-000000000000" # RTX 3090\n'
        'GPU1="GPU-bbbbbbbb-1111-1111-1111-111111111111" # RTX 2060\n'
    )
    return str(cfg)


def test_load_gpu_config(gpu_config):
    gpus = load_gpu_config(gpu_config)
    assert gpus["GPU0"] == "GPU-aaaaaaaa-0000-0000-0000-000000000000"
    assert gpus["GPU1"] == "GPU-bbbbbbbb-1111-1111-1111-111111111111"


def test_cuda_visible_devices_set_before_import(gpu_config, monkeypatch):
    gpus = load_gpu_config(gpu_config)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", gpus["GPU0"])
    # verify the env var is set; actual torch import omitted in unit tests
    assert os.environ["CUDA_VISIBLE_DEVICES"] == "GPU-aaaaaaaa-0000-0000-0000-000000000000"


def test_load_gpu_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_gpu_config("/nonexistent/GPU_config")


def test_load_gpu_config_empty_file(tmp_path):
    cfg = tmp_path / "GPU_config"
    cfg.write_text("# no entries\n")
    with pytest.raises(ValueError, match="No GPU entries found"):
        load_gpu_config(str(cfg))
```

### Alternative: launch Python from a bash wrapper

When the Python script is called from a bash script that already loaded the
config, export `CUDA_VISIBLE_DEVICES` in bash and let Python inherit it:

```bash
source_gpu_config
export CUDA_VISIBLE_DEVICES="$GPU0,$GPU2"
python3 my_script.py    # sees CUDA_VISIBLE_DEVICES from the environment
```

The Python script then reads it with `os.environ.get("CUDA_VISIBLE_DEVICES")`
instead of parsing the config file itself. Use this pattern when the GPU
selection is decided by the launcher, not the Python script.

---

## Common mistakes — all languages

| Mistake | Fix |
|---|---|
| Importing CUDA libraries before setting `CUDA_VISIBLE_DEVICES` (Python) | Set the env var before any CUDA import |
| Using `CUDA_VISIBLE_DEVICES` without `--gpus=all` in a container | Add `--gpus=all` to docker options |
| Sourcing `GPU_config` directly in bash | Use `source_gpu_config` |
| Hardcoding UUIDs | Use `$GPU0`/`gpus["GPU0"]` etc. |
| Depending on `/etc/llm_code/GPU_config` in tests | Pass an explicit fixture path |
| Loading GPU config in a CPU-only script | Remove the load entirely |

---

## Environment variables reference

| Variable | Context | Default | Purpose |
|---|---|---|---|
| `_GPU_CONFIG_FILE` | bash | `/etc/llm_code/GPU_config` | Default path for `source_gpu_config` |
| `GPU0`–`GPU4` | bash (after `source_gpu_config`) | — | GPU UUIDs as shell variables |
| `CUDA_VISIBLE_DEVICES` | both | unset | Comma-separated UUIDs CUDA will use |
