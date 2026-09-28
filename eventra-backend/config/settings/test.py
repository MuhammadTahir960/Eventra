from .dev import *  # noqa: F401,F403

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="eventra-test-media-"))
