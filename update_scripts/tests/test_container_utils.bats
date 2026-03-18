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
