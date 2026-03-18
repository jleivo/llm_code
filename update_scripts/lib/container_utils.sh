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
