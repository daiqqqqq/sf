from __future__ import annotations

import subprocess
from typing import Any

from fastapi import HTTPException

from app.core.config import get_settings

try:
    import docker
except Exception:  # pragma: no cover - optional dependency behavior
    docker = None  # type: ignore[assignment]


class OpsService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.allowed = set(self.settings.allowed_service_names)

    def list_containers(self) -> list[dict[str, Any]]:
        if docker is None:
            return [{"name": name, "status": "unsupported", "detail": {"reason": "docker sdk unavailable"}} for name in self.allowed]
        client = docker.from_env()
        containers = []
        for name in sorted(self.allowed):
            try:
                container = self._get_container(client, name)
                containers.append(
                    {
                        "name": name,
                        "status": container.status,
                        "image": container.image.tags[0] if container.image.tags else None,
                        "started_at": container.attrs["State"].get("StartedAt"),
                        "detail": container.attrs["State"],
                    }
                )
            except Exception as exc:
                containers.append({"name": name, "status": "missing", "detail": {"error": str(exc)}})
        return containers

    def get_logs(self, service_name: str, tail: int = 200) -> str:
        self._ensure_allowed(service_name)
        if docker is None:
            raise HTTPException(status_code=503, detail="docker sdk unavailable")
        client = docker.from_env()
        container = self._get_container(client, service_name)
        return container.logs(tail=tail).decode("utf-8", errors="ignore")

    def perform_action(self, service_name: str, action: str) -> dict[str, Any]:
        self._ensure_allowed(service_name)
        action = action.lower()
        if action == "recreate":
            return self._recreate(service_name)
        if docker is None:
            raise HTTPException(status_code=503, detail="docker sdk unavailable")

        client = docker.from_env()
        container = self._get_container(client, service_name)
        if action == "restart":
            container.restart()
        elif action == "stop":
            container.stop()
        elif action == "start":
            container.start()
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported action: {action}")
        return {"message": f"{action} executed", "service": service_name}

    def _recreate(self, service_name: str) -> dict[str, Any]:
        compose_file = self.settings.docker_compose_file
        command = ["docker", "compose", "-f", compose_file, "up", "-d", "--no-deps", "--force-recreate", service_name]
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        if completed.returncode != 0:
            raise HTTPException(status_code=500, detail=completed.stderr or completed.stdout)
        return {"message": "recreate executed", "service": service_name, "output": completed.stdout.strip()}

    def _ensure_allowed(self, service_name: str) -> None:
        if service_name not in self.allowed:
            raise HTTPException(status_code=403, detail=f"Service {service_name} is not in the whitelist")

    @staticmethod
    def _get_container(client, service_name: str):
        try:
            return client.containers.get(service_name)
        except Exception:
            matches = client.containers.list(all=True, filters={"label": f"com.docker.compose.service={service_name}"})
            if matches:
                return matches[0]
            raise
