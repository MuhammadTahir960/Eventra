from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.contrib.auth.base_user import BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        # always goes through Django's hasher, never stored raw
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        # createsuperuser needs these two flags to grant full access —
        # role=admin alone isn't enough, since is_staff/is_superuser are what
        # Django's own admin site and permission system actually check.
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        # superuser shouldn't be gated by email verification
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("role", User.Roles.ADMIN)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    class Roles(models.TextChoices):
        ADMIN = "admin", "Admin"
        ORGANIZER = "organizer", "Organizer"
        ATTENDEE = "attendee", "Attendee"

    email = models.EmailField(unique=True, db_index=True)
    first_name = models.CharField(max_length=30)
    last_name = models.CharField(max_length=30)
    role = models.CharField(
        max_length=20, choices=Roles.choices, default=Roles.ATTENDEE
    )

    # False until GET /auth/verify-email/ flips it
    is_active = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)

    # not part of RBAC (role does that) — this exists only so Django's admin
    # site and createsuperuser work correctly; PermissionsMixin alone doesn't provide it
    is_staff = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []  # email + password are already required by AbstractBaseUser

    def __str__(self):
        return f"{self.first_name} {self.last_name}"
