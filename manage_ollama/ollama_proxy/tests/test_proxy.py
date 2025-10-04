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
    # Prevent background threads from starting
    mocker.patch('threading.Thread.start')
    mocker.patch.object(HostManager, 'load_config', return_value=None)

    mock_hm = HostManager('dummy_config.json')

    # Define mock hosts
    host1 = OllamaHost({'url': 'http://host1:11434'})
    host2 = OllamaHost({'url': 'http://host2:11434', 'ssh_host': 'host2', 'ssh_user': 'user', 'ssh_pass': 'pass'})
    mock_hm.hosts = [host1, host2]

    # Patch the global variable in the main module
    mocker.patch.object(main, 'host_manager', mock_hm)

    return mock_hm

@pytest.fixture
def client():
    """Provides a TestClient for the FastAPI app."""
    with TestClient(main.app) as c:
        yield c

# --- Test Cases ---

def test_best_host_selection_prefers_loaded_model(mock_host_manager, caplog):
    """
    Tests that the host with the model already loaded is preferred.
    """
    host1, host2 = mock_host_manager.hosts

    host1.available = True
    host1.loaded_models = ['llama3:latest']
    host1.free_vram = 1000

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

    host1.available = True
    host1.loaded_models = []
    host1.free_vram = 1000

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
    """
    host1, host2 = mock_host_manager.hosts
    host1.available = False
    host2.available = True
    host2.loaded_models = ['llama3:latest']
    host2.free_vram = 5000

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
    assert response.json() == {"response": "mocked"}
    assert "Session miss. Finding best host for model 'llama3:latest'." in caplog.text
    assert f"Assigned new host {host2.url} to session." in caplog.text

    assert len(main.sessions) == 1
    session_id = list(main.sessions.keys())[0]
    session_host, _ = main.sessions[session_id]
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
    caplog.clear()

    client.post("/api/chat", json=payload)

    found_log = any(f"Session hit. Routing to previous host: {host1.url}" in record.message for record in caplog.records)
    assert found_log, "Log message for session hit was not found."

@pytest.mark.asyncio
async def test_session_expiration(client, mock_host_manager, mocker, caplog):
    """
    Tests that a session expires and is re-routed to the new best host.
    """
    mocker.patch.object(main, 'SESSION_TIMEOUT_SECONDS', 1)

    host1, host2 = mock_host_manager.hosts
    host1.available = True
    host2.available = True

    mocker.patch('httpx.AsyncClient.send', return_value=MagicMock(status_code=200, headers={}, aiter_raw=lambda: mock_aiter_raw_content()))

    host1.free_vram = 1000
    host2.free_vram = 5000
    payload = {"model": "llama3:latest", "messages": [{"role": "user", "content": "Test prompt"}]}
    client.post("/api/chat", json=payload)
    caplog.clear()

    time.sleep(1.5)

    host1.free_vram = 8000
    host2.free_vram = 1000

    client.post("/api/chat", json=payload)

    expired_log_found = any("Session expired. Finding a new host." in record.message for record in caplog.records)
    reassigned_log_found = any(f"Assigned new host {host1.url} to session." in record.message for record in caplog.records)

    assert expired_log_found, "Log message for session expiration was not found."
    assert reassigned_log_found, "Log message for re-assigning to new best host was not found."

@pytest.mark.asyncio
async def test_routing_with_no_models_loaded(client, mock_host_manager, mocker, caplog):
    """
    Tests that when multiple hosts are available but none have the model loaded,
    the one with the most free VRAM is chosen.
    """
    host1, host2 = mock_host_manager.hosts
    host1.available = True
    host1.free_vram = 2000
    host1.loaded_models = []

    host2.available = True
    host2.free_vram = 8000
    host2.loaded_models = []

    mocker.patch('httpx.AsyncClient.send', return_value=MagicMock(status_code=200, headers={}, aiter_raw=lambda: mock_aiter_raw_content()))

    payload = {"model": "new-model:latest", "messages": [{"role": "user", "content": "Test"}]}
    client.post("/api/chat", json=payload)

    found_log = any(f"Assigned new host {host2.url} to session." in record.message for record in caplog.records)
    assert found_log, "Did not route to the host with the most VRAM."

@pytest.mark.asyncio
async def test_rerouting_after_host_disappearance(client, mock_host_manager, mocker, caplog):
    """
    Tests that if a session's assigned host becomes unavailable, the proxy
    re-routes to the next best host.
    """
    host1, host2 = mock_host_manager.hosts

    host1.available = True
    host1.free_vram = 8000
    host2.available = True
    host2.free_vram = 2000

    mocker.patch('httpx.AsyncClient.send', return_value=MagicMock(status_code=200, headers={}, aiter_raw=lambda: mock_aiter_raw_content()))

    payload = {"model": "llama3:latest", "messages": [{"role": "user", "content": "Initial prompt"}]}

    client.post("/api/chat", json=payload)

    host1.available = False
    caplog.clear()

    client.post("/api/chat", json=payload)

    found_unavailable_log = any(f"Session host {host1.url} is unavailable. Finding a new host." in record.message for record in caplog.records)
    found_reassigned_log = any(f"Assigned new host {host2.url} to session." in record.message for record in caplog.records)
    assert found_unavailable_log, "Log for unavailable session host not found."
    assert found_reassigned_log, "Did not re-route to the next best host."

@pytest.mark.asyncio
async def test_routing_to_newly_appeared_host(client, mock_host_manager, mocker, caplog):
    """
    Tests that if a new, better host appears, it gets chosen for new sessions.
    """
    host1, host2 = mock_host_manager.hosts

    host1.available = False
    host2.available = True
    host2.free_vram = 2000

    mocker.patch('httpx.AsyncClient.send', return_value=MagicMock(status_code=200, headers={}, aiter_raw=lambda: mock_aiter_raw_content()))

    payload1 = {"model": "model1", "messages": [{"role": "user", "content": "Prompt 1"}]}
    client.post("/api/chat", json=payload1)
    assert any(f"Assigned new host {host2.url} to session." in record.message for record in caplog.records)

    host1.available = True
    host1.free_vram = 16000
    caplog.clear()

    payload2 = {"model": "model2", "messages": [{"role": "user", "content": "Prompt 2"}]}
    client.post("/api/chat", json=payload2)

    assert any(f"Assigned new host {host1.url} to session." in record.message for record in caplog.records)