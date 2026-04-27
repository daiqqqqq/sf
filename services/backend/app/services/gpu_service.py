from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.schemas.api import GpuDeviceRead, GpuOverviewResponse, GpuServiceStatusRead


class PrometheusQueryError(RuntimeError):
    """Raised when a Prometheus instant query fails."""


@dataclass
class GpuSample:
    key: str
    label: str
    uuid: str | None = None
    model_name: str | None = None
    utilization_percent: float | None = None
    memory_used_mb: float | None = None
    memory_total_mb: float | None = None
    memory_utilization_percent: float | None = None
    temperature_celsius: float | None = None
    power_watts: float | None = None
    sample_time: datetime | None = None
    status: str = "healthy"


class GpuMonitorService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def build_overview(self) -> GpuOverviewResponse:
        warnings: list[str] = []
        devices: list[GpuDeviceRead] = []

        try:
            samples, exporter_status = await self._collect_gpu_samples()
            devices = [self._to_device(item) for item in samples]
            prometheus_status = "healthy"
        except PrometheusQueryError as exc:
            warnings.append(str(exc))
            devices = []
            exporter_status = "unknown"
            prometheus_status = "degraded"

        model_services = await self._probe_model_services()
        node_status = self._determine_node_status(exporter_status, model_services)

        total_memory_mb = sum(item.memory_total_mb or 0.0 for item in devices)
        used_memory_mb = sum(item.memory_used_mb or 0.0 for item in devices)
        utilization_values = [item.utilization_percent for item in devices if item.utilization_percent is not None]
        temperature_values = [item.temperature_celsius for item in devices if item.temperature_celsius is not None]
        power_values = [item.power_watts for item in devices if item.power_watts is not None]
        sample_times = [item.sample_time for item in devices if item.sample_time is not None]

        sampled_at = max(sample_times) if sample_times else None
        average_utilization_percent = (
            round(sum(utilization_values) / len(utilization_values), 1) if utilization_values else None
        )
        max_temperature_celsius = max(temperature_values) if temperature_values else None
        total_power_watts = round(sum(power_values), 1) if power_values else None

        if not devices and exporter_status == "healthy":
            warnings.append("GPU exporter is reachable, but no device metrics were returned.")
        if exporter_status != "healthy" and not warnings:
            warnings.append("GPU exporter status is degraded.")

        return GpuOverviewResponse(
            node_host=self.settings.gpu_node_host,
            node_status=node_status,
            exporter_status=exporter_status,
            prometheus_status=prometheus_status,
            sampled_at=sampled_at,
            gpu_count=len(devices),
            total_memory_mb=round(total_memory_mb, 1),
            used_memory_mb=round(used_memory_mb, 1),
            average_utilization_percent=average_utilization_percent,
            max_temperature_celsius=max_temperature_celsius,
            total_power_watts=total_power_watts,
            grafana_url=self.settings.grafana_gpu_dashboard_url,
            warnings=warnings,
            devices=devices,
            model_services=model_services,
        )

    async def _collect_gpu_samples(self) -> tuple[list[GpuSample], str]:
        exporter_up = await self._query_instant(
            f'up{{job="{self.settings.gpu_exporter_job_name}",instance="{self.settings.gpu_exporter_instance}"}}'
        )
        exporter_status = self._status_from_up_result(exporter_up)

        queries = {
            "utilization_percent": f'DCGM_FI_DEV_GPU_UTIL{{instance="{self.settings.gpu_exporter_instance}"}}',
            "memory_total_mb": f'DCGM_FI_DEV_FB_TOTAL{{instance="{self.settings.gpu_exporter_instance}"}}',
            "memory_used_mb": f'DCGM_FI_DEV_FB_USED{{instance="{self.settings.gpu_exporter_instance}"}}',
            "temperature_celsius": f'DCGM_FI_DEV_GPU_TEMP{{instance="{self.settings.gpu_exporter_instance}"}}',
            "power_watts": f'DCGM_FI_DEV_POWER_USAGE{{instance="{self.settings.gpu_exporter_instance}"}}',
        }

        samples_by_key: dict[str, GpuSample] = {}
        for field_name, expr in queries.items():
            results = await self._query_instant(expr)
            self._merge_metric_results(samples_by_key, field_name, results)

        for sample in samples_by_key.values():
            if sample.memory_total_mb and sample.memory_used_mb is not None:
                sample.memory_utilization_percent = round(sample.memory_used_mb / sample.memory_total_mb * 100, 1)

        ordered = sorted(
            samples_by_key.values(),
            key=lambda item: (
                self._numeric_sort_key(item.key),
                item.uuid or "",
                item.label,
            ),
        )
        return ordered, exporter_status

    async def _query_instant(self, expr: str) -> list[dict[str, Any]]:
        url = f"{self.settings.prometheus_url.rstrip('/')}/api/v1/query"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params={"query": expr})
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:  # pragma: no cover - network failure path
            raise PrometheusQueryError(f"Prometheus query failed for `{expr}`: {exc}") from exc

        if payload.get("status") != "success":
            error_text = payload.get("error", "unknown prometheus error")
            raise PrometheusQueryError(f"Prometheus query failed for `{expr}`: {error_text}")
        data = payload.get("data", {})
        return data.get("result", [])

    async def _probe_model_services(self) -> list[GpuServiceStatusRead]:
        services = [
            ("ollama", f"{self.settings.ollama_base_url.rstrip('/')}/api/tags", {}),
            (
                "qwen27",
                f"{self.settings.vllm_qwen27_base_url.rstrip('/')}/models",
                {"Authorization": f"Bearer {self.settings.vllm_qwen27_api_key}"},
            ),
            (
                "qwen35",
                f"{self.settings.vllm_qwen35_base_url.rstrip('/')}/models",
                {"Authorization": f"Bearer {self.settings.vllm_qwen35_api_key}"},
            ),
        ]

        items: list[GpuServiceStatusRead] = []
        for name, url, headers in services:
            started = perf_counter()
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(url, headers=headers)
                    response.raise_for_status()
                items.append(
                    GpuServiceStatusRead(
                        name=name,
                        base_url=url,
                        status="healthy",
                        response_ms=int((perf_counter() - started) * 1000),
                        detail="reachable",
                    )
                )
            except Exception as exc:
                items.append(
                    GpuServiceStatusRead(
                        name=name,
                        base_url=url,
                        status="unhealthy",
                        response_ms=int((perf_counter() - started) * 1000),
                        detail=str(exc),
                    )
                )
        return items

    def _merge_metric_results(
        self,
        samples_by_key: dict[str, GpuSample],
        field_name: str,
        results: list[dict[str, Any]],
    ) -> None:
        for item in results:
            metric = item.get("metric", {})
            key = self._series_key(metric)
            if key == "":
                continue

            sample = samples_by_key.get(key)
            if sample is None:
                sample = GpuSample(
                    key=key,
                    label=self._device_label(metric),
                    uuid=metric.get("UUID"),
                    model_name=metric.get("modelName") or metric.get("device"),
                )
                samples_by_key[key] = sample

            value, sample_time = self._parse_value(item.get("value"))
            if sample_time is not None and (sample.sample_time is None or sample_time > sample.sample_time):
                sample.sample_time = sample_time

            if field_name == "memory_total_mb":
                value = self._normalize_memory_mb(value)
            elif field_name == "memory_used_mb":
                value = self._normalize_memory_mb(value)
            elif field_name == "power_watts":
                value = round(value, 1)
            elif field_name == "temperature_celsius":
                value = round(value, 1)
            elif field_name == "utilization_percent":
                value = round(value, 1)

            setattr(sample, field_name, value)

    @staticmethod
    def _status_from_up_result(results: list[dict[str, Any]]) -> str:
        if not results:
            return "unhealthy"
        value, _ = GpuMonitorService._parse_value(results[0].get("value"))
        return "healthy" if value >= 1 else "unhealthy"

    @staticmethod
    def _parse_value(raw_value: Any) -> tuple[float, datetime | None]:
        if not isinstance(raw_value, list) or len(raw_value) != 2:
            return 0.0, None
        timestamp = raw_value[0]
        value = raw_value[1]
        try:
            parsed_value = float(value)
        except (TypeError, ValueError):
            parsed_value = 0.0
        sample_time = None
        try:
            sample_time = datetime.fromtimestamp(float(timestamp), tz=UTC)
        except (TypeError, ValueError, OSError):
            sample_time = None
        return parsed_value, sample_time

    @staticmethod
    def _normalize_memory_mb(value: float) -> float:
        if value > 1024 * 1024:
            return round(value / (1024 * 1024), 1)
        return round(value, 1)

    @staticmethod
    def _series_key(metric: dict[str, str]) -> str:
        for candidate in ("gpu", "minor_number", "UUID", "device"):
            if metric.get(candidate):
                return str(metric[candidate])
        return ""

    @staticmethod
    def _device_label(metric: dict[str, str]) -> str:
        gpu = metric.get("gpu") or metric.get("minor_number")
        if gpu:
            return f"GPU {gpu}"
        uuid = metric.get("UUID")
        if uuid:
            return f"GPU {uuid[-6:]}"
        device = metric.get("device")
        if device:
            return str(device)
        return "GPU"

    @staticmethod
    def _numeric_sort_key(value: str) -> tuple[int, str]:
        try:
            return int(value), value
        except (TypeError, ValueError):
            return 10_000, value

    @staticmethod
    def _determine_node_status(exporter_status: str, model_services: list[GpuServiceStatusRead]) -> str:
        has_healthy_model = any(item.status == "healthy" for item in model_services)
        has_unhealthy_model = any(item.status != "healthy" for item in model_services)

        if exporter_status == "healthy" and not has_unhealthy_model:
            return "healthy"
        if exporter_status == "healthy" and has_unhealthy_model:
            return "degraded"
        if has_healthy_model:
            return "degraded"
        return "unreachable"

    @staticmethod
    def _to_device(sample: GpuSample) -> GpuDeviceRead:
        return GpuDeviceRead(
            id=sample.key,
            label=sample.label,
            uuid=sample.uuid,
            model_name=sample.model_name,
            status=sample.status,
            utilization_percent=sample.utilization_percent,
            memory_used_mb=sample.memory_used_mb,
            memory_total_mb=sample.memory_total_mb,
            memory_utilization_percent=sample.memory_utilization_percent,
            temperature_celsius=sample.temperature_celsius,
            power_watts=sample.power_watts,
            sample_time=sample.sample_time,
        )
