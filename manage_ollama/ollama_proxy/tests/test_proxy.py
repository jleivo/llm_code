import pytest
import asyncio
import time
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

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
    mocker.patch('threading.Thread.start')
    mocker.patch.object(HostManager, 'load_config', return_value=None)

    mock_hm = HostManager('dummy_config.json')

    # Define mock hosts with total VRAM
    host1 = OllamaHost({'url': 'http://host1:11434', 'total_vram_mb': 8192})
    host2 = OllamaHost({'url': 'http://host2:11434', 'total_vram_mb': 16384})
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

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {'Content-Type': 'application/json'}
    async def mock_aiter_raw_specific():
        yield b'{"response": "mocked"}'
    mock_response.aiter_raw = mock_aiter_raw_specific
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

    mocker.patch('httpx.AsyncClient.send', return_value=MagicMock(status_code=200, headers={}, aiter_raw=lambda: mock_aiter_raw_content()))

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