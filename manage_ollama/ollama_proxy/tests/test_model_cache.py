import pytest
import time
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from model_cache import ModelCache


def test_update_and_get_model_size():
    """Test updating and retrieving model size."""
    cache = ModelCache()
    cache.update_model_size('model1', 1024)

    assert cache.get_model_size('model1') == 1024
    assert cache.get_model_size('model2') is None


def test_update_models_from_list():
    """Test updating cache from list of model data."""
    cache = ModelCache()
    models_data = [
        {'name': 'model1', 'size_vram': 1024},
        {'name': 'model2', 'size_vram': 2048},
        {'name': 'model3'}  # Missing size_vram
    ]

    cache.update_models(models_data)

    assert cache.get_model_size('model1') == 1024
    assert cache.get_model_size('model2') == 2048
    assert cache.get_model_size('model3') == 0  # Default to 0


def test_get_all_models():
    """Test getting all model names."""
    cache = ModelCache()
    cache.update_model_size('model1', 1024)
    cache.update_model_size('model2', 2048)

    models = cache.get_all_models()
    assert set(models) == {'model1', 'model2'}


def test_clear():
    """Test clearing cache."""
    cache = ModelCache()
    cache.update_model_size('model1', 1024)
    cache.clear()

    assert cache.get_model_size('model1') is None
