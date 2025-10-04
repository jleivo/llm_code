import json
import logging
import threading
import time
import requests
import paramiko

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
            for host in self.hosts:
                host.update_status()
            time.sleep(60)

    def get_best_host(self, model_name):
        best_host = None
        max_free_vram = -1

        with self.lock:
            for host in self.hosts:
                if host.is_available() and model_name in host.get_loaded_models():
                    free_vram = host.get_free_vram()
                    if free_vram > max_free_vram:
                        max_free_vram = free_vram
                        best_host = host
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

    def check_availability(self):
        try:
            response = requests.get(self.url, timeout=5)
            if response.status_code == 200:
                self.available = True
                logger.info(f"Host {self.url} is available.")
            else:
                self.available = False
                logger.warning(f"Host {self.url} is unavailable (status code: {response.status_code}).")
        except requests.RequestException as e:
            self.available = False
            logger.error(f"Error checking availability for host {self.url}: {e}")

    def update_vram(self):
        if not self.ssh_host:
            self.free_vram = float('inf') # Assume infinite if no SSH details
            return
        try:
            with paramiko.SSHClient() as ssh:
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(self.ssh_host, username=self.ssh_user, password=self.ssh_pass, timeout=10)
                stdin, stdout, stderr = ssh.exec_command("nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits")
                output = stdout.read().decode('utf-8').strip()
                if output:
                    self.free_vram = int(output)
                    logger.info(f"Host {self.url} has {self.free_vram}MB free VRAM.")
                else:
                    self.free_vram = 0
        except Exception as e:
            logger.error(f"Error updating VRAM for host {self.url}: {e}")
            self.free_vram = -1


    def update_loaded_models(self):
        try:
            response = requests.get(f"{self.url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get('models', [])
                self.loaded_models = [model['name'] for model in models]
                logger.info(f"Host {self.url} has loaded models: {self.loaded_models}")
            else:
                self.loaded_models = []
        except requests.RequestException as e:
            logger.error(f"Error updating loaded models for host {self.url}: {e}")
            self.loaded_models = []

    def is_available(self):
        return self.available

    def get_free_vram(self):
        return self.free_vram

    def get_loaded_models(self):
        return self.loaded_models

import os

if __name__ == '__main__':
    # Example usage
    script_dir = os.path.dirname(__file__)
    config_path = os.path.join(script_dir, 'config.json')
    manager = HostManager(config_path)
    time.sleep(5) # Give the monitor thread time to run
    best_host = manager.get_best_host('llama3')
    if best_host:
        print(f"Best host for llama3 is {best_host.url}")
    else:
        print("No suitable host found for llama3")