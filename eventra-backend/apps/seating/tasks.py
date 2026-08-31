from celery import shared_task

from .services import release_expired_holds as _release_expired_holds


@shared_task
def release_expired_holds():
    _release_expired_holds()
