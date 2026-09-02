# Running it

[README.md](../README.md) is the exercise brief as given and is left untouched apart from a
pointer to these documents. This is how to run what was built. Design decisions are in
[DECISIONS.md](DECISIONS.md); what was found in the data is in [NOTES.md](../NOTES.md).

## Locally, in one command

Local is the primary target and must work before hosting does ([DECISIONS.md](DECISIONS.md) D3).

```
cd ZacoAgents_Chris
docker compose up --build
```

Then open <http://localhost:8000> and sign in as `admin@example.com` / `change-me-please`.
Those come from `ADMIN_EMAIL` and `ADMIN_PASSWORD`; the account is seeded **only** on an empty
database and an existing password is never reset.

The compose stack is:

| Service | What it is |
|---|---|
| `db` | Postgres 16, on `127.0.0.1:5432` so the VS Code PostgreSQL extension can inspect the durable record |
| `app` | the application, on `:8000`; runs `alembic upgrade head` before starting |
| `backup-sidecar` | a coarse safety net, for parity with the compose design (see below) |

Volumes `zaco_workbook` and `zaco_backups` hold the operator's live workbook and its snapshots.
They survive `docker compose down`; `docker compose down -v` destroys them.

### About the sidecar

It is parity, not the guarantee. The snapshot that actually protects the workbook is taken
**inside the append transaction** by the application: snapshot, append, commit, or roll all of
it back. A container watching a volume can copy a file mid-write, and on a hosting provider a
disk mounts to exactly one service, so a sidecar cannot share it at all. See [DECISIONS.md](DECISIONS.md) D4.

## Without Docker

```
cd ZacoAgents_Chris
python -m venv .venv && .venv\Scripts\activate      # PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env                              # then edit it
docker compose up -d db                             # or point DATABASE_URL at your own Postgres
alembic upgrade head
uvicorn zaco.main:app --reload
```

## Tests

```
pytest                    # the whole suite
pytest -m "not db"        # only what needs no database
ruff check . && mypy zaco
```

Tests that need Postgres are marked `db` and **skip with a reason** when it is unreachable, so
the suite still runs on a machine that has not started the stack. They use a separate
`zaco_test` database, created by `docker/initdb/`, because they truncate tables between cases --
running the suite must never destroy a staged round. The schema under test is built
by running the real migrations, not `create_all`, so a migration that has drifted from the
models fails here rather than on a deploy.

In VS Code, the Test Explorer is already configured, and `.vscode/launch.json` has debug targets
for the app and for pytest. `.vscode/extensions.json` lists the extensions to install; VS Code
offers them when the folder is opened.

## Hosting

Deliberately not exercised until the local stack works end to end, so hosting can never be
blamed for a bug that is really in the application (D3). `render.yaml` describes a web service,
a managed Postgres and a mounted disk. **No application code changes between the two targets** —
only these environment variables:

| Variable | Local | Hosted |
|---|---|---|
| `DATABASE_URL` | compose `db` service | managed Postgres (`postgres://` URLs are normalised automatically) |
| `WORKBOOK_DIR` / `BACKUP_DIR` | named volumes | paths on the mounted disk |
| `SECRET_KEY` | shipped default, and the app says so | generated; must be real |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | from `.env` | set in the environment group |
| `ALLOWED_EMAIL_DOMAINS` | usually empty | optional; gates who may be **invited**, never an identity |

## Accounts

There is no self-registration. An administrator invites a specific email address and grants
permissions individually — `ingest`, `resolve`, `append`, `record_terms`, `view_reports`,
`admin`. `admin` does not imply the others.

That is not ceremony: every queue answer, DN approval, duplicate decision and append is stamped
with a person, and a duplicate-conflict record reading "chose this export because…" is worth
nothing if a shared account made the choice. See [DECISIONS.md](DECISIONS.md) D14.

No mail is sent. Copy the invitation link from the Accounts page and pass it on.

## Where things are

```
zaco/config.py         every environment-dependent value in the system, and nothing else
zaco/api/              /api/* JSON endpoints; the OpenAPI schema is at /docs
zaco/web/              the built-in interface: a thin client over those same endpoints
zaco/db/               SQLAlchemy models; money is NUMERIC(14,2) and Decimal, never float
migrations/            Alembic
tests/                 fixtures are the real files in data/, never tidied ones
```

The interface calls only documented `/api/*` endpoints, so a React or Flutter frontend can be
added later with nothing but CORS and the schema (D1).
