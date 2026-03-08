# Jules CLI Tool

This tool allows agentic systems (like Openclaw) to collaborate with the Jules AI agent via its REST API.

## Setup

1.  **Jules API Key**: Create a file named `jules_api_key.txt` in the same directory as the script and paste your Jules API key into it. You can get your API key from [jules.google.com/settings](https://jules.google.com/settings).
2.  **GitHub Token**: For the `merge` command, you need a GitHub Personal Access Token.
    *   **Recommended**: Use a **Fine-grained personal access token** for maximum security.
    *   **Permissions**:
        *   **Repository access**: Only select `jleivo/Claw_jules_collaboration`.
        *   **Permissions**: `Repository permissions` -> `Pull requests`: Read and write.
    *   Save this token in a file named `github_token.txt` or set the `GITHUB_TOKEN` environment variable.

## Usage

### Create a new session
Starts a new task for Jules.
```bash
./jules_cli.py create --prompt "Fix the bug in the authentication logic" --title "Bugfix Auth"
```

### Chat with Jules
Enters an interactive REPL loop to discuss the task with Jules.
```bash
./jules_cli.py chat --session-id <SESSION_ID>
```

### Check status
Shows the current state of the session and the latest activities.
```bash
./jules_cli.py status --session-id <SESSION_ID>
```

### Merge the results
Once the session is `COMPLETED` and a Pull Request has been created, use this command to merge it.
```bash
./jules_cli.py merge --session-id <SESSION_ID>
```

## Integration with Orchestrators

Orchestrators should:
1.  Call `create` and store the `SESSION_ID`.
2.  Optionally call `chat` (or implement their own messaging logic using the API) to provide further instructions.
3.  Poll `status` until the state is `COMPLETED`.
4.  Call `merge` if the work is acceptable.
