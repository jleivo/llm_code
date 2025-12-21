import pytest
import json
import tempfile
from unittest.mock import MagicMock, patch, AsyncMock

# Adjust path to import the main app and other modules
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from host_manager import HostManager, OllamaHost

# --- Fixtures ---

@pytest.fixture
def mock_host_manager_for_logic(mocker):
    """Provides a HostManager instance with mocked-out network calls for testing logic."""
    # No longer need to patch threading since the monitor isn't auto-started.
    mocker.patch.object(HostManager, 'load_config', return_value=None)
    hm = HostManager('dummy_config.json')

    # Create mock hosts with specific properties for testing selection logic
    host_p1_vram_high = OllamaHost({'url': 'http://priority1:11434', 'priority': 1, 'total_vram_mb': 16000})
    host_p2_vram_low = OllamaHost({'url': 'http://priority2:11434', 'priority': 2, 'total_vram_mb': 8000})
    host_p3_vram_mid = OllamaHost({'url': 'http://priority3:11434', 'priority': 3, 'total_vram_mb': 12000})

    # Manually set their status for predictable tests
    host_p1_vram_high.available = True
    host_p1_vram_high.free_vram_mb = 8000
    host_p1_vram_high.loaded_models = ['model-a']

    host_p2_vram_low.available = True
    host_p2_vram_low.free_vram_mb = 4000
    host_p2_vram_low.loaded_models = ['model-b']

    host_p3_vram_mid.available = True
    host_p3_vram_mid.free_vram_mb = 10000
    host_p3_vram_mid.loaded_models = []

    hm.hosts = [host_p1_vram_high, host_p2_vram_low, host_p3_vram_mid]
    return hm, hm.hosts

# --- Test Cases for HostManager ---

def test_get_best_host_prefers_loaded_model_over_local(mock_host_manager_for_logic):
    """
    Tests that a host with the model loaded in VRAM is preferred over one
    where the model is only available locally on disk, even if the local one has better priority.
    """
    hm, (host1, host2, host3) = mock_host_manager_for_logic
    host1.loaded_models = []
    host1.local_models = ['the-model'] # P1 has it on disk
    host2.loaded_models = ['the-model'] # P2 has it in VRAM

    best_host = hm.get_best_host('the-model')
    assert best_host.url == 'http://priority2:11434'

def test_get_best_host_prefers_local_model_over_vram(mock_host_manager_for_logic):
    """
    Tests that get_best_host selects a host with the model locally over a host
    with more free VRAM but without the model at all.
    """
    hm, (host1, host2, host3) = mock_host_manager_for_logic
    # host1 (P1) has the model on disk. host3 (P3) has more VRAM but no model.
    host1.local_models = ['the-model']

    best_host = hm.get_best_host('the-model')
    assert best_host.url == 'http://priority1:11434'

def test_get_best_host_respects_priority_when_multiple_hosts_have_model(mock_host_manager_for_logic):
    """
    Tests that if multiple hosts have the model, the one with the best priority is chosen.
    """
    hm, (host1, host2, _) = mock_host_manager_for_logic
    # Add 'model-a' to the second host as well.
    host2.loaded_models.append('model-a')

    # Host1 (P1) and Host2 (P2) both have 'model-a'. Host1 should be chosen due to priority.
    best_host = hm.get_best_host('model-a')
    assert best_host.url == 'http://priority1:11434'

def test_get_best_host_selects_max_vram_when_model_is_not_loaded(mock_host_manager_for_logic):
    """
    Tests that when no host has the model, the one with the most free VRAM is selected.
    """
    hm, _ = mock_host_manager_for_logic
    # 'model-c' is not loaded on any host. Host3 has the most free VRAM (10000MB).
    best_host = hm.get_best_host('model-c')
    assert best_host.url == 'http://priority3:11434'

def test_get_best_host_prefers_vram_when_multiple_hosts_have_model_loaded(mock_host_manager_for_logic):
    """
    Tests that when multiple hosts have the model loaded, the one with more free VRAM is preferred,
    even if it has lower priority. This is the key improvement for VRAM prioritization.
    """
    hm, (host1, host2, host3) = mock_host_manager_for_logic

    # Set up scenario: both host1 (P1, 8000MB free) and host3 (P3, 10000MB free) have the model loaded
    host1.loaded_models = ['test-model']
    host3.loaded_models = ['test-model']

    # Host3 has more free VRAM despite lower priority, so it should be selected
    best_host = hm.get_best_host('test-model')
    assert best_host.url == 'http://priority3:11434'
    assert best_host.get_free_vram() == 10000

def test_get_best_host_prefers_vram_when_multiple_hosts_have_model_local(mock_host_manager_for_logic):
    """
    Tests that when multiple hosts have the model locally, the one with more free VRAM is preferred,
    even if it has lower priority. This ensures we minimize model unloading.
    """
    hm, (host1, host2, host3) = mock_host_manager_for_logic

    # Set up scenario: both host1 (P1, 8000MB free) and host3 (P3, 10000MB free) have the model locally
    host1.local_models = ['test-model']
    host3.local_models = ['test-model']

    # Host3 has more free VRAM despite lower priority, so it should be selected
    best_host = hm.get_best_host('test-model')
    assert best_host.url == 'http://priority3:11434'
    assert best_host.get_free_vram() == 10000

def test_get_best_host_respects_priority_when_vram_similar(mock_host_manager_for_logic):
    """
    Tests that when hosts have similar VRAM availability, priority is still respected.
    This ensures we don't break existing priority-based behavior unnecessarily.
    """
    hm, (host1, host2, host3) = mock_host_manager_for_logic

    # Set up scenario: both host1 (P1, 8000MB free) and host2 (P2, 8000MB free) have the model loaded
    host1.loaded_models = ['test-model']
    host2.loaded_models = ['test-model']
    host1.free_vram_mb = 8000
    host2.free_vram_mb = 8000

    # Host1 should be selected due to higher priority (same VRAM)
    best_host = hm.get_best_host('test-model')
    assert best_host.url == 'http://priority1:11434'
    assert best_host.priority == 1

def test_get_best_host_excludes_hosts(mock_host_manager_for_logic):
    """
    Tests that get_best_host correctly excludes specified hosts from selection.
    """
    hm, _ = mock_host_manager_for_logic
    # Exclude the host that has 'model-a'.
    best_host = hm.get_best_host('model-a', excluded_urls=['http://priority1:11434'])
    # The next best choice should be the one with the most VRAM, as no other host has 'model-a'.
    assert best_host.url == 'http://priority3:11434'

@pytest.mark.asyncio
async def test_pull_model_on_host_success(mock_host_manager_for_logic, mocker):
    """
    Tests the pull_model_on_host function for a successful pull operation.
    """
    hm, (host, _, _) = mock_host_manager_for_logic

    async def mock_aiter_bytes_gen():
        yield b'{"status": "success"}\n'

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.aiter_bytes = mock_aiter_bytes_gen

    mock_client = MagicMock()
    stream_context = AsyncMock()
    stream_context.__aenter__.return_value = mock_response
    mock_client.stream.return_value = stream_context

    client_context = AsyncMock()
    client_context.__aenter__.return_value = mock_client
    mocker.patch('httpx.AsyncClient', return_value=client_context)

    mocker.patch.object(host, 'update_status')
    success = await hm.pull_model_on_host(host, 'new-model')
    assert success is True
    host.update_status.assert_called_once()

@pytest.mark.asyncio
async def test_pull_model_on_host_failure_with_error_in_stream(mock_host_manager_for_logic, mocker):
    """
    Tests the pull_model_on_host function for a failure where the stream contains an error message.
    """
    hm, (host, _, _) = mock_host_manager_for_logic

    async def mock_aiter_bytes_fail_gen():
        yield b'{"error": "model not found"}\n'

    mock_response_fail = MagicMock()
    mock_response_fail.status_code = 200
    mock_response_fail.aiter_bytes = mock_aiter_bytes_fail_gen

    mock_client = MagicMock()
    stream_context = AsyncMock()
    stream_context.__aenter__.return_value = mock_response_fail
    mock_client.stream.return_value = stream_context

    client_context = AsyncMock()
    client_context.__aenter__.return_value = mock_client
    mocker.patch('httpx.AsyncClient', return_value=client_context)

    mocker.patch.object(host, 'update_status')
    success = await hm.pull_model_on_host(host, 'nonexistent-model')
    assert success is False
    host.update_status.assert_not_called()


# --- Test Cases for Server Port Configuration ---

def test_get_server_port_default():
    """
    Tests that get_server_port returns the default port 8080 when no port is specified in config.
    """
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        config_data = {
            "hosts": [
                {"url": "http://host1:11434", "total_vram_mb": 8192, "priority": 1}
            ]
        }
        json.dump(config_data, f)
        config_path = f.name

    try:
        hm = HostManager(config_path)
        assert hm.get_server_port() == 8080
    finally:
        os.unlink(config_path)


def test_get_server_port_custom():
    """
    Tests that get_server_port returns a custom port when specified in config.
    """
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        config_data = {
            "server": {"port": 9090},
            "hosts": [
                {"url": "http://host1:11434", "total_vram_mb": 8192, "priority": 1}
            ]
        }
        json.dump(config_data, f)
        config_path = f.name

    try:
        hm = HostManager(config_path)
        assert hm.get_server_port() == 9090
    finally:
        os.unlink(config_path)


def test_get_server_port_custom_various_ports():
    """
    Tests that get_server_port correctly handles various custom ports.
    """
    test_ports = [3000, 5000, 8000, 8888, 9999, 12345]
    
    for port in test_ports:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_data = {
                "server": {"port": port},
                "hosts": [
                    {"url": "http://host1:11434", "total_vram_mb": 8192, "priority": 1}
                ]
            }
            json.dump(config_data, f)
            config_path = f.name

        try:
            hm = HostManager(config_path)
            assert hm.get_server_port() == port, f"Expected port {port}, got {hm.get_server_port()}"
        finally:
            os.unlink(config_path)


def test_get_server_port_empty_server_section():
    """
    Tests that get_server_port returns the default port when server section exists but is empty.
    """
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        config_data = {
            "server": {},
            "hosts": [
                {"url": "http://host1:11434", "total_vram_mb": 8192, "priority": 1}
            ]
        }
        json.dump(config_data, f)
        config_path = f.name

    try:
        hm = HostManager(config_path)
        assert hm.get_server_port() == 8080
    finally:
        os.unlink(config_path)


def test_load_config_with_server_settings():
    """
    Tests that load_config properly loads server settings from config.
    """
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        config_data = {
            "server": {"port": 7000},
            "hosts": [
                {"url": "http://host1:11434", "total_vram_mb": 8192, "priority": 1},
                {"url": "http://host2:11434", "total_vram_mb": 16384, "priority": 2}
            ]
        }
        json.dump(config_data, f)
        config_path = f.name

    try:
        hm = HostManager(config_path)
        assert hm.server_config == {"port": 7000}
        assert len(hm.hosts) == 2
    finally:
        os.unlink(config_path)


def test_malformed_json_config():
    """
    Tests that loading a malformed JSON config file raises an appropriate error.
    """
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write('{ "invalid json" invalid }')
        config_path = f.name

    try:
        with pytest.raises(json.JSONDecodeError):
            hm = HostManager(config_path)
    finally:
        os.unlink(config_path)


def test_missing_hosts_key_in_config():
    """
    Tests that loading a config without the required 'hosts' key raises an appropriate error.
    """
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        config_data = {
            "server": {"port": 9090}
        }
        json.dump(config_data, f)
        config_path = f.name

    try:
        with pytest.raises(KeyError):
            hm = HostManager(config_path)
    finally:
        os.unlink(config_path)


def test_invalid_port_type_string():
    """
    Tests that a non-numeric port value is handled. The get_server_port should return the value as-is,
    but it's the application's responsibility to handle port type validation.
    """
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        config_data = {
            "server": {"port": "invalid_port"},
            "hosts": [
                {"url": "http://host1:11434", "total_vram_mb": 8192, "priority": 1}
            ]
        }
        json.dump(config_data, f)
        config_path = f.name

    try:
        hm = HostManager(config_path)
        # The method returns the value as-is. Type validation should be done at server startup.
        assert hm.get_server_port() == "invalid_port"
    finally:
        os.unlink(config_path)


def test_negative_port_value():
    """
    Tests that a negative port value is returned as-is. Port validation should be done elsewhere.
    """
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        config_data = {
            "server": {"port": -1234},
            "hosts": [
                {"url": "http://host1:11434", "total_vram_mb": 8192, "priority": 1}
            ]
        }
        json.dump(config_data, f)
        config_path = f.name

    try:
        hm = HostManager(config_path)
        assert hm.get_server_port() == -1234
    finally:
        os.unlink(config_path)


def test_port_out_of_valid_range():
    """
    Tests that port values outside valid range are returned as-is.
    """
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        config_data = {
            "server": {"port": 99999},
            "hosts": [
                {"url": "http://host1:11434", "total_vram_mb": 8192, "priority": 1}
            ]
        }
        json.dump(config_data, f)
        config_path = f.name

    try:
        hm = HostManager(config_path)
        assert hm.get_server_port() == 99999
    finally:
        os.unlink(config_path)