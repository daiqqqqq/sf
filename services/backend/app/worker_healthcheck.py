from __future__ import annotations

import socket
import sys

from app.celery_app import celery_app

REQUIRED_TASKS = {
    "app.tasks.pipeline.ingest_document_task",
    "app.tasks.pipeline.probe_services_task",
}


def main() -> None:
    node_name = f"celery@{socket.gethostname()}"

    try:
        inspector = celery_app.control.inspect(destination=[node_name], timeout=5)
        ping = inspector.ping() or {}
        if ping.get(node_name, {}).get("ok") != "pong":
            raise RuntimeError(f"worker {node_name} did not respond to ping")

        registered = inspector.registered() or {}
        task_names = set(registered.get(node_name, []))
        missing = sorted(task for task in REQUIRED_TASKS if task not in task_names)
        if missing:
            raise RuntimeError(
                f"worker {node_name} is missing required tasks: {', '.join(missing)}"
            )
    except Exception as exc:
        print(f"[worker-healthcheck] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"[worker-healthcheck] worker healthy: {node_name}")


if __name__ == "__main__":
    main()
