# Troubleshooting

Common issues encountered across Jules executor sessions.

## Source Identifier Format

**Symptom:** `400 Bad Request` when creating sessions.

**Cause:** The source identifier must use slashes: `sources/github/owner/repo`, not hyphens like `sources/github-owner-repo`.

**Fix:** Already fixed in the library (v1.0.0+). If you see this error, ensure you're using the latest `jules.py`.

## Vault SSL Certificate Path

**Symptom:** `SSLError` or `certificate verify failed` when connecting to Vault.

**Fix:** The Vault client must use the system CA bundle:
```python
hvac.Client(url=..., verify="/etc/ssl/certs/ca-certificates.crt")
```

## Trailing Whitespace in Vault Secrets

**Symptom:** API key or token rejected despite being correct in Vault.

**Cause:** Vault secrets sometimes have trailing whitespace/newlines.

**Fix:** Always call `.strip()` on values read from Vault. The library does this automatically.

## GitHub Token Retrieval Order

The library checks these sources in order:
1. `GITHUB_TOKEN` environment variable
2. Vault at `hosts/tuvmcpsrvp01/github_token`
3. `github_token.txt` file in CWD

If you need to override, set the env var: `export GITHUB_TOKEN=ghp_...`

## Branch Confusion in Worktrees

**Symptom:** Jules creates PRs against the wrong branch or can't find the branch.

**Cause:** When running from a git worktree, `git rev-parse --abbrev-ref HEAD` returns the worktree's branch, which may not exist on the remote yet.

**Fix:** Always push your worktree branch to the remote before launching Jules sessions:
```bash
git push -u origin HEAD
```

## Requirements Not Installed

**Symptom:** `ModuleNotFoundError: No module named 'hvac'` or `'requests'`.

**Fix:** Install in the active venv:
```bash
pip install -r <skill-path>/scripts/requirements.txt
```

## Session Stuck in STARTING

**Symptom:** Session stays in `STARTING` state for more than 5 minutes.

**Cause:** Jules may be experiencing capacity issues or the repository is very large.

**Fix:** Wait up to 10 minutes. If still stuck, cancel and retry. Check Jules status at https://jules.google.com.

## Poll State File Stale

**Symptom:** `--poll-once` keeps trying to poll sessions that no longer exist.

**Fix:** Delete the state file and let it recreate:
```bash
rm /tmp/jules_state.json
```
