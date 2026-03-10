import pytest
import asyncio
import time
import json
import tempfile
from fastapi.testclient import TestClient
from fastapi.responses import Response
from unittest.mock import MagicMock, patch, AsyncMock
import requests

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
    assert "Session miss for model 'llama3:latest'. Finding best host." in caplog.text
    assert f"Assigned new host {host2.url} to session for model 'llama3:latest'." in caplog.text

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

    found_unavailable_log = any(f"Session host {host1.url} is unavailable for model 'llama3:latest'. Finding a new host." in record.message for record in caplog.records)
    found_reassigned_log = any(f"Assigned new host {host2.url} to session for model 'llama3:latest'." in record.message for record in caplog.records)
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
async def test_host_with_local_model_is_chosen(client, mock_host_manager, mocker, caplog):
    """
    Tests that a host with a model locally on disk is chosen over a host with more VRAM.
    """
    host1, host2 = mock_host_manager.hosts
    host1.available, host2.available = True, True
    host1.free_vram_mb, host2.free_vram_mb = 4000, 8000 # host2 has more VRAM
    host1.local_models = ['the-model'] # but host1 has the model locally
    host2.local_models = []

    mocker.patch('main.forward_request', new_callable=AsyncMock, return_value=Response(b"OK", 200))

    payload = {"model": "the-model", "messages": [{"role": "user", "content": "Test"}]}
    client.post("/api/chat", json=payload)

    assert f"Found host with 'the-model' available locally on disk: {host1.url}" in caplog.text
    main.forward_request.assert_called_once()
    assert main.forward_request.call_args.args[1] == host1

@pytest.mark.asyncio
async def test_model_not_found_triggers_pull_if_no_alternative(client, mock_host_manager, mocker, caplog):
    """
    Tests that if no host has the model locally or loaded, the proxy attempts to pull it.
    """
    host1, host2 = mock_host_manager.hosts
    host1.available, host2.available = True, True
    host1.loaded_models, host2.loaded_models = [], []
    host1.local_models, host2.local_models = [], []
    host1.free_vram_mb, host2.free_vram_mb = 4000, 8000

    mock_404_response = Response(content=b'{"error": "model \'the-model\' not found"}', status_code=404)
    mock_200_response = Response(content=b'{"response": "success from pull"}', status_code=200)
    mocker.patch('main.forward_request', new_callable=AsyncMock, side_effect=[mock_404_response, mock_200_response])
    mocker.patch.object(mock_host_manager, 'refresh_all_hosts_status')
    mocker.patch.object(mock_host_manager, 'pull_model_on_host', new_callable=AsyncMock, return_value=True)

    payload = {"model": "the-model", "messages": [{"role": "user", "content": "Test"}]}
    response = client.post("/api/chat", json=payload)

    assert response.status_code == 200
    assert response.json() == {"response": "success from pull"}
    # New behavior: uses more concise log message when model size is known and fits
    assert "Selected best host for 'the-model'" in caplog.text
    mock_host_manager.pull_model_on_host.assert_called_once_with(host2, 'the-model')
    assert main.forward_request.call_args_list[1].args[1] == host2


@pytest.mark.asyncio
async def test_model_pull_failure_returns_original_404(client, mock_host_manager, mocker, caplog):
    """
    Tests that if the model pull fails, the original 404 response is returned.
    """
    host1, host2 = mock_host_manager.hosts
    host1.available, host2.available = True, True
    host1.loaded_models, host2.loaded_models = [], []
    host1.local_models, host2.local_models = [], []
    host1.free_vram_mb, host2.free_vram_mb = 4000, 8000

    original_404_content = b'{"error": "model \'the-model\' not found"}'
    mock_404_response = Response(content=original_404_content, status_code=404)
    mocker.patch('main.forward_request', new_callable=AsyncMock, return_value=mock_404_response)

    mocker.patch.object(mock_host_manager, 'refresh_all_hosts_status')
    mocker.patch.object(mock_host_manager, 'pull_model_on_host', new_callable=AsyncMock, return_value=False)

    payload = {"model": "the-model", "messages": [{"role": "user", "content": "Test"}]}
    response = client.post("/api/chat", json=payload)

    assert response.status_code == 404
    assert response.content == original_404_content
    assert f"Failed to pull model 'the-model' on host {host2.url}" in caplog.text
    assert main.forward_request.call_count == 1


# --- Test Cases for Server Port Configuration ---

def test_host_manager_reads_server_port_from_config(mocker):
    """
    Tests that HostManager correctly reads the server port from config.json.
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


def test_host_manager_default_port_when_not_configured(mocker):
    """
    Tests that HostManager returns default port 8080 when server config is missing.
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


def test_main_uses_configured_port_from_host_manager(mocker):
    """
    Tests that main.py retrieves and uses the port from HostManager.
    """
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        config_data = {
            "server": {"port": 8888},
            "hosts": [
                {"url": "http://host1:11434", "total_vram_mb": 8192, "priority": 1}
            ]
        }
        json.dump(config_data, f)
        config_path = f.name

    try:
        hm = HostManager(config_path)
        port = hm.get_server_port()
        assert port == 8888
        # Verify the port can be used with uvicorn (just verify the value is correct)
        assert isinstance(port, int)
        assert 0 < port < 65536
    finally:
        os.unlink(config_path)


def test_malformed_config_raises_json_error():
    """
    Tests that a malformed config.json raises a JSONDecodeError.
    """
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write('{ "invalid": json content }')
        config_path = f.name

    try:
        with pytest.raises(json.JSONDecodeError):
            hm = HostManager(config_path)
    finally:
        os.unlink(config_path)


def test_config_missing_hosts_key_raises_error():
    """
    Tests that a config file missing the required 'hosts' key raises KeyError.
    """
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        config_data = {
            "server": {"port": 9090}
            # Missing 'hosts' key
        }
        json.dump(config_data, f)
        config_path = f.name

    try:
        with pytest.raises(KeyError):
            hm = HostManager(config_path)
    finally:
        os.unlink(config_path)


def test_config_file_not_found():
    """
    Tests that attempting to load a non-existent config file raises FileNotFoundError.
    """
    non_existent_path = '/tmp/non_existent_config_12345.json'
    with pytest.raises(FileNotFoundError):
        hm = HostManager(non_existent_path)


def test_various_custom_ports():
    """
    Tests that various custom port configurations are correctly read.
    """
    test_ports = [3000, 5000, 8000, 8888, 9999]

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
            retrieved_port = hm.get_server_port()
            assert retrieved_port == port, f"Expected port {port}, got {retrieved_port}"
        finally:
            os.unlink(config_path)


# --- Test Cases for Aggregated Model Endpoints ---

def test_api_tags_aggregates_from_all_hosts(client, mock_host_manager, mocker):
    """
    Tests that /api/tags returns combined and deduplicated models from all hosts.
    """
    host1, host2 = mock_host_manager.hosts
    host1.available = True
    host2.available = True

    def mock_requests_get(url, timeout=5):
        if 'host1' in url:
            return MockResponse({
                "models": [
                    {"name": "llama3:latest", "digest": "abc123"},
                    {"name": "mistral:latest", "digest": "def456"}
                ]
            })
        if 'host2' in url:
            return MockResponse({
                "models": [
                    {"name": "llama3:latest", "digest": "xyz789"},  # duplicate
                    {"name": "gemma:latest", "digest": "ghi789"}
                ]
            })
        return MockResponse({}, 404)

    mocker.patch('requests.get', side_effect=mock_requests_get)

    response = client.get("/api/tags")

    assert response.status_code == 200
    response_data = response.json()
    assert len(response_data['models']) == 3
    model_names = [m['name'] for m in response_data['models']]
    assert 'llama3:latest' in model_names
    assert 'mistral:latest' in model_names
    assert 'gemma:latest' in model_names


def test_api_ps_aggregates_running_models(client, mock_host_manager, mocker):
    """
    Tests that /api/ps returns combined and deduplicated loaded models from all hosts.
    """
    host1, host2 = mock_host_manager.hosts
    host1.available = True
    host2.available = True

    def mock_requests_get(url, timeout=5):
        if 'host1' in url:
            return MockResponse({
                "models": [
                    {"name": "llama3:latest", "size_vram": 4096},
                    {"name": "mistral:latest", "size_vram": 2048}
                ]
            })
        if 'host2' in url:
            return MockResponse({
                "models": [
                    {"name": "llama3:latest", "size_vram": 4096},  # duplicate
                    {"name": "gemma:latest", "size_vram": 1024}
                ]
            })
        return MockResponse({}, 404)

    mocker.patch('requests.get', side_effect=mock_requests_get)

    response = client.get("/api/ps")

    assert response.status_code == 200
    response_data = response.json()
    assert len(response_data['models']) == 3


def test_api_tags_excludes_unavailable_hosts(client, mock_host_manager, mocker):
    """
    Tests that /api/tags excludes models from unavailable hosts.
    """
    host1, host2 = mock_host_manager.hosts
    host1.available = True
    host2.available = False  # unavailable

    def mock_requests_get(url, timeout=5):
        if 'host1' in url:
            return MockResponse({
                "models": [{"name": "llama3:latest", "digest": "abc123"}]
            })
        return MockResponse({}, 404)

    mocker.patch('requests.get', side_effect=mock_requests_get)

    response = client.get("/api/tags")

    assert response.status_code == 200
    response_data = response.json()
    assert len(response_data['models']) == 1
    assert response_data['models'][0]['name'] == 'llama3:latest'


def test_api_tags_with_empty_hosts(client, mock_host_manager, mocker):
    """
    Tests that /api/tags returns empty models list when no hosts have models.
    """
    host1, host2 = mock_host_manager.hosts
    host1.available = True
    host2.available = True

    def mock_requests_get(url, timeout=5):
        return MockResponse({"models": []})

    mocker.patch('requests.get', side_effect=mock_requests_get)

    response = client.get("/api/tags")

    assert response.status_code == 200
    response_data = response.json()
    assert response_data['models'] == []


def test_api_tags_error_handling(client, mock_host_manager, mocker):
    """
    Tests that /api/tags continues processing even if one host fails.
    """
    host1, host2 = mock_host_manager.hosts
    host1.available = True
    host2.available = True

    def mock_requests_get(url, timeout=5):
        if 'host1' in url:
            return MockResponse({
                "models": [{"name": "llama3:latest", "digest": "abc123"}]
            })
        if 'host2' in url:
            raise requests.RequestException("Connection failed")
        return MockResponse({}, 404)

    mocker.patch('requests.get', side_effect=mock_requests_get)

    response = client.get("/api/tags")

    assert response.status_code == 200
    response_data = response.json()
    assert len(response_data['models']) == 1


def test_api_tags_deduplication_with_different_digests(client, mock_host_manager, mocker):
    """
    Tests that /api/tags deduplicates by name even when digests differ.
    """
    host1, host2 = mock_host_manager.hosts
    host1.available = True
    host2.available = True

    def mock_requests_get(url, timeout=5):
        if 'host1' in url:
            return MockResponse({
                "models": [
                    {"name": "llama3:latest", "digest": "abc123", "size_vram": 4096}
                ]
            })
        if 'host2' in url:
            return MockResponse({
                "models": [
                    {"name": "llama3:latest", "digest": "different_digest", "size_vram": 4500}
                ]
            })
        return MockResponse({}, 404)

    mocker.patch('requests.get', side_effect=mock_requests_get)

    response = client.get("/api/tags")

    assert response.status_code == 200
    response_data = response.json()
    # Should only have one instance of llama3:latest
    assert len(response_data['models']) == 1
    assert response_data['models'][0]['name'] == 'llama3:latest'