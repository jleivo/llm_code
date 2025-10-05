import pytest
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

def test_get_best_host_prefers_loaded_model_over_vram(mock_host_manager_for_logic):
    """
    Tests that get_best_host selects the host with the model loaded, even if it has less VRAM
    and a worse priority than another host.
    """
    hm, _ = mock_host_manager_for_logic
    # Requesting 'model-b', which is only on the P2 host with low VRAM.
    best_host = hm.get_best_host('model-b')
    assert best_host.url == 'http://priority2:11434'

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