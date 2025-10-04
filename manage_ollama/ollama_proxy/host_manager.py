import json
import logging
import threading
import time
import requests
import paramiko
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

    def get_best_host(self, model_name):
        best_host = None
        max_free_vram = -1

        with self.lock:
            available_hosts = [host for host in self.hosts if host.is_available()]
            logger.info(f"Finding best host for model '{model_name}' among {len(available_hosts)} available hosts.")

            # Prefer hosts where the model is already loaded
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

class OllamaHost:
    def __init__(self, config):
        self.url = config['url']
        self.ssh_host = config.get('ssh_host')
        self.ssh_user = config.get('ssh_user')
        self.ssh_pass = config.get('ssh_pass')
        self.available = False
        self.free_vram = -1
        self.loaded_models = []

    def update_status(self):
        self.check_availability()
        if self.available:
            self.update_vram()
            self.update_loaded_models()
        else:
            # If host is not available, reset its stats
            self.free_vram = -1
            self.loaded_models = []


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

    def update_vram(self):
        if not self.ssh_host:
            self.free_vram = float('inf') # Assume effectively infinite if no SSH details
            return
        try:
            with paramiko.SSHClient() as ssh:
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(self.ssh_host, username=self.ssh_user, password=self.ssh_pass, timeout=10)
                # Query for free memory in MiB
                stdin, stdout, stderr = ssh.exec_command("nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits")
                output = stdout.read().decode('utf-8').strip()
                err = stderr.read().decode('utf-8').strip()
                if err:
                    logger.error(f"Error getting VRAM for host {self.url}: {err}")
                    self.free_vram = -1
                elif output:
                    self.free_vram = int(output)
                    logger.info(f"Host {self.url} has {self.free_vram}MB free VRAM.")
                else:
                    self.free_vram = 0 # No output means no free VRAM or command failed silently
        except Exception as e:
            logger.error(f"Failed to update VRAM for host {self.url} via SSH: {e}")
            self.free_vram = -1


    def update_loaded_models(self):
        try:
            # Using the /api/ps endpoint which is more standard in recent Ollama versions
            response = requests.get(f"{self.url}/api/ps", timeout=5)
            response.raise_for_status()
            models_data = response.json().get('models', [])
            self.loaded_models = [model['name'] for model in models_data]
            logger.info(f"Host {self.url} has loaded models: {self.loaded_models}")
        except requests.RequestException as e:
            logger.error(f"Error getting loaded models for host {self.url}: {e}")
            self.loaded_models = []

    def is_available(self):
        return self.available

    def get_free_vram(self):
        return self.free_vram

    def get_loaded_models(self):
        return self.loaded_models

if __name__ == '__main__':
    # Example usage
    script_dir = os.path.dirname(__file__)
    config_path = os.path.join(script_dir, 'config.json.example')
    # Create dummy config if it doesn't exist for testing
    if not os.path.exists(config_path):
        with open(config_path, 'w') as f:
            json.dump({"hosts": [{"url": "http://localhost:11434"}]}, f)

    manager = HostManager(config_path)
    print("Host manager initialized. Monitoring in the background...")
    time.sleep(5) # Give the monitor thread time to run a cycle
    print("\nAttempting to find best host for 'llama3'...")
    best_host = manager.get_best_host('llama3')
    if best_host:
        print(f"Best host for llama3 is {best_host.url}")
    else:
        print("No suitable host found for llama3")

    print("\nFinal host statuses:")
    for host in manager.hosts:
        print(f"  - Host: {host.url}, Available: {host.available}, Free VRAM: {host.free_vram}, Models: {host.loaded_models}")