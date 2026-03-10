import pytest
import time
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from lru_tracker import LRUCache


def test_record_and_get_lru():
    """Test recording usage and getting LRU model."""
    cache = LRUCache()
    cache.record_usage('model1')
    time.sleep(0.01)  # Small delay to ensure timestamp difference
    cache.record_usage('model2')
    time.sleep(0.01)
    cache.record_usage('model3')

    assert cache.get_lru_model() == 'model1'


def test_get_all_models_sorted():
    """Test getting all models sorted by LRU."""
    cache = LRUCache()
    cache.record_usage('model1')
    time.sleep(0.01)
    cache.record_usage('model2')
    time.sleep(0.01)
    cache.record_usage('model3')

    models = cache.get_all_models_sorted_by_lru()
    assert models == ['model1', 'model2', 'model3']


def test_remove_model():
    """Test removing a model from tracking."""
    cache = LRUCache()
    cache.record_usage('model1')
    cache.record_usage('model2')
    cache.remove_model('model1')

    assert cache.get_lru_model() == 'model2'
    assert cache.get_all_models_sorted_by_lru() == ['model2']


def test_clear():
    """Test clearing all tracking data."""
    cache = LRUCache()
    cache.record_usage('model1')
    cache.record_usage('model2')
    cache.clear()

    assert cache.get_lru_model() is None
    assert cache.get_all_models_sorted_by_lru() == []


def test_empty_cache():
    """Test behavior with empty cache."""
    cache = LRUCache()

    assert cache.get_lru_model() is None
    assert cache.get_all_models_sorted_by_lru() == []
