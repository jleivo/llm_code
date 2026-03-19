# GPU_config Architecture Guide

## Overview

`GPU_config` is a host-level configuration file that maps human-readable GPU
identifiers (`GPU0`–`GPU4`) to stable NVIDIA GPU UUIDs. Scripts that need to
pin containers to specific GPUs source this file instead of hardcoding UUIDs.

---

## File location and format

| Context | Path |
|---|---|
| Production (deployed on server) | `/etc/llm_code/GPU_config` |
| Repository source | `update_scripts/GPU_config` |
| Tests / dev override | any path passed to `source_gpu_config` |

```bash
# GPU config 2026-03-17, see nvidia-smi -L
GPU0="GPU-16bf6b6f-a008-eecc-50c8-eac39eae9f7d" # RTX 3090 24 GB
GPU1="GPU-a83d97d3-e077-83c5-da0b-0e434ff11694" # RXT 2060 Super 8 GB
GPU2="GPU-90689051-9191-c8a4-75b2-ab4e04dae040" # RTX 3060 12 GB
GPU3="GPU-0a895c3d-0f7f-46f1-50ab-1f84e96f7083" # RTX 3090 24 GB
GPU4="GPU-016209dd-9c62-0a1b-0fde-97cfb3b0c090" # RTX 3090 24 GB
```

- One `GPUn="<uuid>"` assignment per line.
- Comments are allowed; they describe the physical card.
- Variables are bash shell variables, not exported — they are available after
  `source`-ing the file in the calling shell only.
- UUIDs come from `nvidia-smi -L` on the target host.

---

## How it is loaded — `source_gpu_config`

`source_gpu_config` is a function in `update_scripts/lib/container_utils.sh`.
It is the only supported way to load the config.

```bash
# Signature
source_gpu_config [path]
```

| Argument | Behaviour |
|---|---|
| omitted or empty string | reads `$_GPU_CONFIG_FILE` (default: `/etc/llm_code/GPU_config`) |
| explicit path | reads that path |

Error handling: exits non-zero and prints `[ERROR]` to stderr if the file does
not exist. The calling script will abort because scripts run with `set -euo pipefail`.

Override `_GPU_CONFIG_FILE` before sourcing the library to redirect all
default-path lookups (useful in CI or dev environments):

```bash
export _GPU_CONFIG_FILE=/path/to/test/GPU_config
source "$(dirname "$0")/lib/container_utils.sh"
source_gpu_config        # now reads from the overridden path
```

---

## Data flow

```
nvidia-smi -L           (run manually to get UUIDs)
      |
      v
update_scripts/GPU_config   (committed to repo)
      |
      v  deploy_to_ollama_srv.sh --apply
      v
/etc/llm_code/GPU_config    (deployed on server)
      |
      v  source_gpu_config
      v
$GPU0 … $GPU4               (shell variables in calling script)
      |
      v  CUDA_VISIBLE_DEVICES=$GPU0,$GPU2,...
      v
docker run                  (container sees only the pinned GPUs)
```

---

## Deployment

`deploy_to_ollama_srv.sh` copies the file to the server:

```bash
# dry-run (default):
./update_scripts/deploy_to_ollama_srv.sh

# apply:
./update_scripts/deploy_to_ollama_srv.sh --apply
```

The deploy script compares MD5 checksums and only copies when content differs.

---

## Variable semantics

| Variable | Physical card | VRAM |
|---|---|---|
| `GPU0` | RTX 3090 | 24 GB |
| `GPU1` | RTX 2060 Super | 8 GB |
| `GPU2` | RTX 3060 | 12 GB |
| `GPU3` | RTX 3090 | 24 GB |
| `GPU4` | RTX 3090 | 24 GB |

Scripts choose which GPUs to expose to a container via `CUDA_VISIBLE_DEVICES`.
The variable names are stable; the underlying UUID can change if a card is
physically replaced — only `GPU_config` needs to be updated in that case.

---

## Updating UUIDs

When a GPU is replaced:

1. Run `nvidia-smi -L` on the target server.
2. Update `update_scripts/GPU_config` in the repo with the new UUID.
3. Commit and deploy: `./update_scripts/deploy_to_ollama_srv.sh --apply`.
4. Re-run any affected update scripts to restart containers with the new config.

No script changes are needed — all scripts continue to reference `$GPU0` etc.
