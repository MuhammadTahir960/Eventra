import django_filters
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.common.constants import Roles
from apps.common.permissions import IsAdmin

from .models import User
from .serializers import (
    ActiveUserTokenObtainPairSerializer,
    DeleteAccountSerializer,
    LogoutSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    SafeTokenRefreshSerializer,
    UserSerializer,
)
from .services import (
    AccountDeletionBlockedError,
    IncorrectPasswordError,
    delete_account,
    issue_ws_ticket,
    register_user,
    request_password_reset,
    reset_password,
    verify_user_email,
)


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth-register"

    def perform_create(self, serializer):
        register_user(serializer)


class VerifyEmailView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth-verify-email"

    def get(self, request):
        token = request.query_params.get("token")
        if not token:
            return Response(
                {"detail": "Missing verification token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = verify_user_email(token)
        if result is None:
            return Response(
                {"detail": "Invalid or expired verification token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user, was_newly_verified = result
        message = (
            "Email verified successfully."
            if was_newly_verified
            else "Email already verified."
        )
        return Response(
            {"detail": message, "email": user.email},
            status=status.HTTP_200_OK,
        )


class LoginView(TokenObtainPairView):
    serializer_class = ActiveUserTokenObtainPairSerializer
    throttle_scope = "auth-login"


class LogoutView(generics.GenericAPIView):
    serializer_class = LogoutSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_205_RESET_CONTENT)


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class AccountDeletionView(generics.GenericAPIView):
    serializer_class = DeleteAccountSerializer
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "auth-delete-account"

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            delete_account(request.user, serializer.validated_data["password"])
        except IncorrectPasswordError:
            return Response(
                {"password": ["That password isn't right."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except AccountDeletionBlockedError as exc:
            return Response(
                {
                    "detail": "Your account can't be deleted yet.",
                    "reasons": exc.reasons,
                },
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordResetRequestView(generics.GenericAPIView):
    serializer_class = PasswordResetRequestSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth-password-reset"

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request_password_reset(serializer.validated_data["email"])
        return Response(
            {
                "detail": (
                    "If an account with that email exists, a password "
                    "reset link has been sent."
                )
            },
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(generics.GenericAPIView):
    serializer_class = PasswordResetConfirmSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth-password-reset"

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        success = reset_password(
            serializer.validated_data["token"],
            serializer.validated_data["new_password"],
        )
        if not success:
            return Response(
                {"detail": "Invalid or expired reset token."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"detail": "Password has been reset successfully."},
            status=status.HTTP_200_OK,
        )


class WsTicketView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "auth-ws-ticket"

    def post(self, request):
        ticket, expires_at = issue_ws_ticket(request.user)
        return Response(
            {"ticket": ticket, "expires_at": expires_at.isoformat()},
            status=status.HTTP_200_OK,
        )


class AdminUserFilterSet(django_filters.FilterSet):
    search = django_filters.CharFilter(method="filter_search", max_length=100)
    role = django_filters.ChoiceFilter(choices=Roles.choices)

    class Meta:
        model = User
        fields = ["search", "role"]

    def filter_search(self, queryset, name, value):
        return queryset.filter(email__icontains=value)


class AdminUserListView(generics.ListAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    filterset_class = AdminUserFilterSet
    queryset = User.objects.all().order_by("-created_at")


class SafeTokenRefreshView(TokenRefreshView):
    serializer_class = SafeTokenRefreshSerializer
