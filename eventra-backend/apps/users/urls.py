from django.urls import path

from .views import (
    AdminUserListView,
    AdminUserRoleUpdateView,
    LoginView,
    LogoutView,
    MeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RegisterView,
    SafeTokenRefreshView,
    VerifyEmailView,
    WsTicketView,
)

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/verify-email/", VerifyEmailView.as_view(), name="verify-email"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/refresh/", SafeTokenRefreshView.as_view(), name="token_refresh"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("auth/me/", MeView.as_view(), name="me"),
    path(
        "auth/password-reset/",
        PasswordResetRequestView.as_view(),
        name="password-reset-request",
    ),
    path(
        "auth/password-reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    path("auth/ws-ticket/", WsTicketView.as_view(), name="ws-ticket"),
    path("admin/users/", AdminUserListView.as_view(), name="admin-users-list"),
    path(
        "admin/users/<uuid:user_id>/role/",
        AdminUserRoleUpdateView.as_view(),
        name="admin-user-role",
    ),
]
