from celery import shared_task

from .services import complete_past_events as _complete_past_events


@shared_task(name="apps.events.tasks.complete_past_events")
def complete_past_events() -> int:
    return _complete_past_events()
