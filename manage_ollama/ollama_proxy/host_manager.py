import json
import logging
import threading
import time
import requests
import httpx

from lru_tracker import LRUCache
from model_cache import ModelCache

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HostManager:
    def __init__(self, config_path):
        self.config_path = config_path
        self.model_cache = ModelCache()
        self.hosts = []
        self.server_config = {}
        self.load_config()
        self.lock = threading.Lock()
        self.monitor_thread = threading.Thread(target=self.monitor_hosts, daemon=True)

    def start_monitoring(self):
        """Starts the background host monitoring thread."""
        logger.info("Starting background host monitor.")
        self.monitor_thread.start()

    def load_config(self):
        with open(self.config_path, 'r') as f:
            config = json.load(f)
        self.server_config = config.get('server', {})
        self.hosts = [OllamaHost(host_config, self.model_cache) for host_config in config['hosts']]
    
    def get_server_port(self):
        """Returns the server port from config, default is 8080."""
        return self.server_config.get('port', 8080)

    def monitor_hosts(self):
        while True:
            logger.info("Starting host monitoring cycle.")
            for host in self.hosts:
                host.update_status()
            logger.info("Host monitoring cycle finished.")
            time.sleep(60)

    def get_primary_host(self):
        for host in self.hosts:
            if host.priority == 1 and host.is_available():
                return host
        return None

    def refresh_all_hosts_status(self):
        """Forces an immediate refresh of all hosts' status, models, and VRAM."""
        logger.info("Forcing immediate refresh of all host statuses.")
        threads = []
        for host in self.hosts:
            thread = threading.Thread(target=host.update_status)
            threads.append(thread)
            thread.start()
        for thread in threads:
            thread.join()
        logger.info("Finished refreshing all host statuses.")

    def get_best_host(self, model_name, excluded_urls=None):
        """
        Finds the best host for a given model, optionally excluding some hosts.
        The logic is as follows:
        1. Prioritize hosts that already have the model loaded in VRAM, preferring hosts with more free VRAM
           when multiple hosts have the model loaded (even if lower priority).
        2. Second, prioritize hosts that have the model on disk (but not loaded), preferring those with more free VRAM.
        3. If no host has the model, select the available host with the most free VRAM.
        4. If no host has enough free VRAM but can evict models via LRU, select the host where LRU eviction
           would free enough space (with fewest evictions preferred).
        """
        if excluded_urls is None:
            excluded_urls = []

        with self.lock:
            available_hosts = sorted(
                [h for h in self.hosts if h.is_available() and h.url not in excluded_urls],
                key=lambda h: h.priority or float('inf')
            )
            logger.info(f"Finding best host for model '{model_name}' among {len(available_hosts)} available hosts (excluding {len(excluded_urls)}).")

            # 1. Prioritize hosts with the model already loaded in VRAM.
            loaded_hosts = [host for host in available_hosts if model_name in host.get_loaded_models()]
            if loaded_hosts:
                # Sort by free VRAM (descending) to prefer hosts with more available memory
                loaded_hosts_sorted = sorted(loaded_hosts, key=lambda h: h.get_free_vram(), reverse=True)
                best_host = loaded_hosts_sorted[0]
                logger.info(f"Found host with '{model_name}' loaded in VRAM: {best_host.url} (Priority: {best_host.priority}, Free VRAM: {best_host.get_free_vram():.2f}MB)")
                return best_host

            # 2. Prioritize hosts with the model on disk (but not loaded).
            local_hosts = [host for host in available_hosts if model_name in host.get_local_models()]
            if local_hosts:
                local_hosts_sorted = sorted(local_hosts, key=lambda h: h.get_free_vram(), reverse=True)
                best_host = local_hosts_sorted[0]
                logger.info(f"Found host with '{model_name}' available locally on disk: {best_host.url} (Priority: {best_host.priority}, Free VRAM: {best_host.get_free_vram():.2f}MB)")
                return best_host

            # 3. Find host with most free VRAM (no eviction needed)
            best_host_by_vram = None
            max_free_vram = -1
            for host in available_hosts:
                free_vram = host.get_free_vram()
                if free_vram > max_free_vram:
                    max_free_vram = free_vram
                    best_host_by_vram = host

            # 4. If no host has enough VRAM, check if LRU eviction would work
            if best_host_by_vram:
                # Get estimated model size (0 if unknown, which means it might fit)
                model_size = best_host_by_vram.get_model_size(model_name) or 0
                if max_free_vram >= model_size:
                    logger.info(f"Selected best host for '{model_name}': {best_host_by_vram.url} with {max_free_vram:.2f}MB free VRAM.")
                    return best_host_by_vram

            # Try LRU eviction scenario
            eviction_candidates = []
            for host in available_hosts:
                model_size = host.get_model_size(model_name) or 0
                if model_size == 0:
                    continue  # Skip if size unknown
                evictable = host.get_models_to_evict(model_size)
                if evictable:
                    eviction_candidates.append((host, evictable, model_size))

            if eviction_candidates:
                # Prefer host with fewest evictions, then most free VRAM
                eviction_candidates.sort(key=lambda x: (len(x[1]), -x[0].get_free_vram()))
                best_eviction = eviction_candidates[0]
                logger.info(f"Selected host {best_eviction[0].url} with LRU eviction of {len(best_eviction[1])} models for '{model_name}'.")
                return best_eviction[0]

            logger.warning(f"No suitable host found for model '{model_name}'.")
            return None

    async def pull_model_on_host(self, host, model_name):
        """
        Pulls a model to a specified host using the /api/pull endpoint.
        Streams the response and logs the progress. Returns True on success, False on failure.
        """
        url = f"{host.url}/api/pull"
        payload = {"name": model_name, "stream": True}
        logger.info(f"Attempting to pull model '{model_name}' on host {host.url}...")

        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("POST", url, json=payload) as response:
                    if response.status_code != 200:
                        response_body = await response.aread()
                        logger.error(f"Failed to initiate model pull for '{model_name}' on {host.url}. Status: {response.status_code}, Body: {response_body.decode()}")
                        return False

                    async for chunk in response.aiter_bytes():
                        try:
                            lines = chunk.decode('utf-8').splitlines()
                            for line in lines:
                                if not line:
                                    continue
                                data = json.loads(line)
                                if 'status' in data:
                                    status = data['status']
                                    progress = ""
                                    if 'total' in data and 'completed' in data and data['total'] > 0:
                                        progress = f"({(data['completed'] / data['total']) * 100:.2f}%)"
                                    logger.info(f"Pulling '{model_name}' on {host.url}: {status} {progress}")
                                if 'error' in data:
                                    logger.error(f"Error pulling model '{model_name}' on {host.url}: {data['error']}")
                                    return False
                        except json.JSONDecodeError:
                            logger.warning(f"Could not decode JSON from pull stream chunk: {chunk}")

            logger.info(f"Successfully pulled model '{model_name}' to host {host.url}.")
            host.update_status()  # Refresh host status to reflect new model and VRAM usage.
            return True

        except httpx.RequestError as e:
            logger.error(f"Request error while trying to pull model on {host.url}: {e}")
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred during model pull on {host.url}: {e}")
            return False

    def get_first_available_host(self):
        with self.lock:
            for host in self.hosts:
                if host.is_available():
                    return host
        return None

class OllamaHost:
    def __init__(self, config, model_cache=None):
        self.url = config['url']
        self.total_vram_mb = config.get('total_vram_mb', float('inf'))
        self.priority = config.get('priority')
        self.model_cache = model_cache
        self.available = False
        self.free_vram_mb = -1
        self.loaded_models = []
        self.local_models = []
        self.model_usage_cache = {}  # {model_name: {"size_vram": int, "last_used": float}}
        self._lru_tracker = LRUCache()
        self.load_monitor_url = config.get('load_monitor_url', None)
        self.gpu_load_threshold_pct = config.get('gpu_load_threshold_pct', 80)
        self.gpu_utilization_pct: float = 0.0

    def update_status(self):
        if not self.check_availability():
            self.free_vram_mb = -1
            self.loaded_models = []
            self.local_models = []
            return
        self.update_models_and_vram_from_api()
        self._update_gpu_utilization()

    def _update_gpu_utilization(self) -> None:
        """Poll the load monitor endpoint and update gpu_utilization_pct. Fails open."""
        if not self.load_monitor_url:
            return
        try:
            response = requests.get(f"{self.load_monitor_url}/metrics", timeout=3)
            if response.status_code != 200:
                logger.warning("Load monitor %s returned HTTP %d — using 0%%",
                               self.load_monitor_url, response.status_code)
                return
            data = response.json()
            raw = data.get("gpu_utilization_pct")
            if not isinstance(raw, (int, float)):
                logger.warning("Load monitor %s returned non-numeric gpu_utilization_pct: %r",
                               self.load_monitor_url, raw)
                return
            self.gpu_utilization_pct = min(float(raw), 100.0)
            logger.info("Host %s GPU utilization: %.1f%%", self.url, self.gpu_utilization_pct)
        except Exception as exc:
            logger.warning("Could not reach load monitor %s: %s — failing open",
                           self.load_monitor_url, exc)

    def check_availability(self):
        try:
            response = requests.get(self.url, timeout=5)
            if response.status_code == 200:
                if not self.available:
                    logger.info(f"Host {self.url} is now available.")
                self.available = True
            else:
                if self.available:
                    logger.warning(f"Host {self.url} is now unavailable (status code: {response.status_code}).")
                self.available = False
        except requests.RequestException as e:
            if self.available:
                logger.error(f"Host {self.url} is now unavailable. Error checking availability: {e}")
            self.available = False
        return self.available

    def update_models_and_vram_from_api(self):
        # First, update loaded models and VRAM from /api/ps
        try:
            response = requests.get(f"{self.url}/api/ps", timeout=5)
            response.raise_for_status()
            models_data = response.json().get('models', [])

            self.loaded_models = [model['name'] for model in models_data]
            logger.info(f"Host {self.url} has loaded models (in VRAM): {self.loaded_models}")

            used_vram_bytes = sum(model.get('size_vram', 0) for model in models_data)
            used_vram_mb = used_vram_bytes / (1024 * 1024)

            if self.total_vram_mb == float('inf'):
                self.free_vram_mb = float('inf')
            else:
                self.free_vram_mb = self.total_vram_mb - used_vram_mb

            logger.info(f"Host {self.url} has {self.free_vram_mb:.2f}MB free VRAM ({used_vram_mb:.2f}MB used).")

            # Update model usage cache with sizes from /api/ps
            self.update_model_usage_cache(models_data)

        except requests.RequestException as e:
            logger.error(f"Error getting loaded model/VRAM data for host {self.url}: {e}")
            self.loaded_models = []
            self.free_vram_mb = -1

        # Second, update the list of all local models from /api/tags
        try:
            response = requests.get(f"{self.url}/api/tags", timeout=5)
            response.raise_for_status()
            models_data = response.json().get('models', [])
            self.local_models = [model['name'] for model in models_data]
            logger.info(f"Host {self.url} has local models (on disk): {self.local_models}")
        except requests.RequestException as e:
            logger.error(f"Error getting local model list for host {self.url}: {e}")
            self.local_models = []

    def is_available(self):
        return self.available

    def get_free_vram(self):
        return self.free_vram_mb

    def get_loaded_models(self):
        return self.loaded_models

    def get_local_models(self):
        return self.local_models

    def mark_as_unavailable(self):
        if self.available:
            logger.warning(f"Host {self.url} marked as unavailable due to request error.")
        self.available = False

    def update_model_usage_cache(self, models_data: list):
        """
        Update the model usage cache from /api/ps response data.
        Stores size_vram and maintains LRU tracking.
        """
        for model in models_data:
            name = model.get('name')
            if name:
                size_vram = model.get('size_vram', 0)
                self.model_usage_cache[name] = {
                    "size_vram": size_vram,
                    "last_used": time.time()  # Update LRU timestamp
                }
                self._lru_tracker.record_usage(name)
                # Persist to global cache
                if self.model_cache:
                    self.model_cache.update_model_size(self.url, name, size_vram)

    def get_model_size(self, model_name: str) -> int | None:
        """Get the cached size_vram for a model."""
        info = self.model_usage_cache.get(model_name)
        if info and info.get('size_vram') is not None:
            return info['size_vram']

        # Fallback to persistent cache
        if self.model_cache:
            size = self.model_cache.get_model_size(self.url, model_name)
            if size is not None:
                # Update memory cache with retrieved value
                self.model_usage_cache[model_name] = {
                    "size_vram": size,
                    "last_used": time.time()
                }
                return size

        return None

    def get_models_sorted_by_lru(self) -> list:
        """Return models sorted by LRU (oldest first)."""
        return self._lru_tracker.get_all_models_sorted_by_lru()

    def get_models_to_evict(self, required_vram: int) -> list:
        """
        Return list of model names to evict to free required_vram.
        Returns empty list if enough space already available.
        """
        current_free = self.get_free_vram()
        if current_free >= required_vram:
            return []

        needed = required_vram - current_free
        models_to_evict = []
        evicted_size = 0

        # Sort by LRU, evict oldest first
        lru_models = self.get_models_sorted_by_lru()

        for model_name in lru_models:
            if model_name not in self.loaded_models:
                continue  # Skip if not currently loaded
            size = self.get_model_size(model_name)
            if size is None:
                continue  # Skip if size unknown
            models_to_evict.append(model_name)
            evicted_size += size
            if evicted_size >= needed:
                break

        return models_to_evict

    def record_model_usage(self, model_name: str):
        """Record that a model was used (for LRU tracking)."""
        self._lru_tracker.record_usage(model_name)