import json
import logging
import threading
import time
import requests
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HostManager:
    def __init__(self, config_path):
        self.config_path = config_path
        self.hosts = []
        self.load_config()
        self.lock = threading.Lock()
        self.monitor_thread = threading.Thread(target=self.monitor_hosts, daemon=True)
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

    def get_best_host(self, model_name):
        best_host = None
        max_free_vram = -1

        with self.lock:
            available_hosts = sorted([host for host in self.hosts if host.is_available()], key=lambda h: h.priority or float('inf'))
            logger.info(f"Finding best host for model '{model_name}' among {len(available_hosts)} available hosts, sorted by priority.")

            loaded_hosts = [host for host in available_hosts if model_name in host.get_loaded_models()]

            if loaded_hosts:
                logger.info(f"Found hosts with '{model_name}' already loaded: {[h.url for h in loaded_hosts]}")
                target_hosts = loaded_hosts
            else:
                logger.info(f"No hosts have '{model_name}' loaded. Considering all available hosts.")
                target_hosts = available_hosts

            for host in target_hosts:
                free_vram = host.get_free_vram()
                if free_vram > max_free_vram:
                    max_free_vram = free_vram
                    best_host = host

        if best_host:
            logger.info(f"Selected best host for '{model_name}': {best_host.url} with {max_free_vram}MB free VRAM.")
        else:
            logger.warning(f"No suitable host found for model '{model_name}'.")

        return best_host

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

    def update_status(self):
        if not self.check_availability():
            self.free_vram_mb = -1
            self.loaded_models = []
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
        try:
            response = requests.get(f"{self.url}/api/ps", timeout=5)
            response.raise_for_status()
            models_data = response.json().get('models', [])

            self.loaded_models = [model['name'] for model in models_data]
            logger.info(f"Host {self.url} has loaded models: {self.loaded_models}")

            # **CRITICAL FIX:** Use 'size_vram' for VRAM calculation, not 'size'.
            used_vram_bytes = sum(model.get('size_vram', 0) for model in models_data)
            used_vram_mb = used_vram_bytes / (1024 * 1024)

            if self.total_vram_mb == float('inf'):
                self.free_vram_mb = float('inf')
            else:
                self.free_vram_mb = self.total_vram_mb - used_vram_mb

            logger.info(f"Host {self.url} has {self.free_vram_mb:.2f}MB free VRAM ({used_vram_mb:.2f}MB used).")

        except requests.RequestException as e:
            logger.error(f"Error getting model/VRAM data for host {self.url}: {e}")
            self.loaded_models = []
            self.free_vram_mb = -1

    def is_available(self):
        return self.available

    def get_free_vram(self):
        return self.free_vram_mb

    def get_loaded_models(self):
        return self.loaded_models

    def mark_as_unavailable(self):
        if self.available:
            logger.warning(f"Host {self.url} marked as unavailable due to request error.")
        self.available = False