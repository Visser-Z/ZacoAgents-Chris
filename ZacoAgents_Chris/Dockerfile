# One image, two targets. Nothing here knows whether it is running under docker compose on a
# laptop or on a hosting provider -- only the environment differs (D3).

# --- the frontend, built here and not on anybody's machine ---------------------------------------
# The bundle is a build artefact: it is gitignored, and .dockerignore keeps a local `npm run build`
# from being copied in. Building it in the image is what makes the two agree.
#
# Bundled, never fetched: D3 says the system has to run from `docker compose up` with no CDN, and
# a React app loaded from unpkg would break that promise while appearing to work on a connected
# laptop.
FROM node:22-alpine AS frontend

WORKDIR /build

# Manifests first, so editing a component does not reinstall the world.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# Typecheck first, so a type error fails the image rather than shipping inside it -- `vite build`
# alone strips types without checking them. The output is redirected because vite.config.ts writes
# to ../zaco/web/spa, which is outside the directory this stage owns.
RUN npm run typecheck && npx vite build --outDir /build/dist --emptyOutDir

# --- the application -----------------------------------------------------------------------------
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
      "email-validator>=2.2" "python-multipart>=0.0.17" "itsdangerous>=2.2" \
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
# The built frontend, from the stage above. Served at / by the API itself, same origin, so the
# session cookie needs no relaxing and there is no CORS or CSRF surface to add. Without this the
# image has an API and no interface at all -- there is no server-rendered fallback any more.
COPY --from=frontend /build/dist ./zaco/web/spa
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
