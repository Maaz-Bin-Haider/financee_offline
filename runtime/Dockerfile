FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
COPY requirements-lock.txt .
RUN pip install --no-cache-dir -r requirements-lock.txt
COPY . .
RUN SECRET_KEY=build-only-unused-key DEBUG=False DB_NAME=build DB_USER=build DB_PASSWORD=build DB_HOST=none DB_PORT=5432 python manage.py collectstatic --noinput
RUN useradd -u 10001 appuser && chown -R appuser:appuser /app
USER appuser
CMD ["gunicorn","financee.wsgi:application","--bind","0.0.0.0:8000","--workers","2","--threads","2","--timeout","60","--access-logfile","-"]
