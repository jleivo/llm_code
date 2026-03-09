# Vault Secret Access for Scripts and Services

This document explains how scripts on this homelab authenticate to HashiCorp Vault
and retrieve secrets at runtime. Authentication uses AppRole with credentials stored
on disk. The Vault CA certificate is trusted system-wide — no per-script CA config needed.

Secrets are fetched live on every run. No caching.

---

## Bootstrap Files

These files are pre-provisioned on every host by the `vault_bootstrap` Ansible role
or the manual provisioning guide. Scripts read them at runtime — never hard-code
the Vault address or credentials.

| File                                      | Purpose                                 |
| ----------------------------------------- | --------------------------------------- |
| `/etc/vault/vault_addr`                   | Vault server URL                        |
| `/etc/vault/host/role_id`                 | AppRole role_id for host-level access   |
| `/etc/vault/host/secret_id`               | AppRole secret_id for host-level access |
| `/etc/vault/services/<service>/role_id`   | AppRole role_id for a systemd service   |
| `/etc/vault/services/<service>/secret_id` | AppRole secret_id for a systemd service |

Host credentials are readable by the `vault-readers` group (mode `640`).
Service credentials are readable only by the service user (mode `600`).

---

## Secret Path Reference

| Namespace | Vault path | Who can read |
|---|---|---|
| Common | `secret/common/<key>` | All hosts |
| Host | `secret/hosts/<hostname>/<key>` | That host's `vault-readers` group |
| Service | `secret/services/<hostname>/<service>/<key>` | That service on that host only |

---

## Bash

### Requirement

The `vault` CLI binary must be installed and in `PATH`.

```bash
# Install on Debian/Ubuntu:
wget -O- https://apt.releases.hashicorp.com/gpg \
    | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] \
    https://apt.releases.hashicorp.com $(lsb_release -cs) main" \
    | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt-get update && sudo apt-get install -y vault
```

### Authentication and Fetch Pattern

Add this block at the top of your script, after `set -euo pipefail`:

```bash
# --- Vault authentication ---
VAULT_ADDR=$(cat /etc/vault/vault_addr)
CREDS_DIR=/etc/vault/host            # or /etc/vault/services/<service> for systemd services
export VAULT_ADDR

VAULT_TOKEN=$(vault write -field=token auth/approle/login \
    role_id="$(cat "${CREDS_DIR}/role_id")" \
    secret_id="$(cat "${CREDS_DIR}/secret_id")")
export VAULT_TOKEN
# --- end Vault authentication ---

# Read a secret
MY_SECRET=$(vault kv get -field=value secret/hosts/<hostname>/<key>)
# or for a service:
MY_SECRET=$(vault kv get -field=value secret/services/<hostname>/<service>/<key>)
```

### Rules

- **Always `export VAULT_ADDR` and `VAULT_TOKEN`** before calling any `vault` subcommand — child processes inherit exported variables.
- **Authenticate once per script run.** Do not store `VAULT_TOKEN` to disk or pass it as an argument.
- **Never `echo $MY_SECRET`** or write secret values to logs.
- **Use `set -euo pipefail`** at the top of every script — the script aborts if any `vault` command fails rather than silently continuing with an empty variable.

---

## Python

### Dependency

```bash
pip install hvac
# or add to requirements.txt:
hvac>=2.0.0
```

### Authentication Pattern

Copy this function into your script or a shared `vault_utils.py`:

```python
import hvac

def vault_client(service: str = None) -> hvac.Client:
    """
    Authenticate to Vault using AppRole and return an authenticated client.

    Args:
        service: If None, uses host-level credentials (/etc/vault/host/).
                 If set, uses service credentials (/etc/vault/services/<service>/).
    """
    base = f"/etc/vault/services/{service}" if service else "/etc/vault/host"
    client = hvac.Client(
        url=open("/etc/vault/vault_addr").read().strip(),
    )
    client.auth.approle.login(
        role_id=open(f"{base}/role_id").read().strip(),
        secret_id=open(f"{base}/secret_id").read().strip(),
    )
    return client
```

### Reading a Secret

```python
# Host-level secret (script runs as a vault-readers group member)
client = vault_client()
value = client.secrets.kv.v2.read_secret_version(
    path="hosts/<hostname>/<key>"
)["data"]["data"]["value"]

# Service-level secret (script runs as the service user)
client = vault_client(service="nginx")
value = client.secrets.kv.v2.read_secret_version(
    path="services/<hostname>/nginx/<key>"
)["data"]["data"]["value"]
```

### Rules

- **Call `vault_client()` once per script run.** The AppRole token has a 1h TTL — do not cache the client across invocations.
- **Never use `verify=False`** — always let hvac verify TLS against the system trust store.
- **Never log or print secret values** unless explicitly required by the task.
- **The `path` argument to `read_secret_version` does not include the `secret/` mount prefix** — hvac handles that internally.

