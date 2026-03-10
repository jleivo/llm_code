import time


def get_timestamp():
    """Returns current time as float for timestamp tracking."""
    return time.time()


class LRUCache:
    """Simple LRU tracker using timestamp-based ordering."""

    def __init__(self):
        self._usage = {}  # {model_name: timestamp}

    def record_usage(self, model_name: str):
        """Record that a model was used at the current timestamp."""
        self._usage[model_name] = get_timestamp()

    def get_lru_model(self) -> str | None:
        """Returns the least recently used model name, or None if empty."""
        if not self._usage:
            return None
        return min(self._usage, key=self._usage.get)

    def get_all_models_sorted_by_lru(self) -> list:
        """Returns all models sorted by LRU (oldest first)."""
        return sorted(self._usage.keys(), key=lambda m: self._usage[m])

    def remove_model(self, model_name: str):
        """Remove a model from tracking."""
        self._usage.pop(model_name, None)

    def clear(self):
        """Clear all tracking data."""
        self._usage.clear()
