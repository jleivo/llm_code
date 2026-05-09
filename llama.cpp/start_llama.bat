@echo off
SET LLAMA_PATH=C:\Users\juha.LHE\.cache\lemonade\bin\llamacpp\vulkan\llama-server.exe
SET INI_PATH=C:\Users\juha.LHE\llama-models.ini
SET EMBED_MODEL=C:\Users\juha.LHE\.cache\huggingface\hub\models--Casual-Autopsy--snowflake-arctic-embed-l-v2.0-gguf\snapshots\0995861dc0b106ddd5152bc753718d4e34d1e68b\snowflake-arctic-embed-l-v2.0-q4_k_m.gguf

echo [1/2] Starting Embedding Server on Port 8081...
start "Llama-Embedding" /min %LLAMA_PATH% -m %EMBED_MODEL% --no-mmap --host 0.0.0.0 --port 8081 --embedding --pooling cls -c 8192 -ngl 99

echo [2/2] Starting Chat Router on Port 8080 (Swapping Enabled)...
%LLAMA_PATH% --models-preset %INI_PATH% --host 0.0.0.0 --port 8080 --no-mmap --models-max 1