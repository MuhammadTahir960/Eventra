from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "type", "status", "sent_at", "created_at")
    list_filter = ("type", "status")
    search_fields = ("id", "user__email")
    ordering = ("-created_at",)
