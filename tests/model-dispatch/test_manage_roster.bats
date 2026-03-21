#!/usr/bin/env bats

setup() {
    export TEST_AGENTS_DIR="$(mktemp -d)"
    export AGENTS_DIR="$TEST_AGENTS_DIR"
    export SCRIPT="$HOME/.agents/skills/model-dispatch/scripts/manage-roster.sh"
}

teardown() {
    rm -rf "$TEST_AGENTS_DIR"
}

@test "list shows empty roster" {
    run bash "$SCRIPT" list
    [ "$status" -eq 0 ]
    [[ "$output" == *"No models"* ]] || [[ "$output" == *"empty"* ]]
}

@test "add creates agent file" {
    run bash "$SCRIPT" add test-model "test-model-id:latest"
    [ "$status" -eq 0 ]
    [ -f "$TEST_AGENTS_DIR/test-model.md" ]
}

@test "add substitutes short name in agent file" {
    bash "$SCRIPT" add test-model "test-model-id:latest"
    run grep "name: test-model" "$TEST_AGENTS_DIR/test-model.md"
    [ "$status" -eq 0 ]
}

@test "add substitutes model id in agent file" {
    bash "$SCRIPT" add test-model "test-model-id:latest"
    run grep "model: test-model-id:latest" "$TEST_AGENTS_DIR/test-model.md"
    [ "$status" -eq 0 ]
}

@test "add overwrites existing entry" {
    bash "$SCRIPT" add test-model "old-model:v1"
    bash "$SCRIPT" add test-model "new-model:v2"
    run grep "model: new-model:v2" "$TEST_AGENTS_DIR/test-model.md"
    [ "$status" -eq 0 ]
}

@test "add rejects invalid short name with uppercase" {
    run bash "$SCRIPT" add "BadName" "model:latest"
    [ "$status" -ne 0 ]
    [[ "$output" == *"must match"* ]] || [[ "$output" == *"invalid"* ]]
}

@test "add rejects invalid short name with spaces" {
    run bash "$SCRIPT" add "bad name" "model:latest"
    [ "$status" -ne 0 ]
}

@test "add rejects empty model id" {
    run bash "$SCRIPT" add "good-name" ""
    [ "$status" -ne 0 ]
}

@test "add rejects missing arguments" {
    run bash "$SCRIPT" add
    [ "$status" -ne 0 ]
}

@test "remove deletes agent file" {
    bash "$SCRIPT" add test-model "test-model-id:latest"
    run bash "$SCRIPT" remove test-model
    [ "$status" -eq 0 ]
    [ ! -f "$TEST_AGENTS_DIR/test-model.md" ]
}

@test "remove nonexistent model fails" {
    run bash "$SCRIPT" remove nonexistent
    [ "$status" -ne 0 ]
}

@test "list shows added models" {
    bash "$SCRIPT" add alpha "alpha-model:v1"
    bash "$SCRIPT" add beta "beta-model:v2"
    run bash "$SCRIPT" list
    [ "$status" -eq 0 ]
    [[ "$output" == *"alpha"* ]]
    [[ "$output" == *"beta"* ]]
}

@test "unknown command fails" {
    run bash "$SCRIPT" unknown
    [ "$status" -ne 0 ]
}

@test "no arguments shows usage" {
    run bash "$SCRIPT"
    [ "$status" -ne 0 ]
    [[ "$output" == *"Usage"* ]]
}
