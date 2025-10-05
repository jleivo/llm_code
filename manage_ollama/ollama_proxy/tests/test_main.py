import pytest
import asyncio
import time
from fastapi.testclient import TestClient
from fastapi.responses import Response
from unittest.mock import MagicMock, patch, AsyncMock

# Adjust path to import the main app and other modules
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import main
from host_manager import HostManager, OllamaHost

# --- Fixtures ---

@pytest.fixture(autouse=True)
def cleanup_sessions():
    """Cleans up the global sessions dictionary after each test."""
    yield
    main.sessions.clear()

@pytest.fixture
def mock_host_manager(mocker):
    """
    Provides a mocked HostManager instance and patches it into the main module.
    """
    # No longer need to patch threading since the monitor isn't auto-started.
    mocker.patch.object(HostManager, 'load_config', return_value=None)
    mock_hm = HostManager('dummy_config.json')

    # Define mock hosts with total VRAM
    host1 = OllamaHost({'url': 'http://host1:11434', 'total_vram_mb': 8192, 'priority': 2})
    host2 = OllamaHost({'url': 'http://host2:11434', 'total_vram_mb': 16384, 'priority': 1})
    mock_hm.hosts = [host1, host2]

    mocker.patch.object(main, 'host_manager', mock_hm)

    return mock_hm

@pytest.fixture
def client():
    """Provides a TestClient for the FastAPI app."""
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
    with open(config_path, 'w') as f:
        f.write('{"hosts": []}')

    with TestClient(main.app) as c:
        yield c

    os.remove(config_path)


# --- Mocks ---

class MockResponse:
    def __init__(self, json_data, status_code=200):
        self.json_data = json_data
        self.status_code = status_code

    def json(self):
        return self.json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"Error {self.status_code}")

# Helper for mocking async iterators
async def mock_aiter_raw_content(content=b'{}'):
    yield content

# --- Test Cases ---

def test_vram_calculation_uses_size_vram(mock_host_manager, mocker):
    """
    Tests that free VRAM is correctly calculated using the 'size_vram' field,
    not the 'size' field.
    """
    host1 = mock_host_manager.hosts[0]
    host1.available = True

    # Mock an API response where size_vram (2GB) is different from size (4GB)
    mock_api_response = {
        "models": [{
            "name": "llama3:latest",
            "size": 4 * 1024 * 1024 * 1024,
            "size_vram": 2 * 1024 * 1024 * 1024, # Correct field to use
            "digest": "test-digest",
            "details": {}
        }]
    }
    mocker.patch('requests.get', return_value=MockResponse(mock_api_response))

    host1.update_status()

    # Total VRAM is 8192MB. Used VRAM should be 2048MB (from size_vram).
    # Free should be 8192 - 2048 = 6144MB.
    assert host1.get_free_vram() == (8192 - 2048)
    assert host1.get_loaded_models() == ['llama3:latest']

def test_best_host_selection_chooses_max_vram(mock_host_manager, mocker, caplog):
    """
    Tests that when no host has the model loaded, the one with the most
    free VRAM (calculated from size_vram) is selected.
    """
    host1, host2 = mock_host_manager.hosts

    # Mock responses for each host using the detailed structure
    def mock_requests_get(url, timeout=5):
        if 'host1' in url: # 8GB total
            # 4GB used according to size_vram -> 4GB free
            return MockResponse({"models": [{"name": "model1", "size": 1, "size_vram": 4096 * 1024 * 1024}]})
        if 'host2' in url: # 16GB total
            # 2GB used according to size_vram -> 14GB free
            return MockResponse({"models": [{"name": "model2", "size": 1, "size_vram": 2048 * 1024 * 1024}]})
        return MockResponse({}, 404)

    mocker.patch('requests.get', side_effect=mock_requests_get)

    host1.available = True
    host2.available = True
    host1.update_status()
    host2.update_status()

    best_host = mock_host_manager.get_best_host('codellama:latest')

    assert best_host is host2
    assert f"Selected best host for 'codellama:latest': {host2.url}" in caplog.text

@pytest.mark.asyncio
async def test_proxy_routing_and_session_creation(client, mock_host_manager, mocker, caplog):
    """
    Tests that a new request is routed to the best host and a session is created.
    """
    host1, host2 = mock_host_manager.hosts
    mocker.patch('requests.get', return_value=MockResponse({"models":[]}))

    host1.available = False
    host2.available = True
    host2.update_status()

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.headers = {'Content-Type': 'application/json'}
    async def mock_aiter_raw_specific():
        yield b'{"response": "mocked"}'
    mock_response.aiter_raw = mock_aiter_raw_specific
    mock_response.aclose = AsyncMock()
    mocker.patch('httpx.AsyncClient.send', return_value=mock_response)

    payload = {"model": "llama3:latest", "messages": [{"role": "user", "content": "Why is the sky blue?"}]}
    response = client.post("/api/chat", json=payload)

    assert response.status_code == 200
    assert "miss. Finding best host for model 'llama3:latest'." in caplog.text
    assert f"Assigned new host {host2.url} to session." in caplog.text

    assert len(main.sessions) == 1
    session_id = list(main.sessions.keys())[0]
    session_host, _ = main.sessions[session_id]
    assert session_host is host2

@pytest.mark.asyncio
async def test_rerouting_after_host_disappearance(client, mock_host_manager, mocker, caplog):
    """
    Tests that if a session's assigned host becomes unavailable, the proxy
    re-routes to the next best host.
    """
    host1, host2 = mock_host_manager.hosts
    mocker.patch('requests.get', return_value=MockResponse({"models":[]}))

    host1.available = True
    host1.update_status()
    host2.available = True
    host2.update_status()

    mocker.patch('httpx.AsyncClient.send', return_value=AsyncMock(
        status_code=200,
        headers={},
        aiter_raw=lambda: mock_aiter_raw_content(),
        aclose=AsyncMock()
    ))

    payload = {"model": "llama3:latest", "messages": [{"role": "user", "content": "Initial prompt"}]}

    # Force host1 to be better initially
    host1.free_vram_mb = 8000
    host2.free_vram_mb = 2000
    client.post("/api/chat", json=payload)

    # Now, host1 disappears
    host1.available = False
    caplog.clear()

    client.post("/api/chat", json=payload)

    found_unavailable_log = any(f"Session host {host1.url} is unavailable. Finding a new host." in record.message for record in caplog.records)
    found_reassigned_log = any(f"Assigned new host {host2.url} to session." in record.message for record in caplog.records)
    assert found_unavailable_log, "Log for unavailable session host not found."
    assert found_reassigned_log, "Did not re-route to the next best host."

@pytest.mark.asyncio
async def test_proxy_streaming_chat(client, mock_host_manager, mocker):
    """
    Tests that a streaming chat request is handled correctly.
    """
    mocker.patch('requests.get', return_value=MockResponse({"models":[]}))
    host = mock_host_manager.hosts[0]
    host.available = True
    host.update_status()

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.headers = {'Content-Type': 'application/json'}
    async def mock_aiter_raw_specific():
        yield b'{"response": "streaming"}'
    mock_response.aiter_raw = mock_aiter_raw_specific
    mock_response.aclose = AsyncMock()
    mocker.patch('httpx.AsyncClient.send', return_value=mock_response)

    payload = {"model": "llama3:latest", "messages": [{"role": "user", "content": "Stream test"}], "stream": True}
    response = client.post("/api/chat", json=payload)

    assert response.status_code == 200
    assert response.text == '{"response": "streaming"}'


@pytest.mark.asyncio
async def test_proxy_non_streaming_chat(client, mock_host_manager, mocker):
    """
    Tests that a non-streaming chat request is handled correctly.
    """
    mocker.patch('requests.get', return_value=MockResponse({"models":[]}))
    host = mock_host_manager.hosts[0]
    host.available = True
    host.update_status()

    mock_response = Response(
        content=b'{"response": "non-streaming"}',
        status_code=200,
        headers={'Content-Type': 'application/json'}
    )
    mocker.patch('main.forward_request', new=AsyncMock(return_value=mock_response))

    payload = {"model": "llama3:latest", "messages": [{"role": "user", "content": "Non-stream test"}], "stream": False}
    response = client.post("/api/chat", json=payload)

    assert response.status_code == 200
    assert response.json() == {"response": "non-streaming"}

@pytest.mark.asyncio
async def test_model_not_found_triggers_retry_to_alternative_host(client, mock_host_manager, mocker, caplog):
    """
    Tests that a 404 'model not found' error triggers a retry to a second host
    that is discovered to have the model after a status refresh.
    """
    host1, host2 = mock_host_manager.hosts
    host1.available, host2.available = True, True
    host1.loaded_models, host2.loaded_models = [], []

    # First, get_best_host is called and returns host2 (P1).
    # After the 404, it's called again and returns host1 (the only other option).
    mocker.patch.object(mock_host_manager, 'get_best_host', side_effect=[host2, host1])
    # The refresh should "reveal" that host1 now has the model.
    def refresh_side_effect():
        host1.loaded_models = ['the-model']
    mocker.patch.object(mock_host_manager, 'refresh_all_hosts_status', side_effect=refresh_side_effect)

    mock_404_response = Response(content=b'{"error": "model \'the-model\' not found"}', status_code=404)
    mock_200_response = Response(content=b'{"response": "success"}', status_code=200)
    mocker.patch('main.forward_request', new_callable=AsyncMock, side_effect=[mock_404_response, mock_200_response])

    payload = {"model": "the-model", "messages": [{"role": "user", "content": "Test"}]}
    response = client.post("/api/chat", json=payload)

    assert response.status_code == 200
    assert response.json() == {"response": "success"}
    assert f"Model 'the-model' not found on host {host2.url}" in caplog.text
    assert f"Found alternative host {host1.url} with model 'the-model'. Retrying request." in caplog.text
    assert main.forward_request.call_count == 2


@pytest.mark.asyncio
async def test_model_not_found_triggers_pull_if_no_alternative(client, mock_host_manager, mocker, caplog):
    """
    Tests that if no other host has the model after a refresh, the proxy attempts to pull it.
    """
    host1, host2 = mock_host_manager.hosts
    host1.available, host2.available = True, True
    host1.loaded_models, host2.loaded_models = [], []

    # 1. Initial call returns host2.
    # 2. Call after 404 returns host1 (the only one not excluded).
    # 3. host1 doesn't have the model, so we enter pull logic. A final call selects the best host for pulling (host2).
    mocker.patch.object(mock_host_manager, 'get_best_host', side_effect=[host2, host1, host2])
    mocker.patch.object(mock_host_manager, 'refresh_all_hosts_status')

    mock_404_response = Response(content=b'{"error": "model \'the-model\' not found"}', status_code=404)
    mock_200_response = Response(content=b'{"response": "success from pull"}', status_code=200)
    mocker.patch('main.forward_request', new_callable=AsyncMock, side_effect=[mock_404_response, mock_200_response])

    mocker.patch.object(mock_host_manager, 'pull_model_on_host', new_callable=AsyncMock, return_value=True)

    payload = {"model": "the-model", "messages": [{"role": "user", "content": "Test"}]}
    response = client.post("/api/chat", json=payload)

    assert response.status_code == 200
    assert response.json() == {"response": "success from pull"}
    assert f"No other host has model 'the-model'. Attempting to pull it." in caplog.text
    mock_host_manager.pull_model_on_host.assert_called_once_with(host2, 'the-model')


@pytest.mark.asyncio
async def test_model_pull_failure_returns_original_404(client, mock_host_manager, mocker, caplog):
    """
    Tests that if the model pull fails, the original 404 response is returned.
    """
    host1, host2 = mock_host_manager.hosts
    host1.available, host2.available = True, True
    host1.loaded_models, host2.loaded_models = [], []

    mocker.patch.object(mock_host_manager, 'get_best_host', side_effect=[host2, host1, host2])
    mocker.patch.object(mock_host_manager, 'refresh_all_hosts_status')

    original_404_content = b'{"error": "model \'the-model\' not found"}'
    mock_404_response = Response(content=original_404_content, status_code=404)
    mocker.patch('main.forward_request', new_callable=AsyncMock, return_value=mock_404_response)

    mocker.patch.object(mock_host_manager, 'pull_model_on_host', new_callable=AsyncMock, return_value=False)

    payload = {"model": "the-model", "messages": [{"role": "user", "content": "Test"}]}
    response = client.post("/api/chat", json=payload)

    assert response.status_code == 404
    assert response.content == original_404_content
    assert f"Failed to pull model 'the-model' on host {host2.url}" in caplog.text
    assert main.forward_request.call_count == 1