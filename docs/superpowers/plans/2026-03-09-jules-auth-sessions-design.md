# Jules Auth Check + Session Listing Design

**Date:** 2026-03-09
**Status:** Approved

## Overview

Add two new capabilities to the Jules CLI and library:
1. **Auth check** — verify the API key works and display identity/project info
2. **Session listing** — list all sessions with optional state filtering, plus a helper to show valid states

## Library (`jules/jules.py`)

### `auth_check()`

- Calls `GET /sessions?pageSize=1` as a minimal authenticated probe
- On success: returns `{"status": "ok", "endpoint": JULES_API_BASE, "project": <extracted or "unknown">}`
- On HTTP 401/403: raises `JulesError("Invalid or missing API key")`
- On other errors: re-raises with context

### `list_sessions(state_filter=None)`

- Calls `GET /sessions` with full pagination (mirrors existing `get_activities` pattern)
- Filters client-side by `state_filter` if provided (Jules API filter syntax undocumented)
- Returns list of dicts: `id`, `state`, `title`, `url`, `createTime`

### `VALID_STATES`

Hardcoded tuple of known Jules session states:

```python
VALID_STATES = (
    "STARTING",
    "WAITING_FOR_USER_RESPONSE",
    "CODING",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
)
```

Used by the `states` CLI subcommand and for `--state` validation.

## CLI (`jules/jules_cli.py`)

### `auth` subcommand

```
./jules_cli.py auth
```

Success output:
```
Authentication OK
  API endpoint: https://jules.googleapis.com/v1alpha
  Project: <value or "unknown">
```

Failure output:
```
Authentication failed: Invalid or missing API key
```

### `list` subcommand

```
./jules_cli.py list [--state STATE]
```

Output:
```
ID           State       Title
session-123  CODING      Fix auth bug
session-456  COMPLETED   Add tests
```

- `--state STATE` filters to sessions matching that state (case-insensitive)
- Invalid `--state` value prints a warning and suggests running `./jules_cli.py states`

### `states` subcommand

```
./jules_cli.py states
```

Output:
```
Valid session states:
  STARTING
  WAITING_FOR_USER_RESPONSE
  CODING
  COMPLETED
  FAILED
  CANCELLED
```

## Tests

### `jules/test_jules.py`

- `test_auth_check_success` — mock returns session list, verify returns ok dict
- `test_auth_check_failure` — mock returns 401, verify raises `JulesError`
- `test_list_sessions_all` — mock returns sessions, verify all returned
- `test_list_sessions_filtered` — mock returns mixed states, verify filter works

### `jules/test_jules_cli.py`

- CLI tests for `auth`, `list`, `list --state`, and `states` subcommands
