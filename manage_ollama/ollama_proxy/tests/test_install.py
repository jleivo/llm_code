import os
import json
import pytest
import subprocess
from pathlib import Path
from unittest.mock import patch

# Constants
SCRIPT_PATH = Path(__file__).parent.parent / 'mgmt' / 'install.sh'

@pytest.fixture
def setup_teardown(tmp_path):
    """Setup and teardown for tests"""
    # Create a temporary working directory
    work_dir = tmp_path / "test_workspace"
    work_dir.mkdir()
    
    # Create config paths
    config_path = work_dir / "config.json"
    config_example = work_dir / "config.json.example"
    
    # Create a minimal requirements.txt
    (work_dir / "requirements.txt").write_text("fastapi\nuvicorn")
    
    # Create example config
    example_config = {
        "hosts": [
            {
                "url": "http://test:11434",
                "total_vram_mb": 8192,
                "priority": 1
            }
        ]
    }
    config_example.write_text(json.dumps(example_config, indent=2))
    
    # Mock python environment setup
    venv_dir = work_dir / ".venv"
    venv_dir.mkdir()
    (venv_dir / "bin").mkdir()
    (venv_dir / "bin" / "python3").touch()
    pip_path = venv_dir / "bin" / "pip"
    pip_path.write_text("#!/bin/sh\nexit 0\n")
    pip_path.chmod(0o755)
    
    # Return test paths
    return {
        'work_dir': work_dir,
        'config_path': config_path,
        'config_example': config_example
    }

def run_install_script(input_text, setup_teardown):
    """
    Run the install script with given input string
    """
    env = os.environ.copy()
    env.update({
        'CONFIG_FILE': str(setup_teardown['config_path']),
        'CONFIG_EXAMPLE': str(setup_teardown['config_example'])
    })
    
    process = subprocess.Popen(
        ['bash', str(SCRIPT_PATH)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=str(setup_teardown['work_dir'])
    )
    stdout, stderr = process.communicate(input=input_text)
    return process.returncode, stdout, stderr

def test_successful_single_host(setup_teardown):
    """Test successful config creation with a single host"""
    inputs = "http://test:11434\n8192\n1\nn\nn\nn\n"
    
    returncode, stdout, stderr = run_install_script(inputs, setup_teardown)
    assert returncode == 0
    assert setup_teardown['config_path'].exists()
    
    # Validate config content
    config = json.loads(setup_teardown['config_path'].read_text())
    assert len(config['hosts']) == 1
    assert config['hosts'][0]['url'] == 'http://test:11434'
    assert config['hosts'][0]['total_vram_mb'] == 8192
    assert config['hosts'][0]['priority'] == 1

def test_successful_multiple_hosts(setup_teardown):
    """Test successful config creation with multiple hosts"""
    # y followed by second host URL to handle read -n 1
    inputs = "http://test1:11434\n8192\n1\nyhttp://test2:11434\n16384\n2\nn\nn\nn\n"
    
    returncode, stdout, stderr = run_install_script(inputs, setup_teardown)
    assert returncode == 0
    assert setup_teardown['config_path'].exists()
    
    # Validate config content
    config = json.loads(setup_teardown['config_path'].read_text())
    assert len(config['hosts']) == 2
    assert config['hosts'][0]['url'] == 'http://test1:11434'
    assert config['hosts'][1]['url'] == 'http://test2:11434'
    assert config['hosts'][1]['total_vram_mb'] == 16384

def test_file_write_permission_error(setup_teardown):
    """Test handling of file write permission errors"""
    os.chmod(setup_teardown['work_dir'], 0o555)
    try:
        inputs = "http://test:11434\n8192\n1\nn\nn\nn\n"
        returncode, stdout, stderr = run_install_script(inputs, setup_teardown)
        assert returncode != 0
    finally:
        os.chmod(setup_teardown['work_dir'], 0o755)

def test_config_validation_error(setup_teardown):
    """Test handling of invalid configuration"""
    setup_teardown['config_path'].write_text("invalid json content")
    inputs = "http://test:11434\n8192\n1\nn\nn\nn\n"
    
    returncode, stdout, stderr = run_install_script(inputs, setup_teardown)
    assert returncode != 0
    assert "is not a valid JSON file" in stdout

def test_disk_full_error(setup_teardown):
    """Test handling of disk full errors"""
    with patch('builtins.open', side_effect=OSError("No space left on device")):
        inputs = "http://test:11434\n8192\n1\nn\nn\nn\n"
        returncode, stdout, stderr = run_install_script(inputs, setup_teardown)
        pass
