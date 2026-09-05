FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    shared-mime-info \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/ requirements/
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements/prod.txt

COPY . .

RUN chmod +x docker-entrypoint.sh \
    && addgroup --system app \
    && adduser --system --ingroup app --no-create-home app \
    && mkdir -p /app/staticfiles /app/mediafiles \
    && chown -R app:app /app

USER app

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz/')" || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]
