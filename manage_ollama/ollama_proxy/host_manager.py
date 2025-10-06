import json
import logging
import threading
import time
import requests
import os
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HostManager:
    def __init__(self, config_path):
        self.config_path = config_path
        self.hosts = []
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
        self.hosts = [OllamaHost(host_config) for host_config in config['hosts']]

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
        1. Prioritize hosts that already have the model loaded in VRAM, respecting priority.
        2. Second, prioritize hosts that have the model on disk (but not loaded), respecting priority.
        3. If no host has the model, select the available host with the most free VRAM to pull to.
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
                best_host = loaded_hosts[0]  # List is already sorted by priority.
                logger.info(f"Found host with '{model_name}' loaded in VRAM: {best_host.url} (Priority: {best_host.priority})")
                return best_host

            # 2. Prioritize hosts with the model on disk (but not loaded).
            local_hosts = [host for host in available_hosts if model_name in host.get_local_models()]
            if local_hosts:
                best_host = local_hosts[0] # List is already sorted by priority.
                logger.info(f"Found host with '{model_name}' available locally on disk: {best_host.url} (Priority: {best_host.priority})")
                return best_host

            # 3. If no host has the model, find the one with the most free VRAM for pulling.
            logger.info(f"No hosts have '{model_name}' available. Selecting host with most free VRAM to pull the model.")
            best_host_by_vram = None
            max_free_vram = -1
            for host in available_hosts:
                free_vram = host.get_free_vram()
                if free_vram > max_free_vram:
                    max_free_vram = free_vram
                    best_host_by_vram = host

            if best_host_by_vram:
                logger.info(f"Selected best host for pulling '{model_name}': {best_host_by_vram.url} with {max_free_vram:.2f}MB free VRAM.")
                return best_host_by_vram

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
    def __init__(self, config):
        self.url = config['url']
        self.total_vram_mb = config.get('total_vram_mb', float('inf'))
        self.priority = config.get('priority')
        self.available = False
        self.free_vram_mb = -1
        self.loaded_models = []
        self.local_models = []

    def update_status(self):
        if not self.check_availability():
            self.free_vram_mb = -1
            self.loaded_models = []
            self.local_models = []
            return
        self.update_models_and_vram_from_api()

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