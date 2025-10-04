import pytest
import asyncio
import time
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

# Adjust path to import the main app and other modules
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import app, sessions, host_manager, SESSION_TIMEOUT_SECONDS
from host_manager import HostManager, OllamaHost

# --- Fixtures ---

@pytest.fixture(scope="function")
def client():
    """Provides a TestClient for the FastAPI app."""
    with TestClient(app) as c:
        yield c

@pytest.fixture(autouse=True)
def cleanup_sessions():
    """Cleans up the global sessions dictionary after each test."""
    yield
    sessions.clear()

@pytest.fixture
def mock_host_manager(mocker):
    """Mocks the HostManager and its underlying network calls."""
    # Prevent the real monitoring thread from starting
    mocker.patch('threading.Thread.start')

    # Mock the config loading to provide a controlled set of hosts
    mocker.patch.object(HostManager, 'load_config')

    # Create a HostManager instance without starting the monitor
    hm = HostManager('dummy_config.json')

    # Define two mock hosts
    host1 = OllamaHost({'url': 'http://host1:11434'})
    host2 = OllamaHost({'url': 'http://host2:11434', 'ssh_host': 'host2', 'ssh_user': 'user', 'ssh_pass': 'pass'})

    hm.hosts = [host1, host2]

    # Patch the global host_manager instance in the main module
    mocker.patch('main.host_manager', hm)

    return hm

# --- Test Cases ---

def test_best_host_selection_prefers_loaded_model(mock_host_manager, caplog):
    """
    Tests that the host with the model already loaded is preferred,
    even if another host has more free VRAM.
    """
    host1, host2 = mock_host_manager.hosts

    # Host 1: Model loaded, less VRAM
    host1.available = True
    host1.loaded_models = ['llama3:latest']
    host1.free_vram = 1000

    # Host 2: Model not loaded, more VRAM
    host2.available = True
    host2.loaded_models = []
    host2.free_vram = 5000

    best_host = mock_host_manager.get_best_host('llama3:latest')

    assert best_host is host1
    assert f"Found hosts with 'llama3:latest' already loaded: ['{host1.url}']" in caplog.text

def test_best_host_selection_chooses_max_vram(mock_host_manager, caplog):
    """
    Tests that when no host has the model loaded, the one with the most
    free VRAM is selected.
    """
    host1, host2 = mock_host_manager.hosts

    # Host 1: Less VRAM
    host1.available = True
    host1.loaded_models = []
    host1.free_vram = 1000

    # Host 2: More VRAM
    host2.available = True
    host2.loaded_models = []
    host2.free_vram = 5000

    best_host = mock_host_manager.get_best_host('codellama:latest')

    assert best_host is host2
    assert f"Selected best host for 'codellama:latest': {host2.url}" in caplog.text

# Helper for mocking async iterators
async def mock_aiter_raw_content(content=b'{}'):
    yield content

@pytest.mark.asyncio
async def test_proxy_routing_and_session_creation(client, mock_host_manager, mocker, caplog):
    """
    Tests that a new request is routed to the best host and a session is created.
    It also verifies the logging output for this process.
    """
    # Setup host states
    host1, host2 = mock_host_manager.hosts
    host1.available = False # Make host1 unavailable
    host2.available = True
    host2.loaded_models = ['llama3:latest']
    host2.free_vram = 5000

    # Mock the downstream httpx call
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {'Content-Type': 'application/json'}
    async def mock_aiter_raw_specific():
        yield b'{"response": "mocked"}'
    mock_response.aiter_raw = mock_aiter_raw_specific

    mocker.patch('httpx.AsyncClient.send', return_value=mock_response)

    # The request payload
    payload = {
        "model": "llama3:latest",
        "messages": [{"role": "user", "content": "Why is the sky blue?"}]
    }

    # Make the request
    response = client.post("/api/chat", json=payload)

    assert response.status_code == 200
    assert response.json() == {"response": "mocked"}

    # Verify logging (more robustly)
    assert "miss. Finding best host for model 'llama3:latest'" in caplog.text
    assert f"Assigned new host {host2.url} to session" in caplog.text

    # Verify session was created
    assert len(sessions) == 1
    session_id = list(sessions.keys())[0]
    session_host, _ = sessions[session_id]
    assert session_host is host2

@pytest.mark.asyncio
async def test_session_stickiness(client, mock_host_manager, mocker, caplog):
    """
    Tests that subsequent requests for an existing session are routed to the same host.
    """
    host1, host2 = mock_host_manager.hosts
    host1.available = True
    host1.free_vram = 8000
    host2.available = True
    host2.free_vram = 5000

    mocker.patch('httpx.AsyncClient.send', return_value=MagicMock(status_code=200, headers={}, aiter_raw=lambda: mock_aiter_raw_content()))

    payload = {"model": "llama3:latest", "messages": [{"role": "user", "content": "Initial prompt"}]}
    client.post("/api/chat", json=payload)

    # Clear the logs to isolate the next action
    caplog.clear()

    # Make the second request
    client.post("/api/chat", json=payload)

    # Verify the session hit log message exists in the records
    found_log = any(f"Session hit. Routing to previous host: {host1.url}" in record.message for record in caplog.records)
    assert found_log, "Log message for session hit was not found."

@pytest.mark.asyncio
async def test_session_expiration(client, mock_host_manager, mocker, caplog):
    """
    Tests that a session expires and is re-routed to the new best host.
    """
    original_timeout = SESSION_TIMEOUT_SECONDS
    mocker.patch('main.SESSION_TIMEOUT_SECONDS', 1)

    host1, host2 = mock_host_manager.hosts
    host1.available = True
    host2.available = True

    mocker.patch('httpx.AsyncClient.send', return_value=MagicMock(status_code=200, headers={}, aiter_raw=lambda: mock_aiter_raw_content()))

    # First request to establish session on host2
    host1.free_vram = 1000
    host2.free_vram = 5000
    payload = {"model": "llama3:latest", "messages": [{"role": "user", "content": "Test prompt"}]}
    client.post("/api/chat", json=payload)

    # Clear the logs to isolate the next action
    caplog.clear()

    # Wait for the session to expire
    time.sleep(1.5)

    # Now, make host1 the best host
    host1.free_vram = 8000
    host2.free_vram = 1000

    # Make the same request again
    client.post("/api/chat", json=payload)

    # Verify the expiration and re-assignment logs exist in the records
    expired_log_found = any("Session expired. Finding a new host." in record.message for record in caplog.records)
    reassigned_log_found = any(f"Assigned new host {host1.url} to session." in record.message for record in caplog.records)

    assert expired_log_found, "Log message for session expiration was not found."
    assert reassigned_log_found, "Log message for re-assigning to new best host was not found."

    mocker.patch('main.SESSION_TIMEOUT_SECONDS', original_timeout)