# Container Utils Library Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract shared Docker container update logic into `update_scripts/lib/container_utils.sh` and refactor `update_ollama.sh` and `update_open-webui.sh` to use it.

**Architecture:** A sourced bash library exposes four public functions (`get_secret`, `source_gpu_config`, `register_container`, `run_updates`). Scripts register containers declaratively and call `run_updates` to drive the full pull → smart-restart → prune lifecycle. Vault auth and GPU config are opt-in.

**Tech Stack:** bash 4.3+, bats (unit tests), shellcheck, HashiCorp Vault CLI, Docker CLI.

**Spec:** `docs/superpowers/specs/2026-03-17-container-utils-library-design.md`

---

## Chunk 1: Infrastructure + Library Scaffold + source_gpu_config + register_container

### Task 1: Move GPU_config to /etc/llm_code/

**Files:**
- Delete: `update_scripts/GPU_config`
- Create (system): `/etc/llm_code/GPU_config`

- [ ] **Step 1: Create system directory and copy file**

```bash
sudo mkdir -p /etc/llm_code
sudo cp update_scripts/GPU_config /etc/llm_code/GPU_config
sudo chmod 644 /etc/llm_code/GPU_config
cat /etc/llm_code/GPU_config
```

Expected: file content with GPU0–GPU4 variables printed.

- [ ] **Step 2: Remove old file from repo**

```bash
git rm update_scripts/GPU_config
```

Note: `/etc/llm_code/GPU_config` is a system file outside the repo and is not committed. Only the deletion of `update_scripts/GPU_config` is committed.

- [ ] **Step 3: Commit**

```bash
git commit -m "Feat: Move GPU_config to /etc/llm_code/"
```

---

### Task 2: Create library scaffold and bats test file

**Files:**
- Create: `update_scripts/lib/container_utils.sh`
- Create: `update_scripts/tests/test_container_utils.bats`

- [ ] **Step 1: Create directories**

```bash
mkdir -p update_scripts/lib update_scripts/tests
```

- [ ] **Step 2: Write failing test for bash version check**

Create `update_scripts/tests/test_container_utils.bats`:

```bash
#!/usr/bin/env bats

LIB="${BATS_TEST_DIRNAME}/../lib/container_utils.sh"

setup() {
    # Reset global state by re-sourcing the library each test
    # shellcheck disable=SC1090
    source "$LIB"
}

# --- bash version check ---

@test "library loads successfully under bash 4.3+" {
    run bash -c "source '${LIB}' && echo loaded"
    [ "$status" -eq 0 ]
    [[ "$output" == *"loaded"* ]]
}
```

- [ ] **Step 3: Run test to verify it fails (library doesn't exist yet)**

```bash
bats update_scripts/tests/test_container_utils.bats
```

Expected: FAIL — "No such file or directory" or similar.

- [ ] **Step 4: Write minimal library scaffold**

Create `update_scripts/lib/container_utils.sh`:

```bash
# container_utils.sh
# version: 1.0.0
# Shared library for container update scripts. Source this file; do not execute directly.
#
# History
#   1.0.0 - 2026-03-17,     Initial release
#

# Require bash 4.3+ for declare -n nameref support
if (( BASH_VERSINFO[0] < 4 || (BASH_VERSINFO[0] == 4 && BASH_VERSINFO[1] < 3) )); then
    echo "[ERROR] container_utils.sh requires bash 4.3+" >&2
    return 1 2>/dev/null || exit 1
fi

# --- Internal state (reset on each source) ---
_CONTAINER_NAMES=()
declare -gA _CONTAINER_IMAGES=()
declare -g _RUN_UPDATES_CALLED=false
declare -g _VAULT_TOKEN=""
# Overridable in tests:
declare -g _VAULT_ADDR_FILE="/etc/vault/vault_addr"
declare -g _VAULT_CREDS_DIR="/etc/vault/host"
```

- [ ] **Step 5: Run test to verify it passes**

```bash
bats update_scripts/tests/test_container_utils.bats
```

Expected: PASS — 1 test.

- [ ] **Step 6: Commit**

```bash
git add update_scripts/lib/container_utils.sh update_scripts/tests/test_container_utils.bats
git commit -m "Feat: Add container_utils library scaffold and bats test file"
```

---

### Task 3: Implement source_gpu_config

**Files:**
- Modify: `update_scripts/lib/container_utils.sh`
- Modify: `update_scripts/tests/test_container_utils.bats`

- [ ] **Step 1: Write failing tests for source_gpu_config**

Append to `update_scripts/tests/test_container_utils.bats`:

```bash
# --- source_gpu_config ---

@test "source_gpu_config loads GPU variables from default path /etc/llm_code/GPU_config" {
    # Requires /etc/llm_code/GPU_config to exist on the system
    run bash -c "source '${LIB}'; source_gpu_config; echo GPU0=\$GPU0"
    [ "$status" -eq 0 ]
    [[ "$output" == GPU0=* ]]
}

@test "source_gpu_config loads GPU variables from explicit path" {
    local tmpfile
    tmpfile="$(mktemp)"
    echo 'GPU0="test-gpu-uuid"' > "$tmpfile"
    run bash -c "source '${LIB}'; source_gpu_config '$tmpfile'; echo GPU0=\$GPU0"
    rm -f "$tmpfile"
    [ "$status" -eq 0 ]
    [[ "$output" == "GPU0=test-gpu-uuid" ]]
}

@test "source_gpu_config exits non-zero for missing file" {
    run bash -c "source '${LIB}'; source_gpu_config /nonexistent/GPU_config"
    [ "$status" -ne 0 ]
    [[ "$output" == *"[ERROR]"* ]]
}

@test "source_gpu_config treats empty string path as default" {
    local tmpfile
    tmpfile="$(mktemp)"
    echo 'GPU0="fallback-gpu-uuid"' > "$tmpfile"
    # Override the default path by providing it explicitly, then verify empty string
    # falls back identically to the no-argument case by checking output is the same
    local result_no_arg result_empty_arg
    result_no_arg=$(bash -c "source '${LIB}'; source_gpu_config '$tmpfile'; echo \$GPU0" 2>/dev/null || true)
    result_empty_arg=$(bash -c "source '${LIB}'; source_gpu_config ''; echo \$GPU0" 2>/dev/null || true)
    # Both should either succeed with same GPU0 (if /etc/llm_code/GPU_config exists)
    # or both fail with [ERROR] — either way, empty-string behaviour must match no-arg behaviour
    # At minimum, empty-string must resolve to /etc/llm_code/GPU_config (not crash differently)
    run bash -c "source '${LIB}'; source_gpu_config '' 2>&1; echo exit:\$?"
    # Must not produce a bash error about empty path — only [ERROR] if file is missing
    [[ "$output" != *"syntax error"* ]]
    [[ "$output" != *"unbound variable"* ]]
    rm -f "$tmpfile"
}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
bats update_scripts/tests/test_container_utils.bats
```

Expected: FAIL on the new tests — "source_gpu_config: command not found".

- [ ] **Step 3: Implement source_gpu_config**

Append to `update_scripts/lib/container_utils.sh`:

```bash
# source_gpu_config [path]
# Sources GPU UUID variables from GPU_config file.
# Defaults to /etc/llm_code/GPU_config if no path given.
source_gpu_config() {
    local config_path="${1:-}"
    if [[ -z "$config_path" ]]; then
        config_path="/etc/llm_code/GPU_config"
    fi
    if [[ ! -f "$config_path" ]]; then
        echo "[ERROR] GPU_config not found: $config_path" >&2
        return 1
    fi
    # shellcheck disable=SC1090
    source "$config_path"
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
bats update_scripts/tests/test_container_utils.bats
```

Expected: PASS — all tests (the default-path test requires `/etc/llm_code/GPU_config` to exist from Task 1).

- [ ] **Step 5: Commit**

```bash
git add update_scripts/lib/container_utils.sh update_scripts/tests/test_container_utils.bats
git commit -m "Feat: Implement source_gpu_config in container_utils"
```

---

### Task 4: Implement register_container

**Files:**
- Modify: `update_scripts/lib/container_utils.sh`
- Modify: `update_scripts/tests/test_container_utils.bats`

- [ ] **Step 1: Write failing tests for register_container**

Append to `update_scripts/tests/test_container_utils.bats`:

```bash
# --- register_container ---

@test "register_container stores name and image" {
    register_container "myapp" "myimage:latest"
    [ "${_CONTAINER_NAMES[0]}" = "myapp" ]
    [ "${_CONTAINER_IMAGES[myapp]}" = "myimage:latest" ]
}

@test "register_container stores docker options" {
    register_container "myapp" "myimage:latest" -p 8080:80 --restart always
    [ "${_CONTAINER_OPTS_myapp[0]}" = "-p" ]
    [ "${_CONTAINER_OPTS_myapp[1]}" = "8080:80" ]
    [ "${_CONTAINER_OPTS_myapp[2]}" = "--restart" ]
    [ "${_CONTAINER_OPTS_myapp[3]}" = "always" ]
}

@test "register_container sanitizes hyphens in name for array variable" {
    register_container "open-webui" "ghcr.io/open-webui/open-webui:main" -p 4000:8080
    [ "${_CONTAINER_NAMES[0]}" = "open-webui" ]
    [ "${_CONTAINER_IMAGES[open_webui]}" = "ghcr.io/open-webui/open-webui:main" ]
    [ "${_CONTAINER_OPTS_open_webui[0]}" = "-p" ]
}

@test "register_container supports multiple containers" {
    register_container "app1" "img1:latest"
    register_container "app2" "img2:latest"
    [ "${#_CONTAINER_NAMES[@]}" -eq 2 ]
    [ "${_CONTAINER_NAMES[1]}" = "app2" ]
}

@test "register_container exits non-zero after run_updates was called" {
    _RUN_UPDATES_CALLED=true
    run register_container "late" "img:tag"
    [ "$status" -ne 0 ]
    [[ "$output" == *"[ERROR]"* ]]
}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
bats update_scripts/tests/test_container_utils.bats
```

Expected: FAIL on new tests.

- [ ] **Step 3: Implement register_container**

Append to `update_scripts/lib/container_utils.sh`:

```bash
# register_container <name> <image> [docker_opts...]
# Registers a container for the next run_updates call.
# -d and --name are added automatically by run_updates; do not include them here.
register_container() {
    if [[ "$_RUN_UPDATES_CALLED" == true ]]; then
        echo "[ERROR] register_container called after run_updates" >&2
        return 1
    fi

    local name="$1"
    local image="$2"
    shift 2
    local sanitized="${name//-/_}"

    _CONTAINER_NAMES+=("$name")
    _CONTAINER_IMAGES["$sanitized"]="$image"

    # Dynamically declare and populate a global array for this container's options.
    # shellcheck disable=SC2178
    declare -ga "_CONTAINER_OPTS_${sanitized}"
    local -n _cu_reg_ref="_CONTAINER_OPTS_${sanitized}"
    _cu_reg_ref=("$@")
    unset -n _cu_reg_ref
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
bats update_scripts/tests/test_container_utils.bats
```

Expected: PASS — all tests.

- [ ] **Step 5: Run shellcheck on library**

```bash
shellcheck -s bash update_scripts/lib/container_utils.sh
```

Expected: zero warnings. Fix any before committing.

- [ ] **Step 6: Commit**

```bash
git add update_scripts/lib/container_utils.sh update_scripts/tests/test_container_utils.bats
git commit -m "Feat: Implement register_container in container_utils"
```

> **Note:** `update_scripts/CHANGELOG.md` is updated in Chunk 3, Task 10, after all library and script work is complete.

---

## Chunk 2: get_secret + run_updates + shellcheck

### Task 5: Implement get_secret

**Files:**
- Modify: `update_scripts/lib/container_utils.sh`
- Modify: `update_scripts/tests/test_container_utils.bats`

The tests mock the `vault` command by creating a fake executable in a temp bin directory prepended to PATH.

- [ ] **Step 1: Write failing tests for get_secret**

Append to `update_scripts/tests/test_container_utils.bats`:

```bash
# --- get_secret ---
# Tests override _VAULT_ADDR_FILE and _VAULT_CREDS_DIR (state vars in the library)
# and inject a mock vault binary via PATH. Everything runs in bash -c subshells
# to isolate state and capture stderr alongside stdout.

@test "get_secret returns secret value from vault" {
    local mock_bin vault_dir
    mock_bin="$(mktemp -d)"
    vault_dir="$(mktemp -d)"
    echo "http://127.0.0.1:8200" > "$vault_dir/vault_addr"
    mkdir -p "$vault_dir/host"
    echo "test-role-id"   > "$vault_dir/host/role_id"
    echo "test-secret-id" > "$vault_dir/host/secret_id"
    cat > "$mock_bin/vault" << 'EOF'
#!/usr/bin/env bash
if [[ "$1" == "write" ]]; then echo "test-token"; exit 0; fi
if [[ "$1" == "kv"    ]]; then echo "my-secret-value"; exit 0; fi
EOF
    chmod +x "$mock_bin/vault"

    run bash -c "
        export PATH='$mock_bin:\$PATH'
        source '${LIB}'
        _VAULT_ADDR_FILE='$vault_dir/vault_addr'
        _VAULT_CREDS_DIR='$vault_dir/host'
        get_secret 'mykey' 2>/dev/null
    "
    [ "$status" -eq 0 ]
    [ "$output" = "my-secret-value" ]
    rm -rf "$mock_bin" "$vault_dir"
}

@test "get_secret exits non-zero when vault_addr file is missing" {
    local mock_bin vault_dir
    mock_bin="$(mktemp -d)"
    vault_dir="$(mktemp -d)"
    # vault_addr intentionally NOT created

    run bash -c "
        export PATH='$mock_bin:\$PATH'
        source '${LIB}'
        _VAULT_ADDR_FILE='$vault_dir/vault_addr'
        _VAULT_CREDS_DIR='$vault_dir/host'
        get_secret 'mykey' 2>&1
    "
    [ "$status" -ne 0 ]
    [[ "$output" == *"[ERROR]"* ]]
    rm -rf "$mock_bin" "$vault_dir"
}

@test "get_secret caches vault token — vault write called only once for two calls" {
    local mock_bin vault_dir call_count_file
    mock_bin="$(mktemp -d)"
    vault_dir="$(mktemp -d)"
    call_count_file="$(mktemp)"
    echo "0" > "$call_count_file"
    echo "http://127.0.0.1:8200" > "$vault_dir/vault_addr"
    mkdir -p "$vault_dir/host"
    echo "test-role-id"   > "$vault_dir/host/role_id"
    echo "test-secret-id" > "$vault_dir/host/secret_id"
    cat > "$mock_bin/vault" << EOF
#!/usr/bin/env bash
if [[ "\$1" == "write" ]]; then
    count=\$(cat "$call_count_file")
    echo \$((count + 1)) > "$call_count_file"
    echo "cached-token"
    exit 0
fi
if [[ "\$1" == "kv" ]]; then echo "value"; exit 0; fi
EOF
    chmod +x "$mock_bin/vault"

    run bash -c "
        export PATH='$mock_bin:\$PATH'
        source '${LIB}'
        _VAULT_ADDR_FILE='$vault_dir/vault_addr'
        _VAULT_CREDS_DIR='$vault_dir/host'
        get_secret 'key1' >/dev/null 2>/dev/null
        get_secret 'key2' >/dev/null 2>/dev/null
        cat '$call_count_file'
    "
    [ "$status" -eq 0 ]
    [ "$output" -eq 1 ]
    rm -rf "$mock_bin" "$vault_dir"
    rm -f "$call_count_file"
}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
bats update_scripts/tests/test_container_utils.bats
```

Expected: FAIL on new tests — `get_secret: command not found`.

- [ ] **Step 3: Implement get_secret**

Append to `update_scripts/lib/container_utils.sh`:

```bash
# get_secret <name>
# Fetches secret from Vault path secret/hosts/<hostname>/<name>.
# Vault login is performed lazily on first call; token is cached in _VAULT_TOKEN.
# Only the secret value is written to stdout; all diagnostics go to stderr.
get_secret() {
    local name="$1"

    if [[ -z "$_VAULT_TOKEN" ]]; then
        [[ -f "$_VAULT_ADDR_FILE" && -s "$_VAULT_ADDR_FILE" ]] \
            || { echo "[ERROR] Vault address file not found: $_VAULT_ADDR_FILE" >&2; exit 1; }
        [[ -f "$_VAULT_CREDS_DIR/role_id" ]] \
            || { echo "[ERROR] role_id not found in $_VAULT_CREDS_DIR" >&2; exit 1; }
        [[ -f "$_VAULT_CREDS_DIR/secret_id" ]] \
            || { echo "[ERROR] secret_id not found in $_VAULT_CREDS_DIR" >&2; exit 1; }

        local vault_addr
        vault_addr=$(cat "$_VAULT_ADDR_FILE")
        export VAULT_ADDR="$vault_addr"

        _VAULT_TOKEN=$(vault write -field=token auth/approle/login \
            role_id="$(cat "$_VAULT_CREDS_DIR/role_id")" \
            secret_id="$(cat "$_VAULT_CREDS_DIR/secret_id")") \
            || { echo "[ERROR] Vault login failed" >&2; exit 1; }
        export VAULT_TOKEN="$_VAULT_TOKEN"
    fi

    vault kv get -field=value "secret/hosts/$(hostname)/${name}" \
        || { echo "[ERROR] Failed to get secret: $name" >&2; exit 1; }
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
bats update_scripts/tests/test_container_utils.bats
```

Expected: PASS — all tests (vault token caching test verifies `vault write` called exactly once).

- [ ] **Step 5: Commit**

```bash
git add update_scripts/lib/container_utils.sh update_scripts/tests/test_container_utils.bats
git commit -m "Feat: Implement get_secret in container_utils"
```

---

### Task 6: Implement run_updates

**Files:**
- Modify: `update_scripts/lib/container_utils.sh`
- Modify: `update_scripts/tests/test_container_utils.bats`

Tests mock the `docker` command via a fake executable in a temp bin directory.

- [ ] **Step 1: Write failing tests for run_updates**

Append to `update_scripts/tests/test_container_utils.bats`:

```bash
# Note: run_updates sends all log output to stderr. Tests use bash -c subshells
# with 2>&1 to merge stderr into stdout so bats $output captures log messages.
# register_container is called inside the subshell to keep state consistent.

@test "run_updates with no containers logs WARN and returns 0" {
    local mock_bin
    mock_bin="$(mktemp -d)"
    run bash -c "
        export PATH='$mock_bin:\$PATH'
        source '${LIB}'
        run_updates 2>&1
    "
    [ "$status" -eq 0 ]
    [[ "$output" == *"[WARN]"* ]]
    [[ "$output" == *"No containers registered"* ]]
    rm -rf "$mock_bin"
}

@test "run_updates skips restart when image unchanged and container running" {
    local mock_bin flag_file
    mock_bin="$(mktemp -d)"
    flag_file="$(mktemp)"
    rm "$flag_file"
    cat > "$mock_bin/docker" << EOF
#!/usr/bin/env bash
case "\$1 \$2" in
    "image inspect"*) echo "sha256:same" ;;
    "pull"*)          echo "Status: up to date" ;;
    "ps"*)            echo "running123" ;;
    "image prune"*)   echo "pruned"; exit 0 ;;
    *)                exit 0 ;;
esac
EOF
    chmod +x "$mock_bin/docker"
    run bash -c "
        export PATH='$mock_bin:\$PATH'
        source '${LIB}'
        register_container 'myapp' 'img:latest' --restart always
        run_updates 2>&1
    "
    [ "$status" -eq 0 ]
    [[ "$output" == *"up-to-date"* ]]
    rm -rf "$mock_bin"
}

@test "run_updates restarts container when image changes" {
    local mock_bin flag_file
    mock_bin="$(mktemp -d)"
    flag_file="${mock_bin}/pulled"
    cat > "$mock_bin/docker" << EOF
#!/usr/bin/env bash
case "\$1 \$2" in
    "image inspect"*)
        [[ -f "$flag_file" ]] && echo "sha256:new" || echo "sha256:old" ;;
    "pull"*)
        touch "$flag_file"; echo "Status: Pull complete" ;;
    "ps"*)       echo "running123" ;;
    "inspect"*)  exit 0 ;;
    "stop"*)     exit 0 ;;
    "rm"*)       exit 0 ;;
    "run"*)      echo "newid"; exit 0 ;;
    "image prune"*) echo "pruned"; exit 0 ;;
    *)           exit 0 ;;
esac
EOF
    chmod +x "$mock_bin/docker"
    run bash -c "
        export PATH='$mock_bin:\$PATH'
        source '${LIB}'
        register_container 'myapp' 'img:latest' --restart always
        run_updates 2>&1
    "
    [ "$status" -eq 0 ]
    [[ "$output" == *"[STOP]"* ]]
    [[ "$output" == *"[RUN]"* ]]
    [[ "$output" == *"Image prune complete"* ]]
    rm -rf "$mock_bin"
}

@test "run_updates starts container when not running even if image unchanged" {
    local mock_bin
    mock_bin="$(mktemp -d)"
    cat > "$mock_bin/docker" << 'EOF'
#!/usr/bin/env bash
case "$1 $2" in
    "image inspect"*) echo "sha256:same" ;;
    "pull"*)          echo "Status: up to date" ;;
    "ps"*)            echo "" ;;   # not running
    "inspect"*)       exit 1 ;;   # does not exist
    "run"*)           echo "newid"; exit 0 ;;
    "image prune"*)   echo "pruned"; exit 0 ;;
    *)                exit 0 ;;
esac
EOF
    chmod +x "$mock_bin/docker"
    run bash -c "
        export PATH='$mock_bin:\$PATH'
        source '${LIB}'
        register_container 'myapp' 'img:latest' --restart always
        run_updates 2>&1
    "
    [ "$status" -eq 0 ]
    [[ "$output" == *"[RUN]"* ]]
    rm -rf "$mock_bin"
}

@test "run_updates sets non-zero exit and skips prune on pull failure" {
    local mock_bin
    mock_bin="$(mktemp -d)"
    cat > "$mock_bin/docker" << 'EOF'
#!/usr/bin/env bash
case "$1 $2" in
    "image inspect"*) echo "sha256:old" ;;
    "pull"*)          echo "Error: pull failed"; exit 1 ;;
    *)                exit 0 ;;
esac
EOF
    chmod +x "$mock_bin/docker"
    run bash -c "
        export PATH='$mock_bin:\$PATH'
        source '${LIB}'
        register_container 'myapp' 'img:latest'
        run_updates 2>&1
    "
    [ "$status" -ne 0 ]
    [[ "$output" == *"[ERROR]"* ]]
    [[ "$output" != *"Image prune"* ]]
    rm -rf "$mock_bin"
}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
bats update_scripts/tests/test_container_utils.bats
```

Expected: FAIL on new tests — `run_updates: command not found`.

- [ ] **Step 3: Implement run_updates**

Append to `update_scripts/lib/container_utils.sh`:

```bash
# run_updates
# Drives the full update lifecycle for all registered containers.
# Runs docker image prune once at end if all updates succeeded.
# Must be called exactly once per script.
run_updates() {
    _RUN_UPDATES_CALLED=true

    if [[ "${#_CONTAINER_NAMES[@]}" -eq 0 ]]; then
        echo "[WARN] No containers registered." >&2
        return 0
    fi

    local _all_ok=true

    for name in "${_CONTAINER_NAMES[@]}"; do
        local sanitized="${name//-/_}"
        local image="${_CONTAINER_IMAGES[$sanitized]}"

        # Record old image ID
        local old_id
        old_id=$(docker image inspect "$image" --format '{{.Id}}' 2>/dev/null || echo "")

        # Pull image
        local pull_out pull_rc
        pull_out=$(docker pull "$image" 2>&1)
        pull_rc=$?

        if (( pull_rc != 0 )); then
            echo "[ERROR] docker pull failed for $image (exit $pull_rc)" >&2
            echo "$pull_out" >&2
            _all_ok=false
            continue
        fi

        # Record new image ID
        local new_id
        new_id=$(docker image inspect "$image" --format '{{.Id}}')

        # Check if container is running
        local container_running=false
        if [[ -n "$(docker ps -q -f "name=$name" 2>/dev/null)" ]]; then
            container_running=true
        fi

        if [[ "$old_id" != "$new_id" ]] || [[ "$container_running" == false ]]; then
            # Stop and remove if container exists
            if docker inspect "$name" >/dev/null 2>&1; then
                echo "[STOP] Stopping container $name ..." >&2
                docker stop "$name" 2>/dev/null || true
                docker rm   "$name" 2>/dev/null || true
            fi

            # Start container using nameref to options array
            echo "[RUN] Starting new container $name ..." >&2
            # shellcheck disable=SC2178
            declare -n _cu_opts_ref="_CONTAINER_OPTS_${sanitized}"
            if docker run -d --name "$name" "${_cu_opts_ref[@]}" "$image" >/dev/null; then
                echo "[OK] $name started." >&2
            else
                echo "[ERROR] Failed to start $name" >&2
                _all_ok=false
            fi
            unset -n _cu_opts_ref
        else
            echo "[OK] $name is up-to-date, skipping restart." >&2
        fi
    done

    if [[ "$_all_ok" == true ]]; then
        docker image prune -f >/dev/null
        echo "[OK] Image prune complete." >&2
    else
        echo "[WARN] Skipping image prune due to update errors." >&2
        exit 1
    fi
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
bats update_scripts/tests/test_container_utils.bats
```

Expected: PASS — all tests.

- [ ] **Step 5: Commit**

```bash
git add update_scripts/lib/container_utils.sh update_scripts/tests/test_container_utils.bats
git commit -m "Feat: Implement run_updates in container_utils"
```

---

### Task 7: Run shellcheck on library

**Files:**
- Modify: `update_scripts/lib/container_utils.sh` (fix any warnings)

- [ ] **Step 1: Run shellcheck**

```bash
shellcheck -s bash update_scripts/lib/container_utils.sh
```

Expected: zero warnings. Fix any that appear before proceeding. Common issues to expect:
- SC1090 (non-constant source) — add `# shellcheck disable=SC1090` above `source "$config_path"`
- SC2034 (unused variable) on `declare -ga` — add `# shellcheck disable=SC2034`
- SC2178 (nameref warning) — already noted in code with disable comments

- [ ] **Step 2: Commit if any fixes were needed**

```bash
git add update_scripts/lib/container_utils.sh
git commit -m "Style: Fix shellcheck warnings in container_utils"
```

---

## Chunk 3: Script Refactoring + CHANGELOG

### Task 8: Refactor update_ollama.sh

**Files:**
- Modify: `update_scripts/update_ollama.sh`

- [ ] **Step 1: Replace file content entirely**

Write `update_scripts/update_ollama.sh` with this exact content:

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

# shellcheck source=lib/container_utils.sh
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

Note: `# shellcheck source=lib/container_utils.sh` tells shellcheck where the sourced file is so it can follow it.

- [ ] **Step 2: Run shellcheck**

```bash
shellcheck -s bash update_scripts/update_ollama.sh
```

Expected: zero warnings.

- [ ] **Step 3: Verify no open-webui references remain**

```bash
grep -i "open.webui\|open_webui" update_scripts/update_ollama.sh && echo "FAIL: references found" || echo "OK: no references"
```

Expected: `OK: no references`

- [ ] **Step 4: Commit**

```bash
git add update_scripts/update_ollama.sh
git commit -m "Feat: Refactor update_ollama.sh to use library"
```

---

### Task 9: Refactor update_open-webui.sh

**Files:**
- Modify: `update_scripts/update_open-webui.sh`

- [ ] **Step 1: Replace file content entirely**

Write `update_scripts/update_open-webui.sh` with this exact content:

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

# shellcheck source=lib/container_utils.sh
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

- [ ] **Step 2: Run shellcheck**

```bash
shellcheck -s bash update_scripts/update_open-webui.sh
```

Expected: zero warnings.

- [ ] **Step 3: Commit**

```bash
git add update_scripts/update_open-webui.sh
git commit -m "Feat: Refactor update_open-webui.sh to use library"
```

---

### Task 10: Update CHANGELOG.md and final checks

**Files:**
- Modify: `update_scripts/CHANGELOG.md`

- [ ] **Step 1: Prepend new entry to CHANGELOG.md**

Add the following at the top of the file, after the `# Changelog` and intro lines:

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

- [ ] **Step 2: Run full bats test suite**

```bash
bats update_scripts/tests/test_container_utils.bats
```

Expected: PASS — all tests.

- [ ] **Step 3: Run shellcheck on all three bash files**

```bash
shellcheck -s bash \
    update_scripts/lib/container_utils.sh \
    update_scripts/update_ollama.sh \
    update_scripts/update_open-webui.sh
```

Expected: zero warnings across all three files.

- [ ] **Step 4: Commit**

```bash
git add update_scripts/CHANGELOG.md
git commit -m "Docs: Update CHANGELOG for 2.0.0 refactor"
```
