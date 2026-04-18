我现在有两个服务器，一个是GPU大模型服务器（192.168.110.241），一个是应用服务器（192.168.110.117，用户名root，密码123qazqwer）。我想在应用服务器上部署容器化部署（上面方块里面的内容）。并帮我写一个dashboard，统一管理。

大模型服务器里面的模型已经部署好了。部署命令分别是
ollama里面的向量模型：
services:
  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    ports:
      - "11434:11434"
    volumes:
      - /opt/my_ai/ollama_data:/root/.ollama
    environment:
      - OLLAMA_NUM_PARALLEL=1
      - OLLAMA_MAX_LOADED_MODELS=1
    restart: unless-stopped
qwen3.5-27b：
docker run -d \ --name vllm-qwen3.5-27b-int8-128k \ --gpus '"device=0,1"' \ --ipc=host \ --ulimit memlock=-1 \ --ulimit stack=67108864 \ --cpuset-cpus="0-27,56-83" \ -v /opt/vllm/model:/model \ -v /opt/vllm/logs:/logs \ -p 12434:12434 \ vllm/vllm-openai:latest\ /model/qwen3.5-27b-fp8 \ --host 0.0.0.0 \ --port 12434 \ --api-key qwen-241-12434 \ --tensor-parallel-size 2 \ --max-model-len 131072 \ --gpu-memory-utilization 0.92 \ --served-model-name qwen3.5-27b-int8-128k \ --max-num-seqs 4 \ --max-num-batched-tokens 12288 \ --enable-prefix-caching
qwen3.5-35b
docker run -d \ --name vllm-qwen3.5-35b-a3b-int4-256k \ --gpus '"device=2,3"' \ --ipc=host \ --ulimit memlock=-1 \ --ulimit stack=67108864 \ --cpuset-cpus="28-55,84-111" \ -v /opt/vllm/model:/model \ -v /opt/vllm/logs:/logs \ -p 13434:13434 \ vllm/vllm-openai:v0.17.0 \ /model/qwen3.5-35b-a3b \ --host 0.0.0.0 \ --port 13434 \ --api-key qwen-241-13434 \ --tensor-parallel-size 2 \ --max-model-len 262144 \ --gpu-memory-utilization 0.90 \ --served-model-name qwen3.5-35b-a3b-int4-256k \ --max-num-seqs 2 \ --max-num-batched-tokens 4096 \ --language-model-only \ --enable-prefix-caching
