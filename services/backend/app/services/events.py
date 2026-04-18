from __future__ import annotations

import json
import logging
from typing import Any

from kafka import KafkaProducer

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class EventPublisher:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._producer: KafkaProducer | None = None

    def _get_producer(self) -> KafkaProducer | None:
        if self._producer is not None:
            return self._producer
        try:
            self._producer = KafkaProducer(
                bootstrap_servers=self.settings.kafka_bootstrap_servers,
                value_serializer=lambda value: json.dumps(value, ensure_ascii=False).encode("utf-8"),
            )
        except Exception as exc:
            logger.warning("Kafka unavailable, falling back to logs only: %s", exc)
            self._producer = None
        return self._producer

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        producer = self._get_producer()
        if producer is None:
            logger.info("EVENT[%s] %s", topic, payload)
            return
        try:
            producer.send(topic, payload)
            producer.flush(timeout=2)
        except Exception as exc:
            logger.warning("Kafka publish failed for %s: %s", topic, exc)

