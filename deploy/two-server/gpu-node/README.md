# GPU Node Monitoring

This directory documents the external GPU monitoring dependency for the dual-server RAG platform.

## Goal

Expose NVIDIA GPU metrics from the GPU model server `192.168.110.241` so that:

- Prometheus on `192.168.110.117` can scrape GPU load, memory, temperature, and power
- Grafana can render the detailed GPU dashboard
- The platform dashboard can aggregate a read-only GPU overview page

## Recommended exporter

Use NVIDIA DCGM Exporter on the GPU node and expose it on `9400/tcp`.

Prerequisites on `192.168.110.241`:

- NVIDIA driver is installed and `nvidia-smi` works
- Docker is installed
- NVIDIA Container Toolkit is installed so `--gpus all` works

## Deployment

Run the exporter on the GPU node:

```bash
docker run -d \
  --name dcgm-exporter \
  --restart unless-stopped \
  --gpus all \
  --cap-add SYS_ADMIN \
  -p 9400:9400 \
  nvcr.io/nvidia/k8s/dcgm-exporter:3.3.9-3.6.1-ubuntu22.04
```

## Validation

On `192.168.110.241`:

```bash
curl http://127.0.0.1:9400/metrics | grep DCGM_FI_DEV_GPU_UTIL | head
```

On `192.168.110.117`:

```bash
curl http://192.168.110.241:9400/metrics | grep DCGM_FI_DEV_GPU_UTIL | head
```

## Prometheus integration

The app node Prometheus configuration scrapes:

- `192.168.110.241:9400`
- job name: `gpu-exporter`

After deployment, verify in Prometheus that the target is `UP`.

## Grafana integration

The repository provisions a GPU dashboard with UID:

- `rag-platform-gpu`

Grafana URL pattern:

```text
http://192.168.110.117:3000/d/rag-platform-gpu
```

## Troubleshooting

If the target is down:

- confirm `docker ps` shows `dcgm-exporter`
- confirm `nvidia-smi` works on the GPU node
- confirm port `9400` is reachable from `192.168.110.117`
- confirm Prometheus on the app node has been reloaded or restarted after config changes
