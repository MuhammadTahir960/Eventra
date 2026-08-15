from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import (
    ActiveUserTokenObtainPairSerializer,
    LogoutSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UserSerializer,
)
from .services import (
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
