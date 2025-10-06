import os
import json
import pytest
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

# Constants
SCRIPT_PATH = Path(__file__).parent.parent / 'mgmt' / 'install.sh'

# Remove all duplicate and old code leaving only the fixed version
def run_install_script(inputs, env_vars):
    """
    Run the install script with given inputs
    
    Args:
        inputs (list): List of strings to feed as input to the script
        env_vars (dict): Dictionary containing paths and environment variables
    
    Returns:
        tuple: (return_code, stdout, stderr)
    """
    env = os.environ.copy()
    env.update({
        'CONFIG_FILE': str(env_vars['config_path']),
        'CONFIG_EXAMPLE': str(env_vars['config_example'])
    })
    
    # Convert inputs to proper newline-terminated strings
    input_text = '\n'.join(inputs) + '\n'
    
    process = subprocess.Popen(
        ['bash', str(SCRIPT_PATH)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=str(env_vars['work_dir'])
    )
    stdout, stderr = process.communicate(input=input_text)
    print(f"STDOUT: {stdout}")
    print(f"STDERR: {stderr}")
    return process.returncode, stdout, stderr

@pytest.fixture
def mock_file_operations():
    """Mock file operations that might fail"""
    with patch('builtins.open') as mock_open, \
         patch('os.path.exists') as mock_exists, \
         patch('subprocess.Popen') as mock_popen:
        
        mock_process = MagicMock()
        mock_process.communicate.return_value = ('mock stdout', 'mock stderr')
        mock_process.returncode = 0
        mock_popen.return_value = mock_process
        
        yield {
            'open': mock_open,
            'exists': mock_exists,
            'popen': mock_popen
        }

def test_successful_single_host(setup_teardown):
    """Test successful config creation with a single host"""
    inputs = [
        'http://test:11434',  # URL
        '8192',               # VRAM
        '1',                  # Priority
        'n'                   # Don't add another host
    ]
    
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
    inputs = [
        'http://test1:11434',  # First host
        '8192',
        '1',
        'y',                   # Add another host
        'http://test2:11434',  # Second host
        '16384',
        '2',
        'n'                    # Don't add more hosts
    ]
    
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
    with patch('builtins.open', side_effect=PermissionError("Permission denied")):
        inputs = [
            'http://test:11434',
            '8192',
            '1',
            'n'
        ]
        
        returncode, stdout, stderr = run_install_script(inputs, setup_teardown)
        assert returncode != 0
        assert "Permission denied" in stderr

def test_config_validation_error(setup_teardown):
    """Test handling of invalid configuration"""
    # Create an invalid config file
    setup_teardown['config_path'].write_text("invalid json content")
    
    inputs = [
        'http://test:11434',
        '8192',
        '1',
        'n'
    ]
    
    returncode, stdout, stderr = run_install_script(inputs, setup_teardown)
    assert returncode != 0
    assert "not a valid JSON file" in stderr

def test_disk_full_error(setup_teardown):
    """Test handling of disk full errors"""
    with patch('builtins.open', side_effect=OSError("No space left on device")):
        inputs = [
            'http://test:11434',
            '8192',
            '1',
            'n'
        ]
        
        returncode, stdout, stderr = run_install_script(inputs, setup_teardown)
        assert returncode != 0
        assert "No space left on device" in stderr

@pytest.fixture(autouse=True)
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
    (venv_dir / "bin" / "pip").touch()
    
    # Return test paths
    return {
        'work_dir': work_dir,
        'config_path': config_path,
        'config_example': config_example
    }

def run_install_script(inputs, work_dir, config_path, config_example):
    """
    Run the install script with given inputs
    
    Args:
        inputs (list): List of strings to feed as input to the script
        work_dir (Path): Working directory for the script
        config_path (Path): Path to the config file
        config_example (Path): Path to the example config file
    
    Returns:
        tuple: (return_code, stdout, stderr)
    """
    env = os.environ.copy()
    env.update({
        'CONFIG_FILE': str(config_path),
        'CONFIG_EXAMPLE': str(config_example)
    })
    
    # Convert inputs to proper newline-terminated strings
    input_text = '\n'.join(inputs) + '\n'
    
    process = subprocess.Popen(
        ['bash', str(SCRIPT_PATH)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=str(work_dir)
    )
    stdout, stderr = process.communicate(input=input_text)
    return process.returncode, stdout, stderr

@pytest.fixture
def mock_file_operations():
    """Mock file operations that might fail"""
    with patch('builtins.open') as mock_open, \
         patch('os.path.exists') as mock_exists, \
         patch('subprocess.Popen') as mock_popen:
        
        mock_process = MagicMock()
        mock_process.communicate.return_value = ('mock stdout', 'mock stderr')
        mock_process.returncode = 0
        mock_popen.return_value = mock_process
        
        yield {
            'open': mock_open,
            'exists': mock_exists,
            'popen': mock_popen
        }

def test_successful_single_host(setup_teardown):
    """Test successful config creation with a single host"""
    inputs = [
        'http://test:11434',  # URL
        '8192',               # VRAM
        '1',                  # Priority
        'n'                   # Don't add another host
    ]
    
    returncode, stdout, stderr = run_install_script(
        inputs,
        setup_teardown['work_dir'],
        setup_teardown['config_path'],
        setup_teardown['config_example']
    )
    print(f"STDOUT: {stdout}")
    print(f"STDERR: {stderr}")
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
    inputs = [
        'http://test1:11434',  # First host
        '8192',
        '1',
        'y',                   # Add another host
        'http://test2:11434',  # Second host
        '16384',
        '2',
        'n'                    # Don't add more hosts
    ]
    
    returncode, stdout, stderr = run_install_script(
        inputs,
        setup_teardown['work_dir'],
        setup_teardown['config_path'],
        setup_teardown['config_example']
    )
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
    with patch('builtins.open', side_effect=PermissionError("Permission denied")):
        inputs = [
            'http://test:11434',
            '8192',
            '1',
            'n'
        ]
        
        returncode, stdout, stderr = run_install_script(
            inputs,
            setup_teardown['work_dir'],
            setup_teardown['config_path'],
            setup_teardown['config_example']
        )
        assert returncode != 0
        assert "Permission denied" in stderr

def test_config_validation_error(setup_teardown):
    """Test handling of invalid configuration"""
    # Create an invalid config file
    setup_teardown['config_path'].write_text("invalid json content")
    
    inputs = [
        'http://test:11434',
        '8192',
        '1',
        'n'
    ]
    
    returncode, stdout, stderr = run_install_script(
        inputs,
        setup_teardown['work_dir'],
        setup_teardown['config_path'],
        setup_teardown['config_example']
    )
    assert returncode != 0
    assert "not a valid JSON file" in stderr

def test_disk_full_error(setup_teardown):
    """Test handling of disk full errors"""
    with patch('builtins.open', side_effect=OSError("No space left on device")):
        inputs = [
            'http://test:11434',
            '8192',
            '1',
            'n'
        ]
        
        returncode, stdout, stderr = run_install_script(
            inputs,
            setup_teardown['work_dir'],
            setup_teardown['config_path'],
            setup_teardown['config_example']
        )
        assert returncode != 0
        assert "No space left on device" in stderr
    
    yield
    
    # Teardown
    if TEST_CONFIG_PATH.exists():
        TEST_CONFIG_PATH.unlink()
    if TEST_CONFIG_EXAMPLE.exists():
        TEST_CONFIG_EXAMPLE.unlink()

def run_install_script(inputs):
    """
    Run the install script with given inputs
    
    Args:
        inputs (list): List of strings to feed as input to the script
    
    Returns:
        tuple: (return_code, stdout, stderr)
    """
    env = os.environ.copy()
    env.update({
        'CONFIG_FILE': str(TEST_CONFIG_PATH),
        'CONFIG_EXAMPLE': str(TEST_CONFIG_EXAMPLE)
    })
    
    # Convert inputs to proper newline-terminated strings
    input_text = '\\n'.join(inputs) + '\\n'
    
    process = subprocess.Popen(
        ['bash', str(SCRIPT_PATH)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=str(Path(SCRIPT_PATH).parent)
    )
    stdout, stderr = process.communicate(input=input_text)
    return process.returncode, stdout, stderr
    stdout, stderr = process.communicate(input='\\n'.join(inputs))
    return process.returncode, stdout, stderr

@pytest.fixture
def mock_file_operations():
    """Mock file operations that might fail"""
    with patch('builtins.open') as mock_open, \
         patch('os.path.exists') as mock_exists, \
         patch('subprocess.Popen') as mock_popen:
        
        mock_process = MagicMock()
        mock_process.communicate.return_value = ('mock stdout', 'mock stderr')
        mock_process.returncode = 0
        mock_popen.return_value = mock_process
        
        yield {
            'open': mock_open,
            'exists': mock_exists,
            'popen': mock_popen
        }

def test_successful_single_host():
    """Test successful config creation with a single host"""
    inputs = [
        'http://test:11434',  # URL
        '8192',               # VRAM
        '1',                  # Priority
        'n'                   # Don't add another host
    ]
    
    returncode, stdout, stderr = run_install_script(inputs)
    print(f"STDOUT: {stdout}")
    print(f"STDERR: {stderr}")
    assert returncode == 0
    assert TEST_CONFIG_PATH.exists()
    
    # Validate config content
    config = json.loads(TEST_CONFIG_PATH.read_text())
    assert len(config['hosts']) == 1
    assert config['hosts'][0]['url'] == 'http://test:11434'
    assert config['hosts'][0]['total_vram_mb'] == 8192
    assert config['hosts'][0]['priority'] == 1

def test_successful_multiple_hosts():
    """Test successful config creation with multiple hosts"""
    inputs = [
        'http://test1:11434',  # First host
        '8192',
        '1',
        'y',                   # Add another host
        'http://test2:11434',  # Second host
        '16384',
        '2',
        'n'                    # Don't add more hosts
    ]
    
    returncode, stdout, stderr = run_install_script(inputs)
    assert returncode == 0
    assert TEST_CONFIG_PATH.exists()
    
    # Validate config content
    config = json.loads(TEST_CONFIG_PATH.read_text())
    assert len(config['hosts']) == 2
    assert config['hosts'][0]['url'] == 'http://test1:11434'
    assert config['hosts'][1]['url'] == 'http://test2:11434'
    assert config['hosts'][1]['total_vram_mb'] == 16384

def test_file_write_permission_error():
    """Test handling of file write permission errors"""
    with patch('builtins.open') as mock_open:
        mock_open.side_effect = PermissionError("Permission denied")
        
        inputs = [
            'http://test:11434',
            '8192',
            '1',
            'n'
        ]
        
        returncode, stdout, stderr = run_install_script(inputs)
        assert returncode != 0
        assert "Permission denied" in stderr

def test_config_validation_error():
    """Test handling of invalid configuration"""
    # Create an invalid config file
    TEST_CONFIG_PATH.write_text("invalid json content")
    
    inputs = [
        'http://test:11434',
        '8192',
        '1',
        'n'
    ]
    
    returncode, stdout, stderr = run_install_script(inputs)
    assert returncode != 0
    assert "not a valid JSON file" in stderr

def test_disk_full_error():
    """Test handling of disk full errors"""
    with patch('builtins.open') as mock_open:
        mock_open.side_effect = OSError("No space left on device")
        
        inputs = [
            'http://test:11434',
            '8192',
            '1',
            'n'
        ]
        
        returncode, stdout, stderr = run_install_script(inputs)
        assert returncode != 0
        assert "No space left on device" in stderr