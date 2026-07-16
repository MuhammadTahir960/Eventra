FROM python:3.14-slim

WORKDIR /app

COPY requirements/ requirements/
RUN pip install --no-cache-dir -r requirements/dev.txt

COPY . .

EXPOSE 8000

CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]
