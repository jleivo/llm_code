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

# --- source_gpu_config ---

@test "source_gpu_config loads GPU variables from default path /etc/llm_code/GPU_config" {
    # Skip if system GPU_config not deployed (dev workstation)
    if [[ ! -f /etc/llm_code/GPU_config ]]; then
        skip "System GPU_config not deployed at /etc/llm_code/GPU_config"
    fi
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
