import pytest
import time
import sys
import os
import tempfile

# Ensure the parent directory is in the path so we can import ModelCache
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from model_cache import ModelCache

@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp()
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)

def test_update_and_get_model_size(temp_db):
    """Test updating and retrieving model size."""
    cache = ModelCache(db_path=temp_db)
    cache.update_model_size('http://host1', 'model1', 1024)

    assert cache.get_model_size('http://host1', 'model1') == 1024
    assert cache.get_model_size('http://host1', 'model2') is None
    assert cache.get_model_size('http://host2', 'model1') is None

def test_get_all_entries(temp_db):
    """Test getting all entries."""
    cache = ModelCache(db_path=temp_db)
    cache.update_model_size('http://host1', 'model1', 1024)
    cache.update_model_size('http://host2', 'model2', 2048)

    entries = cache.get_all_entries()
    assert len(entries) == 2
    # host_url, model_name, size_vram_bytes, last_updated
    entry1 = next(e for e in entries if e[0] == 'http://host1')
    assert entry1[1] == 'model1'
    assert entry1[2] == 1024

def test_clear(temp_db):
    """Test clearing cache."""
    cache = ModelCache(db_path=temp_db)
    cache.update_model_size('http://host1', 'model1', 1024)
    cache.clear()

    assert cache.get_model_size('http://host1', 'model1') is None

def test_persistence(temp_db):
    """Test that data persists across different instances of ModelCache."""
    cache1 = ModelCache(db_path=temp_db)
    cache1.update_model_size('http://host1', 'model1', 1024)

    cache2 = ModelCache(db_path=temp_db)
    assert cache2.get_model_size('http://host1', 'model1') == 1024
