#Requires -RunAsAdministrator
param(
    [string]$InstallDir = "C:\opt\gpu_monitor",
    [string]$NssmPath = "nssm.exe"
)

Write-Host "Installing gpu_monitor to $InstallDir..."

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item "$PSScriptRoot\..\..\gpu_monitor\gpu_monitor.py" $InstallDir
Copy-Item "$PSScriptRoot\..\..\gpu_monitor\requirements.txt" $InstallDir

# Create venv and install deps
python -m venv "$InstallDir\.venv"
& "$InstallDir\.venv\Scripts\pip.exe" install --upgrade pip -q
& "$InstallDir\.venv\Scripts\pip.exe" install -r "$InstallDir\requirements.txt" -q

# Register Windows service via NSSM
& $NssmPath install gpu_monitor "$InstallDir\.venv\Scripts\python.exe"
& $NssmPath set gpu_monitor AppParameters "$InstallDir\gpu_monitor.py"
& $NssmPath set gpu_monitor AppDirectory $InstallDir
& $NssmPath set gpu_monitor Start SERVICE_AUTO_START
& $NssmPath start gpu_monitor

Write-Host "gpu_monitor service installed and started."
