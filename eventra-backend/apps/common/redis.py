from django_redis import get_redis_connection


def get_redis_client():
    return get_redis_connection("default")
