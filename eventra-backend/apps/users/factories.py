import factory
from factory.django import DjangoModelFactory
from .models import User


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    # Sequence guarantees a unique email on every call within a test run —
    # n increments (0, 1, 2...) each time the factory builds an instance.
    # Faker's random email generation *could* collide eventually; a sequence
    # can't, which matters since `email` has a UNIQUE constraint at the DB
    # level (per the migration) — a collision would fail the test with a
    # confusing IntegrityError instead of a clear assertion failure.
    email = factory.Sequence(lambda n: f"user{n}@example.com")

    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")

    # Plain field assignment, not Faker — tests need deterministic, known
    # values here (e.g. `UserFactory(role=User.Roles.ORGANIZER)` in a
    # permission test needs to know exactly what role it's asserting against).
    role = User.Roles.ATTENDEE

    # Deliberately True here, even though real registration defaults to
    # False. Most tests are checking something else entirely (permissions,
    # /auth/me/, ownership) and shouldn't all have to fight an "unverified user"
    # condition just to set up their fixture. Override explicitly per-test when
    # you actually need the unverified case: UserFactory(is_active=False).
    is_active = True

    # Writing `password = "something"` as a plain field would set the raw string
    # directly onto the model attribute — bypassing Django's hasher entirely.
    # That means the value stored wouldn't be a valid password hash at all, so
    # any test trying to actually log in as this user would fail, or worse,
    # you'd have an unhashed password sitting in a test DB row without realizing it.
    #
    # PostGenerationMethodCall runs *after* the instance is created, calling
    # user.set_password("testpass123") on it — the exact same method registration
    # flow (UserManager.create_user) uses. This routes test users through the
    # identical hashing path as production users.
    password = factory.PostGenerationMethodCall("set_password", "testpass123")
