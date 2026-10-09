from celery import shared_task

from .models import User
from .services import send_password_reset_email, send_verification_email


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def send_verification_email_task(user_id: str) -> None:
    user = User.objects.filter(id=user_id).first()
    if user is not None and not user.is_email_verified:
        send_verification_email(user)


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def send_password_reset_email_task(user_id: str) -> None:
    user = User.objects.filter(id=user_id, is_active=True).first()
    if user is not None:
        send_password_reset_email(user)
