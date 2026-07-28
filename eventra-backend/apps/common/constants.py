from django.db import models


class Roles(models.TextChoices):
    ATTENDEE = "attendee", "Attendee"
    ORGANIZER = "organizer", "Organizer"
    ADMIN = "admin", "Admin"
