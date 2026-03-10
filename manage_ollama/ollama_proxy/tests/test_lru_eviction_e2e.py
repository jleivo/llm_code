import pytest
import time
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from host_manager import HostManager, OllamaHost


@pytest.fixture
def mock_host_manager_for_logic(mocker):
    """Provides a HostManager instance with mocked-out network calls for testing logic."""
    mocker.patch.object(HostManager, 'load_config', return_value=None)
    hm = HostManager('dummy_config.json')

    host_p1_vram_high = OllamaHost({'url': 'http://priority1:11434', 'priority': 1, 'total_vram_mb': 16000})
    host_p2_vram_low = OllamaHost({'url': 'http://priority2:11434', 'priority': 2, 'total_vram_mb': 8000})
    host_p3_vram_mid = OllamaHost({'url': 'http://priority3:11434', 'priority': 3, 'total_vram_mb': 12000})

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


def test_lru_eviction_selection_when_vram_insufficient(mock_host_manager_for_logic, mocker):
    """
    Test: When VRAM is insufficient on all hosts with known model sizes,
    get_best_host should select a host where LRU eviction would free enough space.

    In this test, host1 is chosen because:
    - model size is 6000MB (known)
    - host1: 2000MB free + can evict old-model (3MB) + newer-model (4MB) = 9MB total (2 evictions)
    - host2: 4000MB free + can evict existing-model (2MB) = 6MB total (1 eviction)
    - host3: 3000MB free, can't evict (no loaded models with known size)

    Host2 is selected because it requires the fewest evictions (1) to free enough space.
    """
    hm, (host1, host2, host3) = mock_host_manager_for_logic

    # Set up host1 with loaded models but limited VRAM, and known model sizes
    host1.available = True
    host1.total_vram_mb = 8000
    host1.free_vram_mb = 2000  # Limited
    host1.loaded_models = ['old-model', 'newer-model']
    host1.local_models = []

    models_data = [
        {'name': 'old-model', 'size_vram': 3000},
        {'name': 'newer-model', 'size_vram': 4000}
    ]
    host1.update_model_usage_cache(models_data)

    # Record LRU timing - old-model is older
    host1._lru_tracker.record_usage('old-model')
    time.sleep(0.01)
    host1._lru_tracker.record_usage('newer-model')

    # Set up host2 with limited VRAM and known model sizes
    host2.available = True
    host2.total_vram_mb = 8000
    host2.free_vram_mb = 4000  # More than host1's 2000MB
    host2.loaded_models = ['existing-model']  # Has loaded model
    host2.local_models = []
    host2.update_model_usage_cache([{'name': 'existing-model', 'size_vram': 2000}])

    # Set up host3 with limited VRAM and no evictable models
    host3.available = True
    host3.total_vram_mb = 8000
    host3.free_vram_mb = 3000
    host3.loaded_models = []
    host3.local_models = []

    # Set model size for the new-model on all hosts
    host1.model_usage_cache['new-model'] = {'size_vram': 6000, 'last_used': time.time()}
    host2.model_usage_cache['new-model'] = {'size_vram': 6000, 'last_used': time.time()}
    host3.model_usage_cache['new-model'] = {'size_vram': 6000, 'last_used': time.time()}

    # Request a model that needs 6000MB
    best_host = hm.get_best_host('new-model')

    # Host2 should be selected because it requires the fewest evictions (1) to free enough space
    # host2: 4000MB free + evict existing-model (2MB) = 6000MB total (1 eviction)
    # host1: 2000MB free + evict both models (7MB) = 9000MB total (2 evictions)
    assert best_host is host2, f"Expected host2 (fewest evictions), got {best_host.url}"

    # Verify LRU eviction would work for host1 (which has older models)
    evict1 = host1.get_models_to_evict(6000)
    assert 'old-model' in evict1, f"Expected old-model in evict list for host1, got {evict1}"
