# container_utils.sh
# version: 1.0.0
# Shared library for container update scripts. Source this file; do not execute directly.
#
# History
#   1.0.0 - 2026-03-18,     Initial release
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
