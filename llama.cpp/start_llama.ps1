# v1.0.1
# start_llama.ps1 - Start llama.cpp servers with graceful shutdown

$ErrorActionPreference = "Stop"

$LLAMA_PATH = "C:\Users\juha.LHE\.cache\lemonade\bin\llamacpp\vulkan\llama-server.exe"
$INI_PATH = "C:\Users\juha.LHE\llama-models.ini"
$EMBED_MODEL = "C:\Users\juha.LHE\.cache\huggingface\hub\models--Casual-Autopsy--snowflake-arctic-embed-l-v2.0-gguf\snapshots\0995861dc0b106ddd5152bc753718d4e34d1e68b\snowflake-arctic-embed-l-v2.0-q4_k_m.gguf"

$embeddingProcess = $null
$chatProcess = $null

$cleanup = {
    Write-Host "`nShutting down servers..." -ForegroundColor Yellow

    if ($script:chatProcess -and !$script:chatProcess.HasExited) {
        Write-Host "Stopping Chat Router..." -ForegroundColor Yellow
        $script:chatProcess.Kill()
        $script:chatProcess.WaitForExit()
    }

    if ($script:embeddingProcess -and !$script:embeddingProcess.HasExited) {
        Write-Host "Stopping Embedding Server..." -ForegroundColor Yellow
        $script:embeddingProcess.Kill()
        $script:embeddingProcess.WaitForExit()
    }

    Write-Host "All servers stopped." -ForegroundColor Green
    exit
}

Register-EngineEvent PowerShell.Exiting -Action $cleanup | Out-Null
trap {
    Write-Host "`nInterrupt received (Ctrl+C)" -ForegroundColor Red
    & $cleanup
}

Write-Host "[1/2] Starting Embedding Server on Port 8081..." -ForegroundColor Cyan
$embeddingProcess = Start-Process -FilePath $LLAMA_PATH -ArgumentList "-m", $EMBED_MODEL, "--no-mmap", "--host", "0.0.0.0", "--port", "8081", "--embedding", "--pooling", "cls", "-c", "8192", "-ngl", "99" -NoNewWindow -PassThru

Start-Sleep -Seconds 1

Write-Host "[2/2] Starting Chat Router on Port 8080 (Swapping Enabled)..." -ForegroundColor Cyan
$chatProcess = Start-Process -FilePath $LLAMA_PATH -ArgumentList "--models-preset", $INI_PATH, "--host", "0.0.0.0", "--port", "8080", "--no-mmap", "--models-max", "1" -NoNewWindow -PassThru

Write-Host "Both servers running. Press Ctrl+C to stop." -ForegroundColor Green
Write-Host ""

try {
    while ($true) {
        if ($embeddingProcess.HasExited) {
            Write-Host "`nEmbedding Server exited unexpectedly (code: $($embeddingProcess.ExitCode))" -ForegroundColor Red
            break
        }
        if ($chatProcess.HasExited) {
            Write-Host "`nChat Router exited unexpectedly (code: $($chatProcess.ExitCode))" -ForegroundColor Red
            break
        }
        Start-Sleep -Seconds 2
    }
}
finally {
    & $cleanup
}
