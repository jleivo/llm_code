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
    # shellcheck disable=SC2317  # exit 1 is reachable when script is executed directly
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
# GPU config path — override for dev/test; production default: /etc/llm_code/GPU_config
declare -g _GPU_CONFIG_FILE="/etc/llm_code/GPU_config"

# source_gpu_config [path]
# Sources GPU UUID variables from GPU_config file.
# If no path given, uses $_GPU_CONFIG_FILE (default: /etc/llm_code/GPU_config).
# Override _GPU_CONFIG_FILE for development/test use.
source_gpu_config() {
    local config_path="${1:-}"
    if [[ -z "$config_path" ]]; then
        config_path="$_GPU_CONFIG_FILE"
    fi
    if [[ ! -f "$config_path" ]]; then
        echo "[ERROR] GPU_config not found: $config_path" >&2
        return 1
    fi
    # shellcheck disable=SC1090
    source "$config_path"
}

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
