import time

from apps.common.redis import get_redis_client


def is_rate_limited(*, key: str, limit: int, window_seconds: int) -> bool:
    client = get_redis_client()

    bucket = int(time.time() // window_seconds)
    redis_key = f"{key}:{bucket}"

    count = client.incr(redis_key)
    if count == 1:
        client.expire(redis_key, window_seconds)

    return count > limit
