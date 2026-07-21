from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from .serializers import RegisterSerializer
from .services import register_user, verify_user_email


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def perform_create(self, serializer):
        register_user(serializer)


class VerifyEmailView(APIView):
    permission_classes = [permissions.AllowAny]

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
