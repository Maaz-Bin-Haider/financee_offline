FROM postgres:16@sha256:ca0bd484cb98bf4b24eb1010e73fb3fcbd6714d240fbc1a10eea5b7dbecb641d AS pgtools
RUN mkdir -p /pgtools/bin /pgtools/lib /pgtools/notices && \
    cp /usr/lib/postgresql/16/bin/pg_dump /usr/lib/postgresql/16/bin/pg_restore /pgtools/bin/ && \
    ldd /pgtools/bin/pg_dump /pgtools/bin/pg_restore | awk '/=> \/.* \(/ {print $3}' | sort -u | \
    while read lib; do cp -L "$lib" /pgtools/lib/; done && \
    cp -a /usr/share/doc /pgtools/notices/debian-doc
FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
COPY --from=pgtools /pgtools /opt/pg16
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
COPY requirements-lock.txt .
RUN pip install --no-cache-dir -r requirements-lock.txt
COPY . .
RUN SECRET_KEY=build-only-unused-key DEBUG=False DB_NAME=build DB_USER=build DB_PASSWORD=build DB_HOST=none DB_PORT=5432 python manage.py collectstatic --noinput
RUN useradd -m -u 10001 appuser && chown -R appuser:appuser /app
USER appuser
CMD ["gunicorn","financee.wsgi:application","--bind","0.0.0.0:8000","--workers","2","--threads","2","--timeout","60","--access-logfile","-"]
