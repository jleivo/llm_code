import time


class ModelCache:
    """Cache for model sizes (size_vram) from /api/ps responses."""

    def __init__(self):
        self._sizes = {}  # {model_name: size_vram_bytes}
        self._last_updated = {}  # {model_name: timestamp}

    def update_model_size(self, model_name: str, size_vram: int):
        """Update the cached size for a model."""
        self._sizes[model_name] = size_vram
        self._last_updated[model_name] = time.time()

    def get_model_size(self, model_name: str) -> int | None:
        """Get the cached size for a model, or None if not found."""
        return self._sizes.get(model_name)

    def get_all_models(self) -> list:
        """Return all model names in the cache."""
        return list(self._sizes.keys())

    def update_models(self, models_data: list):
        """Update cache from a list of model dictionaries (from /api/ps)."""
        for model in models_data:
            name = model.get('name')
            size_vram = model.get('size_vram', 0)
            if name is not None:
                self.update_model_size(name, size_vram)

    def clear(self):
        """Clear all cached data."""
        self._sizes.clear()
        self._last_updated.clear()
