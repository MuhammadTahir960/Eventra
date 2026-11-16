from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import AuthenticationFailed, TokenError
from rest_framework_simplejwt.serializers import (
    TokenObtainPairSerializer,
    TokenRefreshSerializer,
)
from rest_framework_simplejwt.tokens import RefreshToken

from apps.common.constants import Roles
from apps.common.serializers import RejectUnknownFieldsMixin

from .models import User


class RegisterSerializer(RejectUnknownFieldsMixin, serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, max_length=128)
    captcha_token = serializers.CharField(
        write_only=True, required=False, allow_blank=True, max_length=2048
    )
    gender = serializers.ChoiceField(
        choices=User.Gender.choices,
        required=True,
        allow_blank=False,
        allow_null=False,
    )
    role = serializers.ChoiceField(
        choices=[
            (Roles.ATTENDEE, Roles.ATTENDEE.label),
            (Roles.ORGANIZER, Roles.ORGANIZER.label),
        ],
        required=True,
    )

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "password",
            "first_name",
            "last_name",
            "gender",
            "role",
            "captcha_token",
        ]
        read_only_fields = ["id"]
        extra_kwargs = {"email": {"validators": []}}

    def validate_email(self, value):
        return value.strip().lower()

    def validate(self, attrs):
        temp_user = User(
            email=attrs.get("email"),
            first_name=attrs.get("first_name"),
            last_name=attrs.get("last_name"),
        )
        validate_password(attrs["password"], user=temp_user)
        return attrs

    def create(self, validated_data):
        validated_data.pop("captcha_token", None)
        return User.objects.create_user(**validated_data)


class ActiveUserTokenObtainPairSerializer(
    RejectUnknownFieldsMixin, TokenObtainPairSerializer
):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        return token

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password"].max_length = 128

    def validate(self, attrs):
        email = attrs.get(self.username_field, "").strip()
        password = attrs.get("password")

        user = User.objects.filter(email__iexact=email).first()

        if user is None:
            User().set_password(password)
            raise AuthenticationFailed(
                "No active account found with the given credentials"
            )

        if not user.check_password(password):
            raise AuthenticationFailed(
                "No active account found with the given credentials"
            )

        if not user.is_active:
            raise AuthenticationFailed(
                "Account is not active. Please verify your email."
            )

        self.user = user
        refresh = self.get_token(self.user)
        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "role": user.role,
        }


class LogoutSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    refresh = serializers.CharField()

    def save(self, **kwargs):
        try:
            token = RefreshToken(self.validated_data["refresh"])
        except TokenError as exc:
            raise serializers.ValidationError({"refresh": str(exc)}) from exc

        request = self.context.get("request")
        if request is not None and str(token.get("user_id")) != str(request.user.id):
            raise serializers.ValidationError(
                {"refresh": "This token does not belong to the current user."}
            )

        try:
            token.blacklist()
        except TokenError as exc:
            raise serializers.ValidationError({"refresh": str(exc)}) from exc


class DeleteAccountSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    password = serializers.CharField(write_only=True, max_length=128)


class PasswordResetRequestSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, max_length=128)

    def validate_new_password(self, value):
        validate_password(value)
        return value


_AVATAR_ASSET_KEYS = {
    User.Gender.MALE: "avatar-male",
    User.Gender.FEMALE: "avatar-female",
    User.Gender.OTHER: "avatar-other",
}


class UserSerializer(RejectUnknownFieldsMixin, serializers.ModelSerializer):
    avatar = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "role",
            "first_name",
            "last_name",
            "gender",
            "avatar",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "email", "role", "is_active", "created_at"]
        extra_kwargs = {"gender": {"allow_blank": False}}

    def get_avatar(self, obj) -> str | None:
        return _AVATAR_ASSET_KEYS.get(obj.gender)


class SafeTokenRefreshSerializer(RejectUnknownFieldsMixin, TokenRefreshSerializer):
    def validate(self, attrs):
        try:
            return super().validate(attrs)
        except User.DoesNotExist as exc:
            raise TokenError("Token is invalid.") from exc
