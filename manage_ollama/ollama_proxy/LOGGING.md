# Ollama Proxy - Logging Configuration

## Overview

The Ollama Proxy now sends logs to **syslog using facility `LOG_LOCAL7`**. This allows easy separation of application logs from the main system syslog using rsyslog.

## Log Outputs

The application logs to three destinations:

1. **Console** - stdout in real-time
2. **File** - `proxy.log` in the script directory
3. **Syslog** - System syslog using `LOG_LOCAL7` facility

## Debugging Handler Initialization

When the application starts, it prints debug information about the logging configuration. This helps you verify that all handlers are initialized correctly:

```
[LOGGER INIT DEBUG] Initial handlers: [<StreamHandler <stderr> (NOTSET)>]
[LOGGER INIT DEBUG] Checking if handlers exist: True
[LOGGER INIT DEBUG] Clearing 1 existing handlers
[LOGGER INIT DEBUG] Removed handler: StreamHandler
[LOGGER INIT DEBUG] Added StreamHandler
[LOGGER INIT DEBUG] Added FileHandler to /home/juha/git/llm_code/manage_ollama/ollama_proxy/proxy.log
[SYSLOG DEBUG] /dev/log found, permissions: 0o140666
[SYSLOG DEBUG] Successfully initialized SysLogHandler with address=/dev/log
[SYSLOG DEBUG] Syslog facility: LOG_LOCAL7 (23)
[SYSLOG DEBUG] Current handlers: ['StreamHandler', 'FileHandler', 'SysLogHandler']

======================================================================
LOGGING CONFIGURATION DIAGNOSTICS
======================================================================
Root Logger Level: INFO
Total Handlers: 3

  Handler 1: StreamHandler
    Level: NOTSET
    Formatter: %(asctime)s - %(name)s - %(levelname)s - %(message)s

  Handler 2: FileHandler
    Level: NOTSET
    File: /home/juha/git/llm_code/manage_ollama/ollama_proxy/proxy.log
    Formatter: %(asctime)s - %(name)s - %(levelname)s - %(message)s

  Handler 3: SysLogHandler
    Level: NOTSET
    Address: /dev/log
    Facility: LOG_LOCAL7 (23)
    Formatter: %(name)s[%(process)d]: %(levelname)s - %(message)s

Syslog Socket Check:
  /dev/log exists: Yes
  Permissions: 0o140666
  Can write: True
```

### Disabling Debug Output

If you want to remove the debug output, edit `main.py` and comment out or remove the print statements starting with `[LOGGER INIT DEBUG]`, `[SYSLOG DEBUG]`, etc., and also comment out the call to `print_logging_diagnostics()` before the server starts.

## Setting Up rsyslog for Separate Log File

### Quick Setup

```bash
sudo cp ollama_proxy.rsyslog.conf /etc/rsyslog.d/ollama_proxy.conf
sudo systemctl restart rsyslog
```

### Manual Setup

1. Edit `/etc/rsyslog.d/ollama_proxy.conf` (create if it doesn't exist):

```
local7.* /var/log/ollama_proxy.log
```

2. Restart rsyslog:

```bash
sudo systemctl restart rsyslog
```

3. Verify logs are being written:

```bash
tail -f /var/log/ollama_proxy.log
```

### Preventing Duplicates in syslog

If you want to prevent `LOG_LOCAL7` logs from also appearing in `/var/log/syslog`, add this to your rsyslog configuration:

```
local7.* /var/log/ollama_proxy.log
local7.* ~
```

The `~` acts as a discard filter, preventing the message from being processed by subsequent rules.

### Advanced Filtering

You can also create separate files for different log levels:

```
local7.err /var/log/ollama_proxy_errors.log
local7.info /var/log/ollama_proxy_info.log
```

## Verifying Logs Are Sent to Syslog

You can verify that logs are being sent to syslog with the `LOG_LOCAL7` facility:

```bash
# Check for messages in syslog
grep "LOCAL7" /var/log/syslog

# Or search for the application name
grep "__main__" /var/log/syslog

# Watch syslog in real-time while the app runs
tail -f /var/log/syslog | grep "LOCAL7"
```

## Log Levels

The application respects the following log levels:

- `INFO` - Default level, shows general operation info
- `DEBUG` - Verbose output, enabled with `--debug` flag
- `ERROR` - Error messages
- `WARNING` - Warning messages

## Example: Running with Debug Mode

```bash
python main.py --debug
```

This sets all handlers to DEBUG level for verbose logging.

## Syslog Format

Logs sent to syslog use the format:
```
%(name)s[%(process)d]: %(levelname)s - %(message)s
```

Example syslog entry:
```
ollama_proxy[1234]: INFO - Session hit. Routing to previous host: http://192.168.1.100:11434
```

## Troubleshooting

### Syslog handler fails silently on systems without /dev/log

On some systems (like macOS or systems using systemd-journal), `/dev/log` may not be available. The application gracefully handles this by:
- Attempting to use UDP connection to `localhost:514` as a fallback
- Continuing to log to console and file if syslog is unavailable

You'll see debug messages indicating if this fallback was used.

### Checking syslog connectivity

```bash
# Check if syslog socket exists
ls -la /dev/log

# Test syslog writing
logger "Test message from ollama_proxy"
tail /var/log/syslog

# Check permissions
stat /dev/log
```

### Verify rsyslog is processing the config

```bash
# Check rsyslog syntax
sudo rsyslogctl -c list

# View rsyslog configuration being used
sudo rsyslog -N1
```

### Verify all handlers are initialized

Look at the startup output. You should see:
- `[LOGGER INIT DEBUG] Added StreamHandler`
- `[LOGGER INIT DEBUG] Added FileHandler to ...`
- `[SYSLOG DEBUG] Successfully initialized SysLogHandler`
- And in the diagnostics: `Total Handlers: 3`

If you only see 1 handler, the file and syslog handlers are not being added. Check for error messages in the debug output.

