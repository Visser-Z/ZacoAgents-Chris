# One image, two targets. Nothing here knows whether it is running under docker compose on a
# laptop or on a hosting provider -- only the environment differs (D3).

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first, so editing source does not reinstall them.
COPY pyproject.toml ./
RUN pip install --upgrade pip \
 && pip install "fastapi>=0.115" "uvicorn[standard]>=0.32" "sqlalchemy>=2.0.36" \
      "psycopg[binary]>=3.2" "alembic>=1.14" "pydantic>=2.9" "pydantic-settings>=2.6" \
      "email-validator>=2.2" "jinja2>=3.1" "python-multipart>=0.0.17" "itsdangerous>=2.2" \
      "argon2-cffi>=23.1" "openpyxl>=3.1.5"

COPY alembic.ini ./
COPY migrations ./migrations
COPY zaco ./zaco
# The operator's product short codes. Without this the image runs with an empty lookup and
# silently resolves nothing -- which looks like a working system with more work to do.
COPY lookup ./lookup
# The operator's starting workbook. The live book lives on a persistent volume, which is empty
# the first time the stack comes up; this seeds it once, so a fresh clone has something to read
# the delivery note series from instead of refusing to propose a number.
COPY workbook/account-sales-book.xlsx ./seed/account-sales-book.xlsx
COPY entrypoint.sh ./
RUN chmod +x entrypoint.sh

# Runs as a non-root user, which means the volume mount must be writable by it. The compose
# file and the hosting disk are both configured accordingly.
RUN useradd --create-home --uid 10001 zaco \
 && mkdir -p /data/workbook /data/backups \
 && chown -R zaco:zaco /app /data
USER zaco

EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
# --proxy-headers so a TLS-terminating proxy is visible to the app: without it every hosted
# request looks like plain http and the session cookie would not be marked Secure.
CMD ["uvicorn", "zaco.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
