# Container Utils Library Design

**Date:** 2026-03-17
**Status:** Approved

## Overview

Refactor `update_scripts/` to extract shared container update logic into a reusable bash library. Both `update_ollama.sh` and `update_open-webui.sh` currently duplicate container lifecycle management. A shared library eliminates duplication and establishes a consistent pattern for all future update scripts.

The scripts `update_gptresearcher.sh`, `update_piper.sh`, `update_perplexica.sh`, `update_openhands.sh`, and `update_stablediffusion.sh` are out of scope for this refactor.

## Goals

- Single place for smart container update logic (pull → compare image IDs → restart only if needed)
- Opt-in Vault secret fetching via a single `get_secret <name>` call — no boilerplate in scripts
- Shared GPU config loading since multiple scripts will need GPU configuration
- Automatic `docker image prune` after all containers update successfully
- `update_ollama.sh` cleaned of all open-webui references

## Architecture

### Library: `update_scripts/lib/container_utils.sh`

The `update_scripts/lib/` directory must be created before the file is written.

New file, version 1.0.0. Does not have a shebang line (it is sourced, not executed). Header format:

```bash
# container_utils.sh
# version: 1.0.0
# Shared library for container update scripts. Source this file; do not execute directly.
#
# History
#   1.0.0 - 2026-03-17,     Initial release
#
```

The library does NOT call `set -euo pipefail`. Each calling script is responsible for setting its own error-handling options. All scripts in `update_scripts/` must use `set -euo pipefail` at their top level.

Requires bash 4.3+ (for `declare -n` nameref support). The library will validate this at load time. Because the file is sourced, `exit` would kill the parent shell — use the `return 1 2>/dev/null || exit 1` idiom, which returns when sourced and exits when executed directly:

```bash
if (( BASH_VERSINFO[0] < 4 || (BASH_VERSINFO[0] == 4 && BASH_VERSINFO[1] < 3) )); then
    echo "[ERROR] container_utils.sh requires bash 4.3+" >&2
    return 1 2>/dev/null || exit 1
fi
```

Sourced via:

```bash
source "$(dirname "$0")/lib/container_utils.sh"
```

#### Log output format

All library output uses prefixed tags written to **stderr**:

- `[INFO]` — informational progress messages
- `[OK]` — success confirmation
- `[WARN]` — non-fatal warnings
- `[ERROR]` — fatal errors
- `[STOP]` — container being stopped
- `[RUN]` — container being started

Only values intended for command substitution (i.e. `get_secret`) go to **stdout**. All docker command stdout output is suppressed with `>/dev/null` unless the output is being captured for error re-emission (as in `docker pull`).

#### Internal state

Container names may contain hyphens (e.g. `open-webui`). Bash variable names cannot contain hyphens. When storing per-container state in named arrays, hyphens in the container name are replaced with underscores for the variable name only. The original container name is always used for all docker commands. For example, container `open-webui` is stored in `_CONTAINER_OPTS_open_webui`.

Registered containers are stored using:

- `_CONTAINER_NAMES` — indexed array of registered container names (original names, including hyphens) in registration order
- `_CONTAINER_IMAGES` — associative array mapping sanitized name → image
- Per-container options array `_CONTAINER_OPTS_<sanitized_name>` — bash array holding docker run options for that container. Accessed inside `run_updates` using `declare -n _cu_opts_ref="_CONTAINER_OPTS_${sanitized_name}"`. The nameref variable is named `_cu_opts_ref` (prefixed with `_cu_` to avoid collision with any variable in the calling script's scope).
- `_RUN_UPDATES_CALLED` — boolean flag (initialized to `false`, set to `true` when `run_updates` is invoked). Checked at the top of `register_container` to detect invalid post-run registration.
- `_VAULT_TOKEN` — cached Vault token set on first successful `get_secret` call.

`run_updates` must be called exactly once per script. After it sets `_RUN_UPDATES_CALLED=true`, any further call to `register_container` will exit non-zero.

#### Public API

---

**`get_secret <name>`**

Fetches a secret from Vault. On first call, performs AppRole login and caches the token in `_VAULT_TOKEN`. Subsequent calls reuse the cached token. Constructs the full secret path as `secret/hosts/$(hostname)/<name>`. Reads Vault address from `/etc/vault/vault_addr` and AppRole credentials from `/etc/vault/host/role_id` and `/etc/vault/host/secret_id`.

All log and error messages go to **stderr**. Only the secret value is written to **stdout**, making it safe for command substitution.

Error paths are guarded with explicit `|| { echo "[ERROR] ..." >&2; exit 1; }` patterns so that the `[ERROR]` message is always emitted to stderr before the process exits, even when `set -e` is active in the calling script.

Secrets are fetched using `vault kv get -field=value "secret/hosts/$(hostname)/<name>"`. The field name is always `value`. An existing-but-empty field value (exit 0) is treated as valid and written to stdout as an empty string. A non-zero exit from `vault kv get` (path not found or field not found) is treated as an error.

Exits non-zero with a clear `[ERROR]` message to stderr if:
- `/etc/vault/vault_addr` is missing or empty
- `/etc/vault/host/role_id` or `/etc/vault/host/secret_id` is missing
- Vault login fails (non-zero exit from `vault write`)
- Secret does not exist at the constructed path

Usage:
```bash
MY_SECRET=$(get_secret "my_secret_name")
```

---

**`source_gpu_config [path]`**

Sources the `GPU_config` file. If no path is given or an empty string is passed, defaults to `/etc/llm_code/GPU_config` — the standard system location for host-specific GPU configuration, consistent with FHS `/etc/` conventions and aligned with how Vault credentials are stored under `/etc/vault/`.

After sourcing, variables `GPU0`–`GPU4` are available in the calling script. The function does not validate that all five variables were set — if `GPU_config` is malformed, the caller is responsible for detecting missing variables. Exits non-zero with `[ERROR]` if the resolved path does not exist.

Scripts that do not need GPU configuration (e.g. `update_open-webui.sh`) must not call this function.

Usage:
```bash
source_gpu_config
# or with explicit path:
source_gpu_config /path/to/GPU_config
```

---

**`register_container <name> <image> [docker_opts...]`**

Registers a container for the update run.

- The image is stored separately and appended as the final argument to `docker run` by `run_updates`. Callers must not include the image in `docker_opts`.
- `--name` is added automatically by the library from `<name>`. Callers must not include `--name` in `docker_opts`.
- `-d` (detached mode) is hardcoded in `run_updates`'s `docker run` invocation. It is NOT stored in the options array. Callers must not include `-d` in `docker_opts`.
- Options are stored in per-container bash arrays using the sanitized name. This avoids eval and is compatible with shellcheck.

Calling `register_container` after `run_updates` has already been called (i.e. `_RUN_UPDATES_CALLED=true`) exits non-zero with `[ERROR] register_container called after run_updates`.

Usage:
```bash
GPU_OPTS=(--gpus=all -e "CUDA_VISIBLE_DEVICES=$GPU0,$GPU2,$GPU3,$GPU4")

register_container "ollama" "ollama/ollama:${OLLAMA_VERSION}" \
    "${GPU_OPTS[@]}" \
    -p 11434:11434 \
    --restart always
```

---

**`run_updates`**

Drives the full update lifecycle for all registered containers, then prunes images if all updates succeeded.

Sets `_RUN_UPDATES_CALLED=true` at entry.

If no containers are registered, logs `[WARN] No containers registered.` and returns 0.

Algorithm:

1. Set `_all_ok=true`
2. For each container in registration order:
   a. Record current image ID: `docker image inspect "$image" --format '{{.Id}}' 2>/dev/null || echo ""`
   b. Pull image: `docker pull "$image"` — stdout and stderr from `docker pull` are captured; on failure, emit `[ERROR] docker pull failed for $image (exit $pull_rc)` to stderr, then re-emit the captured output to stderr, set `_all_ok=false`, and continue to the next container
   c. Record new image ID: `docker image inspect "$image" --format '{{.Id}}'`
   d. Check whether the container is currently running: `docker ps -q -f "name=$name"`
   e. If image ID changed OR container is not running:
      - If container exists (running or stopped), check with `docker inspect "$name" >/dev/null 2>&1`: stop with `docker stop "$name" 2>/dev/null || true`, remove with `docker rm "$name" 2>/dev/null || true` (failures are silently ignored, matching existing behaviour)
      - Start: `docker run -d --name "$name" "${_cu_opts_ref[@]}" "$image"` using the `_cu_opts_ref` nameref to the stored options array
      - On failure log `[ERROR]`, set `_all_ok=false`
   f. If image ID unchanged AND container is running: log `[OK] $name is up-to-date, skipping restart.`
3. After all containers are processed:
   - If `_all_ok=true`: run `docker image prune -f` (dangling images only, `--all` is intentionally omitted), log `[OK] Image prune complete.`
   - If `_all_ok=false`: log `[WARN] Skipping image prune due to update errors.`, then `exit 1`

`run_updates` processes all registered containers regardless of individual failures before deciding on exit code. It does not short-circuit on the first failure.

---

### Refactored `update_ollama.sh`

Version bumps from 1.0.0 → 2.0.0. This is a breaking change: the previous always-stop/remove/recreate flow is replaced by the smart update flow in the library, and the script requires the library to be present.

The current file contains: a `stop_container` function, a `remove_container` function, an `update_container` function, a `cleanup` function, an `ollama_start` function, an `open-webui_start` function, a loop over `[ollama, open-webui]`, separate `update_container` calls for ollama and open-webui, a call to `ollama_start`, and a call to `cleanup`. All of this is replaced by the library-based structure below. The commented-out `open-webui_start` call (lines 81–83) is also removed.

GPU1 (RTX 2060 Super, `$GPU1`) is intentionally excluded from the `CUDA_VISIBLE_DEVICES` list. Ollama uses only `$GPU0,$GPU2,$GPU3,$GPU4`. This must be preserved exactly.

Final file content:

```bash
#!/usr/bin/env bash
#
# Author: Juha Leivo
# Version: 2.0.0
# Date: 2026-03-17
#
# History
#   1.0.0 - 2026-03-17,     Added official header, changed ollama GPU config to
#                           use variable and centralized GPU config file
#   2.0.0 - 2026-03-17,     Refactored to use container_utils shared library,
#                           removed open-webui parts
#
set -euo pipefail

source "$(dirname "$0")/lib/container_utils.sh"

source_gpu_config

OLLAMA_VERSION="0.17.4"
GPU_OPTS=(--gpus=all -e "CUDA_VISIBLE_DEVICES=$GPU0,$GPU2,$GPU3,$GPU4")

register_container "ollama" "ollama/ollama:${OLLAMA_VERSION}" \
    "${GPU_OPTS[@]}" \
    -v ollama:/root/.ollama \
    -v ollama-import:/import \
    -v /srv/ollama/container_modelfiles:/modelfiles \
    -p 11434:11434 \
    -e OLLAMA_MAX_LOADED_MODELS=4 \
    -e OLLAMA_NUM_PARALLEL=4 \
    -e OLLAMA_FLASH_ATTENTION=1 \
    -e OLLAMA_KV_CACHE_TYPE=q8_0 \
    -e OLLAMA_KEEP_ALIVE=24h \
    --restart always

run_updates
```

No Vault usage. No open-webui references.

---

### Refactored `update_open-webui.sh`

Version bumps from 1.2.0 → 2.0.0. Breaking change: inline `update_container` function and Vault auth block replaced by library.

The current `update_open-webui.sh` has no history block in its file header — only `# version: 1.2.0` on line 2. Do not invent prior history entries. The new header carries only the 2.0.0 entry.

`source_gpu_config` is not called — open-webui and open-terminal do not require GPU configuration.

The `open-terminal` image has no explicit tag (`ghcr.io/open-webui/open-terminal`). Docker defaults to `:latest`. This is intentional and matches the existing behaviour.

Final file content:

```bash
#!/usr/bin/env bash
#
# Author: Juha Leivo
# Version: 2.0.0
# Date: 2026-03-17
#
# History
#   2.0.0 - 2026-03-17,     Refactored to use container_utils shared library
#
set -euo pipefail

source "$(dirname "$0")/lib/container_utils.sh"

OPEN_TERMINAL_API_KEY=$(get_secret "open_terminal_apikey")

NETWORK_NAME="open-webui-network"
WEBUI_IMG="ghcr.io/open-webui/open-webui:main"
TERMINAL_IMG="ghcr.io/open-webui/open-terminal"

if ! docker network inspect "$NETWORK_NAME" >/dev/null 2>&1; then
    echo "[INFO] Creating docker network $NETWORK_NAME ..." >&2
    docker network create "$NETWORK_NAME" >/dev/null
fi

register_container "open-webui" "$WEBUI_IMG" \
    -p 127.0.0.1:4000:8080 \
    -v open-webui:/app/backend/data \
    --network="$NETWORK_NAME" \
    --restart always

register_container "open-terminal" "$TERMINAL_IMG" \
    -v open-terminal:/home/user \
    -e "OPEN_TERMINAL_API_KEY=${OPEN_TERMINAL_API_KEY}" \
    --network="$NETWORK_NAME" \
    --memory=2g \
    --cpus=2.0 \
    --restart always

run_updates
```

The inline `update_container` function and Vault auth block are removed entirely.

---

### GPU_config

The file `update_scripts/GPU_config` is moved to `/etc/llm_code/GPU_config`. The `/etc/llm_code/` directory must be created if it does not exist. File content is unchanged — it contains GPU UUID variables `GPU0`–`GPU4`. The old `update_scripts/GPU_config` file is deleted after the move.

---

### `update_scripts/CHANGELOG.md`

The existing CHANGELOG.md uses a flat format with `## [version] - date` headings, not per-script sections. Continue this format. Append the following entries at the top of the file (most recent first):

```markdown
## [2.0.0] - 2026-03-17

### Added
- `lib/container_utils.sh` v1.0.0 — shared bash library providing `get_secret`,
  `source_gpu_config`, `register_container`, and `run_updates`

### Changed
- `update_ollama.sh` refactored to use container_utils library; removed all
  open-webui references; smart update logic (skip restart if image unchanged
  and container running)
- `update_open-webui.sh` refactored to use container_utils library; Vault auth
  replaced by `get_secret` call; inline `update_container` function removed
```

---

## File Summary

| File | Action | New Version |
|---|---|---|
| `update_scripts/lib/` | Create directory | — |
| `update_scripts/lib/container_utils.sh` | Create | 1.0.0 |
| `update_scripts/update_ollama.sh` | Refactor | 2.0.0 |
| `update_scripts/update_open-webui.sh` | Refactor | 2.0.0 |
| `update_scripts/GPU_config` | Move to `/etc/llm_code/GPU_config` | — |
| `update_scripts/CHANGELOG.md` | Prepend 2.0.0 entry | — |

---

## Testing

- `shellcheck -s bash` must pass on all three bash files with zero warnings
- Manual verification on the target host:
  - Containers restart when a new image is available
  - Containers are skipped when already up-to-date and running
  - `docker image prune` runs after a fully successful update
  - `docker image prune` is skipped when any container update fails
  - Calling `register_container` after `run_updates` exits with `[ERROR]`
  - `run_updates` with no registered containers logs `[WARN]` and exits 0
- Vault / secret tests:
  - `get_secret` emits `[ERROR]` to stderr and exits non-zero when Vault is unreachable
  - Multiple `get_secret` calls in one script trigger only one Vault login
