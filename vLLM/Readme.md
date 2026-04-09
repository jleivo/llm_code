# vLLM compose files

```bash
docker compose -f FILENAME up -d
```

## baseline compose file

```text
services:
  vllm:
    image: vllm/vllm-openai:latest
    container_name: vllm
    runtime: nvidia
    ports:
      - "8200:8000"
    environment:
      - NCCL_P2P_DISABLE=1
      - NCCL_IB_DISABLE=1
    volumes:
      - ~/.cache/huggingface:/root/.cache/huggingface
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    command: >
      --model cyankiwi/AWQ-4BIT
      --max-model-len 81920
      --max-num-seqs 4
      --async-scheduling
      --dtype auto
      --kv-cache-dtype fp8
      --enable-expert-parallel
      --trust-remote-code
      --tensor-parallel-size 4
      --enable-chunked-prefill
      --enable-prefix-caching
      --trust-remote-code
      --reasoning-parser nemotron_v3
      --enable-auto-tool-choice
      --tool-call-parser qwen3_xml
    restart: unless-stopped
    ipc: host
```

There are two areas that need to be changed per model:
1) The first three lines of the command
- What model, prefer cyankiwi AWQ-4bit models or AWQ models if you can afford to go higher than 4-bit
- How much context (times max num seqs). NOTE! kv-cache is at FP8 from the start. Rules of thumb for MoE models: at ~122B you can handle 81920 (80k context), at 80B 131072 (128 k) or more
- Max-num-seq is how many side by side. 4 seems plenty

2) The last three lines of the command
- Reasoning parser, is unique to each, use given playbooks 
- tool call parser, qwen3_coder and qwen3_xml are commonly used, see common guidance on what to choose. Test which one gives better results.


## Nemotron-3-super

context: 81920
max-side-by-side: 4
tensor-parallel-size: 4
reasoning-parser: nemotron_v3
tool-call-parser: qwen3_xml
finalized: yes
Personal tune up: Changed tool call parser from qwen3_coder to qwen3_xml. Qwen3_coder caused calling issues.

## Qwen3-Coder-Next

context: 131072
max-side-by-side: 8
tensor-parallel-size: 4
reasoning-parser: none
tool-call-parser: qwen3_xml
finalized: yes
Personal tune up:

## Qwen3.5-122B

context: 98304
max-side-by-side: 2
tensor-parallel-size: 4
reasoning-parser: none
tool-call-parser: qwen3_coder
finalized: no
Personal tune up: Uses max-num-batched-tokens 4096 with disable-custom-all-reduce and enforce-eager for stability. Conservative max-num-seqs due to large model size.

## Qwen3.5-27B

context: 131072
max-side-by-side: 16
tensor-parallel-size: 4
reasoning-parser: qwen3
tool-call-parser: qwen3_coder
finalized: yes
Personal tune up:

## Qwen3.5-35B

context: 131072
max-side-by-side: 16
tensor-parallel-size: 4
reasoning-parser: qwen3
tool-call-parser: qwen3_coder
finalized: yes
Personal tune up:

## Snowflake Arctic Embed-L v2.0

model-type: embedding
context: none (embedding model)
max-side-by-side: N/A
tensor-parallel-size: N/A
reasoning-parser: N/A
tool-call-parser: N/A
finalized: no
Personal tune up: low GPU memory utilization (0.3), due to sharing the GPU with TTS and STT models. Otherwise it won't boot up as too much memory is used.

