# update_scripts

Scripts that keep Docker containers on the host up to date. Each script manages one or more related containers. The shared library `lib/container_utils.sh` handles the common lifecycle.

---

## How to write a new update script

### 1. Script header

Every script must have a standard header. The version on line 2 must match the latest entry in `CHANGELOG.md`.

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
```

### 2. Source the library

```bash
# shellcheck source=lib/container_utils.sh
source "$(dirname "$0")/lib/container_utils.sh"
```

Always use `$(dirname "$0")` so the script works regardless of where it is called from. The `shellcheck source=` directive tells shellcheck where to find the library when linting from within `update_scripts/`.

### 3. Fetch secrets (optional)

Call `get_secret` for any value stored in Vault. Vault login is handled automatically on the first call and the token is cached for subsequent calls in the same run.

```bash
MY_API_KEY=$(get_secret "my_secret_name")
```

The secret is looked up at `secret/hosts/$(hostname)/my_secret_name`. The field name is always `value`. Only the secret value is written to stdout; all errors go to stderr.

Do **not** call `vault` directly or manage the token yourself.

### 4. Load GPU config (optional)

Only call this if the containers need GPU access.

```bash
source_gpu_config
```

This sources `_GPU_CONFIG_FILE` (default: `/etc/llm_code/GPU_config`) which exports variables `GPU0`–`GPU4` containing the GPU UUIDs. After the call you can use them:

```bash
GPU_OPTS=(--gpus=all -e "CUDA_VISIBLE_DEVICES=$GPU0,$GPU1,$GPU2")
```

If you need a specific path (e.g. in a test):

```bash
source_gpu_config /path/to/GPU_config
```

Scripts that do not use GPUs must not call this function.

### 5. Register containers

Call `register_container` once per container. Order determines restart order.

```bash
register_container "<name>" "<image>:<tag>" \
    [docker run options...]
```

Rules:
- Do **not** include `--name`, `-d`, or the image itself in the options — the library adds these.
- Put the image tag in a variable at the top of the script so it is easy to find and update.
- Options are passed verbatim to `docker run`, so use the same syntax you would on the command line.

Example with a pinned version:

```bash
MYAPP_VERSION="1.4.2"

register_container "myapp" "vendor/myapp:${MYAPP_VERSION}" \
    -p 127.0.0.1:8080:8080 \
    -v myapp-data:/data \
    -e "API_KEY=${MY_API_KEY}" \
    --restart always
```

Example with GPU access (GPU1 excluded here intentionally as an example):

```bash
GPU_OPTS=(--gpus=all -e "CUDA_VISIBLE_DEVICES=$GPU0,$GPU2,$GPU3,$GPU4")

register_container "myapp" "vendor/myapp:${MYAPP_VERSION}" \
    "${GPU_OPTS[@]}" \
    -p 8080:8080 \
    --restart always
```

### 6. Run updates

Always end the script with a single call to `run_updates`. Do not call it more than once.

```bash
run_updates
```

`run_updates` does the following for every registered container in order:

1. Records the current local image digest.
2. Pulls the image from the registry.
3. If the digest changed **or** the container is not running: stops and removes the existing container (if any), then starts a fresh one.
4. If the digest is unchanged **and** the container is already running: skips the restart and logs `[OK] … is up-to-date`.
5. After all containers are processed: runs `docker image prune -f` (dangling images only) if every container succeeded. Exits 1 and skips the prune if any container failed.

---

## Complete minimal example

```bash
#!/usr/bin/env bash
#
# Author: Juha Leivo
# Version: 1.0.0
# Date: 2026-03-17
#
# History
#   1.0.0 - 2026-03-17,     Initial release
#
set -euo pipefail

# shellcheck source=lib/container_utils.sh
source "$(dirname "$0")/lib/container_utils.sh"

MYAPP_VERSION="1.4.2"

register_container "myapp" "vendor/myapp:${MYAPP_VERSION}" \
    -p 127.0.0.1:8080:8080 \
    -v myapp-data:/data \
    --restart always

run_updates
```

## Complete example with secrets and GPU

```bash
#!/usr/bin/env bash
#
# Author: Juha Leivo
# Version: 1.0.0
# Date: 2026-03-17
#
# History
#   1.0.0 - 2026-03-17,     Initial release
#
set -euo pipefail

# shellcheck source=lib/container_utils.sh
source "$(dirname "$0")/lib/container_utils.sh"

source_gpu_config
MY_API_KEY=$(get_secret "myapp_apikey")

MYAPP_VERSION="1.4.2"
GPU_OPTS=(--gpus=all -e "CUDA_VISIBLE_DEVICES=$GPU0,$GPU2,$GPU3,$GPU4")

register_container "myapp" "vendor/myapp:${MYAPP_VERSION}" \
    "${GPU_OPTS[@]}" \
    -p 8080:8080 \
    -e "API_KEY=${MY_API_KEY}" \
    --restart always

run_updates
```

---

## Refactoring an existing script to use the library

1. Replace the shebang with `#!/usr/bin/env bash` if it is not already.
2. Add `set -euo pipefail` if missing.
3. Add the `source` line for the library.
4. Replace any inline `vault write` / `vault kv get` block with `get_secret` calls.
5. Replace any `source ./GPU_config` line with `source_gpu_config`.
6. Replace the stop/pull/run logic with `register_container` + `run_updates`.
7. Remove any inline `docker image prune` calls — `run_updates` handles this.
8. Bump the version (breaking change in behaviour → X+1.0.0; otherwise Y+1.0).
9. Add a history entry describing the refactor.
10. Run `shellcheck -s bash <script>` from inside `update_scripts/` — fix all warnings.

---

## Things to avoid

| Do not | Instead |
|---|---|
| Pass `--name` or `-d` to `register_container` | The library adds these automatically |
| Call `vault` directly | Use `get_secret` |
| Source `GPU_config` directly | Use `source_gpu_config` |
| Call `docker image prune` manually | `run_updates` prunes after a clean run |
| Call `run_updates` more than once | Register all containers first, then call it once |
| Call `register_container` after `run_updates` | The library exits non-zero if you do |
| Include the image in the docker options | Pass it as the second argument to `register_container` |
| Hardcode secrets | Store in Vault; fetch with `get_secret` |

---

## Linting

Run shellcheck **from inside `update_scripts/`** so the `shellcheck source=` directive resolves correctly:

```bash
cd update_scripts
shellcheck -s bash lib/container_utils.sh update_ollama.sh update_open-webui.sh
```

All scripts must pass with zero warnings before committing.

---

## Testing

Tests live in `update_scripts/tests/test_container_utils.bats`. Run them with:

```bash
bats update_scripts/tests/test_container_utils.bats
```

The test for `source_gpu_config` with the default path (`/etc/llm_code/GPU_config`) is skipped on development workstations where the system file is not deployed — that is expected.

---

## Deployment

`deploy.sh` copies the update scripts and library to the target server and puts `GPU_config` in `/etc/llm_code/`. Dry-run by default:

```bash
./deploy.sh           # shows what would be copied
./deploy.sh --apply   # performs the copy
```
