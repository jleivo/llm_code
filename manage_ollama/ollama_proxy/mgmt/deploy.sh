#!/bin/bash
#
# Author: Juha Leivo
# Version: 1
# Date: 2025-10-05
#
# Description
#   Simple script to deploy the proxy code
#   to the target system using scp.
#
# History
#   1 - 2025-10-05, initial write

################################# FUNCTIONS ####################################
debug=0

function get_arguments() {

  if [[ "${#}" -lt "2" ]] ; then
    print_usage
    return 1
  fi

  while getopts 'd:hv' flag; do
    case "${flag}" in
      d)
        destination="${OPTARG}"
        ;;
      h)
        print_usage
        ;;
      v)
        debug=1
        ;;
      *)
        print_usage
        ;;
    esac
  done
}

function print_usage() {

    echo ''
    echo 'Deploy script'
    echo ''
    echo 'Usage'
    echo ''
    echo '  -d          Full SCP compliant destination. MANDATORY'
    echo '  -v          Print debug output messages'
    echo '  -h          This help message'
    echo ''
    return 0

}

# Takes takes single argument the log message
function log() {

    local  print_to_screen=0

    # if this is interactive shell, print to screen
    if [[ ${-} == *i* ]]
    then
        print_to_screen=1
    fi

    if [[ "${print_to_screen}" -eq 1 ]]; then 
        echo "${1}"
    else
        logger "${0##*/}": "${1}"
    fi
}

function init() {

  local program_fail=0

  # check if we have the programs
  # shellcheck disable=SC2043
  for program in scp; do
    if ! hash "${program}" 2>/dev/null; then
      log "ERROR: command not found in PATH: %s\n ${program}"
      program_fail=1
    fi
  done

  if [[ "${program_fail}" == '1' ]]; then
    return 1
  fi

}

function deploy() {

    local files_to_copy="host_manager.py main.py requirements.txt mgmt/install.sh"
    if [[ debug -eq 1 ]]; then
        log "Files to copy: ${files_to_copy}"
    fi

    log "Deploying to ${destination}"
    # scp needs to the files unquoted
    # shellcheck disable=SC2086 
    scp -r ${files_to_copy} "${destination}" || { log "ERROR: SCP failed"; return 1; }

    log "Deploy completed" "${debug}"

    return 0

}


##################################### LOGIC ####################################
echo ''
get_arguments "${@}" || exit 1
log "Started" "${debug}" 
init || { log "ERROR: Init failed"; exit 1; }
deploy || { log "ERROR: Deploy failed"; exit 1; }

