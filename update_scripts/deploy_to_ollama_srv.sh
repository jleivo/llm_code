#!/bin/bash
#
# Author: Juha Leivo
# Version: 1.0.1
# Date: 2026-03-18
#
# Deploy script(s) to server, updating only if changed.
#
# History
#   1.0.0 - 2026-03-17, deploy container_utils library, update scripts, and GPU_config
#   1.0.1 - 2026-03-18, sudo fallback for remote mkdir when permission denied

tgt_server="ollama.intra.leivo"
ssh_user="juha"
# files_to_update can contain space-separated entries. Each entry may be:
#   src                 -> copied to remote as ~/.local/bin/$(basename src)
#   src:dest            -> copied to remote path 'dest' (as provided)
# Local src paths may be absolute or relative to this repository root.
files_to_update='update_ollama.sh:~/.local/bin/ lib/container_utils.sh:~/.local/bin/lib/ GPU_config:/etc/llm_code/GPU_config'

# test can one connect
if ping -c 1 -W 1 $tgt_server |grep "^rtt" > /dev/null; then
    echo "$tgt_server is reachable"
else
    echo "Error: $tgt_server is not reachable"
    exit 1
fi

# Default to dry-run. Pass --apply or --commit to perform changes.
DRY_RUN=1
while [ "$#" -gt 0 ]; do
    case "$1" in
        --apply|--commit)
            DRY_RUN=0
            shift ;;
        --help|-h)
            echo "Usage: $0 [--apply|--commit]"
            echo "Default is dry-run (no changes). Use --apply to perform changes."
            exit 0
            ;;
        *)
            echo "Unknown argument: $1"
            exit 1
            ;;
    esac
done

# get remote home directory for correct absolute paths (do it even in dry-run so we can show expanded paths)
remote_home=$(ssh "$ssh_user@$tgt_server" 'echo $HOME' 2>/dev/null || echo "")
if [ -z "$remote_home" ]; then
    echo "Error: could not determine remote HOME for $tgt_server"
    exit 1
fi

declare -a failures=()
declare -a planned_actions=()
declare -a performed_actions=()

# Helper: resolve local path to an absolute path inside this repo when possible
repo_root="$(cd "$(dirname "$0")" && pwd)"

for entry in $files_to_update; do
    # parse src:dest or plain src
    src="$entry"
    dest=""
    if [[ "$entry" == *":"* ]]; then
        src="${entry%%:*}"
        dest="${entry#*:}"
    fi

    # if src is relative, make it relative to repo_root
    if [[ ! "$src" = /* ]]; then
        src="$repo_root/$src"
    fi

    if [ ! -e "$src" ]; then
        msg="source file $src does not exist, skipping"
        echo "Warning: $msg"
        failures+=("$msg")
        continue
    fi

    # default remote destination if not provided
        if [ -z "$dest" ]; then
            dest="$HOME/.local/bin/$(basename "$src")"
    fi

    echo "Checking $src -> $dest"

    # compute local md5
    src_md5=$(md5sum "$src" | awk '{print $1}')

    # expand leading ~ to remote_home so we have absolute remote paths
    if [[ "$dest" == ~* ]]; then
        dest="${dest/#~/$remote_home}"
    fi

    # determine remote target path and remote directory
    if [[ "$dest" == */ ]]; then
        # dest is a directory (possibly with trailing slash)
        remote_dir="${dest%/}"
        remote_target="$remote_dir/$(basename "$src")"
    else
        remote_target="$dest"
        # derive directory portion
        remote_dir="$(dirname "$dest")"
    fi

    # If dest was empty (shouldn't happen here), fallback
    if [ -z "$remote_target" ]; then
        remote_target="$HOME/.local/bin/$(basename "$src")"
        remote_dir="$HOME/.local/bin"
    fi

    # Ensure remote directory exists (or plan to)
    # shellcheck disable=SC2029
    if ssh "$ssh_user@$tgt_server" "[ -d $remote_dir ]"; then
        # Directory already exists; no action needed
        :
    else
        planned_actions+=("ensure remote directory $remote_dir on $tgt_server")
        if [ $DRY_RUN -eq 0 ]; then
            if ! mkdir_out=$(ssh "$ssh_user@$tgt_server" "mkdir -p $remote_dir" 2>&1); then
                echo "mkdir failed, retrying with sudo"
                if ! ssh -t "$ssh_user@$tgt_server" "sudo mkdir -p $remote_dir" 2>&1; then
                    msg="Failed to create remote directory $remote_dir on $tgt_server: $mkdir_out"
                    echo "Error: $msg"
                    failures+=("$msg")
                    continue
                fi
            fi
            performed_actions+=("created remote directory $remote_dir on $tgt_server")
        fi
    fi
    # compute remote md5 for the target path (silently handle missing file)
    remote_md5=$(ssh "$ssh_user@$tgt_server" md5sum "$remote_target" 2>/dev/null | awk '{print $1}' || echo "")

    if [ -z "$remote_md5" ] || [ "$remote_md5" != "$src_md5" ]; then
        echo "Copying updated $(basename "$src") to $tgt_server:$remote_target"
        planned_actions+=("copy $src -> $tgt_server:$remote_target and chmod +x")
        if [ $DRY_RUN -eq 0 ]; then
            scp_out=$(scp "$src" "$ssh_user@$tgt_server":"$remote_target" 2>&1)
            if [ $? -ne 0 ]; then
                original_msg="scp failed for $src -> $remote_target: $scp_out"
                echo "Error: $original_msg"
                # Attempt fallback: copy to /tmp and move with sudo (interactive sudo prompt)
                fallback_target="/tmp/$(basename "$src")"
                echo "Attempting fallback copy to $tgt_server:$fallback_target"
                scp_fallback_out=$(scp "$src" "$ssh_user@$tgt_server":"$fallback_target" 2>&1)
                if [ $? -eq 0 ]; then
                    echo "Fallback copy succeeded, moving to final destination with sudo"
                    # Allocate a pseudo-tty for sudo password prompt
                    ssh -t "$ssh_user@$tgt_server" "sudo mv $fallback_target $remote_target && sudo chmod +x $remote_target"
                    if [ $? -ne 0 ]; then
                        fallback_msg="fallback sudo mv/chmod failed for $fallback_target -> $remote_target"
                        echo "Error: $fallback_msg"
                        failures+=("$original_msg" "$fallback_msg")
                    else
                        performed_actions+=("fallback copy and sudo mv $fallback_target -> $remote_target")
                    fi
                else
                    fallback_msg="fallback scp also failed for $src -> $fallback_target: $scp_fallback_out"
                    echo "Error: $fallback_msg"
                    failures+=("$original_msg" "$fallback_msg")
                fi
                continue
            fi
            performed_actions+=("copied $src -> $tgt_server:$remote_target")
            chmod_out=$(ssh "$ssh_user@$tgt_server" chmod +x "$remote_target" 2>&1) || true
            if [ $? -ne 0 ]; then
                msg="chmod failed for $remote_target on $tgt_server: $chmod_out"
                echo "Warning: $msg"
                failures+=("$msg")
            else
                performed_actions+=("chmod +x $remote_target on $tgt_server")
            fi
        fi
    else
        echo "$(basename "$src") on $tgt_server is up to date"
    fi
done

echo
if [ $DRY_RUN -eq 1 ]; then
    echo "Dry-run summary: planned actions (${#planned_actions[@]}):"
    for a in "${planned_actions[@]}"; do
        echo " - $a"
    done
    if [ ${#failures[@]} -ne 0 ]; then
        echo
        echo "Dry-run noted ${#failures[@]} issue(s):"
        for f in "${failures[@]}"; do
            echo " - $f"
        done
        exit 2
    else
        echo
        echo "Dry-run complete: no immediate errors detected"
        exit 0
    fi
else
    echo "Execution summary: performed actions (${#performed_actions[@]}):"
    for a in "${performed_actions[@]}"; do
        echo " - $a"
    done
    if [ ${#failures[@]} -ne 0 ]; then
        echo
        echo "Deployment completed with ${#failures[@]} failure(s):"
        for f in "${failures[@]}"; do
            echo " - $f"
        done
        exit 2
    else
        echo
        echo "Deployment completed successfully"
        exit 0
    fi
fi
