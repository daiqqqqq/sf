"""Task package.

Import task modules explicitly so Celery workers register shared tasks
consistently in both app runtime and worker runtime.
"""

from app.tasks import pipeline  # noqa: F401
