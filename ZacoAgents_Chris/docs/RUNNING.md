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

On a **fresh** volume the app copies `workbook/account-sales-book.xlsx` into it once, so the
delivery note series has somewhere to come from on the very first round. It never overwrites a
book that is already there: that file is what the business settles money against, and clobbering
it on a restart would be the worst thing this system could do.

### After you change the code

```
docker compose up -d --build app
```

`docker compose restart app` is **not** enough, and the way it fails is quiet. The image copies
the source in at build time rather than mounting the working tree, so a restarted container comes
back running whatever was baked into the image it already has. Nothing errors. The old code
serves happily, and a brand new route simply 404s as though it had never been registered -- which
reads exactly like a mistake in the code you just wrote.

That trade is deliberate: the image is the same one hosting runs, so what is tested locally is
what ships (D3). The cost is this one command, and knowing that a change which seems not to have
taken usually has, into a file nothing is running.

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
npm --prefix frontend ci && npm --prefix frontend run build
uvicorn zaco.main:app --reload
```

The `npm` line is not optional here. The interface is a built bundle, and there is no
server-rendered fallback behind it any more -- without it uvicorn serves a working API and a 404
at the root, and says so in the log rather than leaving you to guess.

### Working on the interface

```
npm --prefix frontend run dev        # :5173, proxying /api to :8000
```

Sign in at <http://localhost:5173>. `localhost:5173` and `localhost:8000` are the **same site** --
SameSite ignores the port -- so the session cookie is sent unchanged and nothing on the server has
to be relaxed to work locally.

After changing an endpoint's shape, regenerate the types with the API running:

```
npm --prefix frontend run types      # openapi.json -> src/api/schema.d.ts
```

That file is generated and committed, and nothing regenerates it automatically. It is committed so
a clone typechecks without a running server; it is not automatic because a silent regeneration
turns a breaking API change into a frontend that compiles against the break.

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

`.github/workflows/ci.yml` runs the same four commands on every push and pull request, with a
Postgres service and `DATABASE_URL` pointed at `zaco_test`. It does **not** run `npm run build`,
so the handful of tests marked `needs_build` -- the ones that check the SPA mount and that a reset
link reaches a page -- skip there and are only exercised locally.

In VS Code, the Test Explorer is already configured, and `.vscode/launch.json` has debug targets
for the app and for pytest. `.vscode/extensions.json` lists the extensions to install; VS Code
offers them when the folder is opened.

## Hosting

Deliberately not exercised until the local stack worked end to end, so hosting could never be
blamed for a bug that is really in the application (D3). `render.yaml` describes a web service, a
managed Postgres and a mounted disk.

**No application code changes between the two targets** -- only these environment variables:

| Variable | Local | Hosted |
|---|---|---|
| `DATABASE_URL` | compose `db` service | managed Postgres (`postgres://` URLs are normalised automatically) |
| `WORKBOOK_DIR` / `BACKUP_DIR` | named volumes | paths on the mounted disk |
| `SECRET_KEY` | shipped default, and the app says so | generated; must be real |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | from `.env` | set in the environment group |
| `ALLOWED_EMAIL_DOMAINS` | usually empty | optional; gates who may be **invited**, never an identity |

### The application is not at the repository root

This is the thing that will fail first, and it fails before the build starts, so there is no log
to read. The repository root holds only `ZacoAgents_Chris/` and `.github/`. Render resolves
`dockerfilePath` and `dockerContext` **from the repository root, regardless of `rootDir`**, so the
obvious `./Dockerfile` finds nothing. `render.yaml` names the subdirectory:

```yaml
rootDir: ZacoAgents_Chris                        # only decides what triggers a build
dockerfilePath: ./ZacoAgents_Chris/Dockerfile    # from the repo root
dockerContext: ./ZacoAgents_Chris                # from the repo root
```

`dockerContext` also decides where `.dockerignore` is read from and what the Dockerfile's `COPY`
lines are relative to -- which is why they say `zaco` and not `ZacoAgents_Chris/zaco`.

Render looks for a blueprint at the repository root by default and this one is not there. Point it
at `ZacoAgents_Chris/render.yaml` when creating the Blueprint, or move the file to the root; the
paths inside are written from the root either way, so they survive the move.

### Before the first deploy

1. **Set `ADMIN_EMAIL` and `ADMIN_PASSWORD`** in the dashboard. They are `sync: false`, so the
   blueprint does not carry them. The first account is seeded **only on an empty database** and an
   existing password is never reset, so a value left wrong is the one you are stuck with -- see
   *Forgotten passwords* below for the way out, which needs a shell on the server.
2. **Leave `SECRET_KEY` to `generateValue`.** The shipped default is a known string; the app logs
   a warning when it is still in use.
3. Migrations run from `entrypoint.sh` on every boot, in both targets, so there is never a schema
   version only one environment has seen.
4. The disk is empty on the first deploy, so the app copies the seed workbook onto it once. It
   never overwrites a book already there.

### What is not uploaded

`.dockerignore` sits at `ZacoAgents_Chris/` -- the context root -- and keeps the build context at
roughly 1.5 MB out of the 339 MB on disk. Four groups, for four different reasons:

| Excluded | Why |
|---|---|
| `.venv/`, `frontend/node_modules/`, `__pycache__/`, `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`, `*.egg-info` | 335 MB of local tooling. Dependencies are installed inside the image. |
| `.env`, `.env.*` | A **local** file. Hosted configuration comes from the environment (D3), and one baked into an image would silently win over it. |
| `zaco/web/spa/`, `frontend/dist/`, `*.tsbuildinfo` | Build artefacts that must be made **by the `frontend` stage**, not copied from a laptop. Shipping a local build is how the image and the repository stop agreeing. |
| `tests/`, `PersonalTest/`, `data/`, `docs/`, `*.md`, `docker/`, `docker-compose.yml`, `render.yaml`, `workbook/template.xlsx` | Not part of the running application; none of it is `COPY`d. Excluded so editing a document does not invalidate the build cache. |

`data/` is the supplied agent reports -- the exercise's input and the suite's fixtures. The running
system is handed documents through the interface and reads nothing from that directory. Of
`workbook/`, only `account-sales-book.xlsx` is copied, as the seed for an empty disk.

Everything the image needs is copied explicitly by the Dockerfile: `pyproject.toml`, `alembic.ini`,
`migrations/`, `zaco/`, `lookup/`, `workbook/account-sales-book.xlsx`, `entrypoint.sh`, and the
frontend bundle from the build stage. **`lookup/` is easy to miss** -- without it the image runs
with an empty set of product short codes and silently resolves nothing, which looks like a working
system with more work to do.

### After it is up

Check `/api/health` (the health check path), then sign in at the service URL and change the seeded
password on your own account page. `/docs` serves the OpenAPI schema.

## Accounts

There is no self-registration. An administrator invites a specific email address and grants
permissions individually — `ingest`, `resolve`, `append`, `record_terms`, `view_reports`,
`admin`. `admin` does not imply the others.

That is not ceremony: every queue answer, DN approval, duplicate decision and append is stamped
with a person, and a duplicate-conflict record reading "chose this export because…" is worth
nothing if a shared account made the choice. See [DECISIONS.md](DECISIONS.md) D14.

No mail is sent. Copy the invitation link from the Accounts page and pass it on.

### Forgotten passwords

Three layers, and each exists because the one above it can run out.

1. **You know your current password.** Change it on your own account page (the name at the foot of
   the sidebar).
2. **You do not.** Say so from the sign-in page. That sends nothing — there is no mail here — it
   puts you on a list at the top of the Accounts page. An administrator opens your account, issues
   a one-time link and hands it to you the way your invitation reached you. It works once and lasts
   four hours.
3. **No administrator can sign in either.** With two administrators this is unlikely and not
   impossible, and until it existed there was no path at all: the first account is seeded only on
   an empty database, and an existing password is never reset. From the server:

   ```
   docker compose exec app python -m zaco.recover you@example.com
   ```

   It prints the same one-time link. There is no endpoint for this and nothing imports the module —
   it asks for possession of the server rather than of an account, and whoever has that already
   holds the database it reads and the workbook the system exists to write. It prints a link rather
   than setting a password, so the new password is typed by the person who will use it and never
   lands in a shell history. Pass `--base-url https://…` when the app is not on localhost.

Every one of these is written into that account's trail, at the foot of the Accounts page —
including a change of the address an account signs in with, which demands a typed reason because
it rewrites who every past decision appears to have come from.

## Working a round

1. **Stage a round** (`/staged`) reads a set of documents and shows what they amount to. Nothing
   is stored. Useful for checking an export before committing to it.
2. **Resolution queue** (`/queue`) saves a round and opens its questions. Four kinds, asked in
   this order because answering one can remove another:

   | | What it asks | Why no document answers it |
   |---|---|---|
   | Product links | are these two names the same fruit? | the reports and the statements use different vocabularies |
   | Product codes | what is Zaco's short code? | column G is the operator's own, and is in no report |
   | Delivery notes | which DN covers this delivery? | column A is Zaco's; the agent's `DELIVERY NOTE NO` is its own number |
   | Disagreements | which document is right, and why? | two exports described one record differently |

   Every card carries the evidence it was raised on and, for a delivery note, the proposal with
   the three tests that produced it. Nothing is applied until someone approves it, and the round
   cannot be closed while anything is open.
3. **Close the queue.** The round becomes `resolved` and its rows are ready for the workbook.
   Appending them is Phase 4.

Answers are remembered. A short code captured once is never asked for again; a rejected link is
never re-offered; a delivery note approved for a delivery holds. What a resolved round counted is
also remembered, which is what stops the June export -- which reprints two of May's dockets
verbatim -- from counting the same 65 cartons twice.

## Where things are

```
zaco/config.py         every environment-dependent value in the system, and nothing else
zaco/api/              /api/* JSON endpoints; the OpenAPI schema is at /docs
zaco/ingest/           the five readers and the content-based classifier
zaco/domain/           the grain: delivery -> consignment -> docket, and the workbook row
zaco/resolve/          the queue: delivery notes, product codes, opening stock, disagreements
zaco/workbook/         locating the operator's sheet and columns by header text, never position
zaco/db/               SQLAlchemy models; money is NUMERIC(14,2) and Decimal, never float
zaco/web/spa/          where `npm run build` puts the interface; served at / (gitignored)
frontend/              the React interface: a client over those same endpoints
migrations/            Alembic
tests/                 fixtures are the real files in data/, never tidied ones
```

A saved round stores the **documents themselves**, and the deliveries, consignments and rows are
re-derived from them each time. What the agent sent is the only thing that cannot be recomputed;
a correction to a reader then improves the whole history instead of leaving stale rows behind it.
What *is* stored is the part no document contains — the answers, each with a person's name on
it.

The interface calls only documented `/api/*` endpoints and holds no logic of its own, which is
what made replacing it a matter of drawing the same answers differently (D1). It is served from
the API's own origin rather than a separate host: the session is an HttpOnly `SameSite=lax`
cookie and there is no CSRF token in this system, so a second origin would need
`SameSite=None; Secure` and a CSRF layer built to go with it.
