# Handover

**This file is append-only.** Every time Chris asks for a handover, add a new dated entry at the
bottom under `## Session log`. Never rewrite or delete an earlier entry — correct it by writing a
later one that says what changed and why. The sections above the log are the standing brief and
may be edited in place when a fact stops being true.

---

## What this project is

`ZacoAgents_Chris/` is a build exercise. Zaco takes fresh produce on consignment, places it with
market agents, and is never present when it sells. The only account of what happened is the nine
agent reports in `data/`. An operator transcribes those by hand into
`workbook/account-sales-book.xlsx` — the book the business settles real money against.

We are building a hosted system that reads a round of those reports, resolves the facts the
reports do not carry, appends to the operator's existing workbook without disturbing it, keeps a
durable record, and answers questions from that record.

Read in this order before touching anything:

| File | Why |
|---|---|
| `REQUIREMENTS.md` | The brief. Sections 3–10 are the spec; §12 says a plain interface is fine; §13 is the assessment order. |
| `DECISIONS.md` | D1–D14, agreed with Chris. These are settled. Do not relitigate one without asking. |
| `NOTES.md` | The sixteen findings in the supplied data that drive the design. |
| `C:\Users\Chris\.claude\plans\first-read-the-md-radiant-aho.md` | The full build plan, phase by phase, with per-phase tests. |
| This file | What actually happened, and what is left. |

## Chris

Solution engineer on this project; it is mostly AI-coded and he reviews it. He reads the code and
the commit history — the README says explicitly that how the work was sequenced is informative.

What he has asked for, that keeps applying:

- **Never commit to `main`, never force push `main`.** Everything lives on
  `feature/zaco-agents-system` and lands via PR at the end.
- **Simple language.** Explain in plain words, not jargon. Say what a thing does and why it
  matters, not what pattern it is.
- **Do not over-test.** Run only the test files covering what changed while working; run the full
  suite plus `ruff` and `mypy` **once per phase**, before the commit. Re-running all 431 tests
  after every edit re-proves work that was already green and was the single largest cost in the
  build. He noticed and asked about it.
- **Do not chase tangents.** When he says a thing is the next session's job, leave it.

## Running it

```
cd ZacoAgents_Chris
docker compose up -d --build          # app, postgres, backup sidecar
.venv/Scripts/python.exe -m alembic upgrade head
```

- App: <http://127.0.0.1:8000>
- Account: `chrisesterhuyse19@gmail.com` / `zaco-review-2026` (all six permissions). There is also
  a seeded `admin@example.com` whose password comes from `ADMIN_PASSWORD` in `.env`.
- Tests need Postgres. The `db` marker skips cleanly when it is unreachable, so a green run with
  everything skipped is not a green run — check the count.
- Tests use a separate `zaco_test` database and TRUNCATE between cases. The conftest copies the
  real workbook into a tmp dir; nothing in the suite touches `workbook/account-sales-book.xlsx`.

```
.venv/Scripts/python.exe -m pytest                 # 431 tests
.venv/Scripts/python.exe -m ruff format . && .venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy zaco              # strict, 47 files
```

**Windows gotchas that cost time.** The Bash tool's heredocs break on Python scripts containing
`'''` — write the script to the scratchpad with the Write tool and run it with
`.venv/Scripts/python.exe` instead. `python -c` with newlines is unreliable through Bash; use
PowerShell for those. Docker Desktop is at
`C:\Users\Chris\AppData\Local\Programs\DockerDesktop\Docker Desktop.exe`, not Program Files.

## The rules that must not be broken

These come from `DECISIONS.md` and the findings. Breaking one produces a workbook that opens
without complaint and is wrong.

1. **Nothing is located by position.** The brief prints 21 columns A–U. The real book has 23:
   `Buyer note` at C and `Packhouse` at V shift every letter after B, so `Baby Stock` is
   `=I{r}-K{r}` and not the `=H{r}-J{r}` the brief gives. Sheet and every column are found by
   header text. `zaco/workbook/locate.py`.
2. **A computed value never reaches a formula column.** Eight columns belong to the operator.
3. **`NOTES` is not read, not derived, not written.**
4. **Money is `Decimal` end to end**, `NUMERIC(14,2)` in Postgres, and crosses the wire as a
   **string** so no client can turn it into a float. `zaco/api/render.py`.
5. **Absent is not zero.** Returns the payment side cannot report are `None`, not `0`.
6. **Delivery-scoped quantities are counted once per consignment**, never per row.
7. **Merge products on evidence only, never on resemblance.** A suggestion is offered with its
   reasoning and never applied.
8. **The DN is never derived from the agent's `DELIVERY NOTE NO` field** — that is the agent's
   `203xxx` series, not Zaco's `14xxx`. Every DN proposal needs explicit approval.
9. **Documents are the durable record.** Everything else is re-derived on read, so a reader fix
   improves the whole history rather than leaving stale rows behind.
10. **Nothing is defaulted.** The queue blocks; the system says what it does not know.

## Where things are

```
zaco/
  ingest/     five readers + a content-based classifier (never sees a filename)
  domain/     model.py (grain), build.py (a round from documents), products.py (union-find)
  resolve/    dn.py, book.py, stock.py, queue.py, service.py  (service.py ties DB + build + queue)
  workbook/   locate.py (headers), append.py (the write), snapshot.py (versions, D4)
  api/        routes_* + schemas.py + render.py
  web/        spa/ -- the built React bundle, served at / (gitignored build artefact)
  db/         models.py + migrations/versions/0001..0006
frontend/     the React interface: Vite + TypeScript, built into the image
tests/        561 tests
PersonalTest/ hand-made documents for trying the system by hand; see its README
```

## Phase status

| Phase | State |
|---|---|
| 0 — branch, decisions, accounts, local stack | done |
| 1 — the five readers (§4) | done |
| 2 — domain model and grain (§3, §6) | done |
| 3 — resolution queue (§7) | done |
| 3.5 — taking a document back out | done |
| 4 — the workbook (§5) | done; the page draws the book itself since 2026-09-04 |
| 4.5 — promote to Render | **in progress**; render.yaml corrected, deploy needs Chris's Render account |
| 5 — reconciliation, Nett, settlement (§8) | done |
| 6 — reporting (§9) | done |
| 7 — agent conduct (§10) | done |
| 8 — process both rounds, commit the book, write NOTES.md | done 2026-09-05; the PR is deliberately not open |
| the React port (its own 8-step plan) | done 2026-09-06; the Jinja interface is removed |

## Open items, most important first

### 1. A row appended before its payment arrives is never revisited

**This is money and it is the first thing to build.** `JOH*SUB*5644210/1` sold in round 1, so
row 11 of the committed book has a blank `Nett Total` with `no payment run` recorded as the
reason. That was the honest answer when it was written. Its payment arrived in round 2, and the
reconciliation board now shows it **reconciled at R1,500 with a Nett of R1,275**.

Both halves are correct on their own and nothing joins them. Not rewriting an appended row is
deliberate and must stay that way — the book is the operator's and the whole claim of this system
is that it does not disturb it. What is missing is a screen that says *these appended rows have a
blank the record can now fill*, offering it as a **fresh append** rather than an edit. Without it
the operator has to notice R1,275 by hand.

Everything needed exists: `zaco/resolve/reconcile.py` knows the account sale is settled,
`zaco/workbook/locate.py:read_rows` can already read every column of every row, and
`zaco/workbook/agreement.py` already holds each appended round's claim against the file.

### 2. Chris's demo data is split across three rounds

Rounds 1, 2 and 3 in his live database each hold part of one round: the sales file alone, the
consignment report alone, then the three payment and statement files. The five `PersonalTest/
round-a` files are meant to go up **together**. Split like that, the consignment report has no
sales to agree with and the statements have no rows to attach to.

Tell him to put rounds 1 and 2 aside (Resolution queue → *Put the round aside*, with a reason)
and upload all five at once. Expected then: 5 deliveries, 5 rows, R8,025.00, 12 open questions.
**Do not do it for him without asking — they are his rounds.**

### 3. Hosting is in progress

**This is what Chris is working on now.** `render.yaml` exists and its Docker paths have been
corrected — the application is a subdirectory of the repository, and Render resolves
`dockerfilePath` and `dockerContext` from the repository *root* whatever `rootDir` says. Phase 4.5
still needs Chris's own Render account, so the deploy itself cannot be done for him. The dated
entry at the bottom of the session log has the detail.

The separate-origin warning that used to sit here is now moot and worth recording as settled: the
frontend is served by FastAPI from its own origin, so the session cookie stays `SameSite=lax`,
`credentials: "same-origin"` is correct, and no CORS or CSRF layer was ever needed. A future
separate-origin client would still need `credentials: "include"`, `allow_credentials`,
`SameSite=None; Secure` or a token flow — but nothing here depends on that.

### 4. The pull request is deliberately not open

Everything Phase 8 asks for is committed and pushed. Chris was offered the PR — draft, ready, or
body-only — and chose **not yet**. Do not open it without him saying so.

### 5. Nine product short codes in column G are not the operator's

`lookup/product-codes.json` carries two. The rest were supplied while processing both rounds,
because the queue rightly blocks until somebody gives them. They follow the shape of the
operator's existing rows but drop the `Imp` prefix, which reads as *imported* and is a claim
nothing in the data supports. They are labels, not figures — no money depends on them — but they
should be replaced with the real ones when Chris has them. Listed in `NOTES.md`.

### 6. Smaller things noted and not done

- `PersonalTest/README.md` was three phases out of date and was refreshed on 2026-09-05; check it
  again if the queue's behaviour changes.
- The compose backup sidecar's copies are named `sidecar-*` and are deliberately **not** offered
  as rollback targets — a timer-driven copy can catch the file mid-write, which is the whole
  reason D4 puts the snapshot inside the append. If that ever changes, say why in the UI.
- The append marks the round before writing and rolls both back on failure, but a database commit
  that fails *after* a successful file write would leave the book ahead of the record. Guarded by
  the append-once check and visible in the version list; not otherwise handled.
- `render.py` and `domain/model.py` both expose `display_account_sale`; the second is canonical
  and the first delegates. Leave it that way or remove the shim, but not both.
- `_open_questions` re-derives a whole round per unsettled round in the rounds list. Correct, and
  the only way the figure is true, but it is the obvious thing to cache if that list ever gets
  long.

---

# Session log

## 2026-09-03 — Phases 3.5 and 4, and a page that drew nothing

Branch `feature/zaco-agents-system`, eleven commits ahead of `main`, `main` untouched.
**431 tests pass**, `ruff check`, `ruff format --check` and `mypy zaco` (strict, 47 files) clean.

### Commits this session

```
2cf5b13 The workbook preview is a grid of the sheet it is going into
7ae228e The workbook page drew nothing, and nothing could have told us
43ac357 Phase 4: the operator's book, appended by header and never by letter
81f2a9d Taking a document back out of a round
38de6ee PersonalTest: files to try the system by hand, and three defects they found
```

### What was built

**Phase 3.5 — taking a document back out.** A file can be perfectly readable and still not belong
in a round: another producer's payment export, or last quarter's run, is a good Payment Details
report and the classifier has no reason to refuse it. A document is now *withdrawn*, not deleted
— its figures leave the round, the bytes stay with the person and the reason. Plus reopen
(resolved or set-aside back to staged) and abandon, both needing a typed reason, and a
`round_events` table holding the trail that `withdrawn_at` alone cannot.

**Phase 4 — the workbook.** `zaco/workbook/append.py` writes rows beneath what is there, with the
eight formula columns written as formulas for the new row number, built from letters resolved out
of the header row. `snapshot.py` takes the copy as a step inside the append (D4): copy aside,
write to a temp file, replace, put the copy back on any failure. `routes_workbook.py` exposes
state, preview, append, download and rollback. A round cannot be appended twice, and an appended
round cannot be reopened.

Verified end to end against the live stack: 4 rows written at 5–8, `=I5-K5`, `=SUM(K5*M5)`,
`=IFERROR(P5*70%,"-")`, number formats matching the rows above, then rolled back to a
byte-identical file.

### Defects found and fixed

Each of these would have produced a file that opened without complaint.

1. **A minted delivery note could reissue one from an earlier round.** Minting only avoided the
   current round's approved DNs. Two loads under one number, in the book money is settled against.
2. **Nett Payment Adjustments lost half its account sale numbers — in the supplied `data/`.** The
   file uses two shapes on one page: `JOH*SUB*5640001/12026-04-13` jammed and
   `PRE*BT*380101 2026-04-01` spaced. Only the first was handled; `PRE*BT*380101` and `380102`
   sat in the system as real payments with nothing to join on.
3. **An account sale restated in a later round was a second record, not a conflict.** Only the
   first upload survived.
4. **`openpyxl` converts a `Decimal` to a float on the way into the file.** A price of 400 ÷ 3 was
   stored as `133.33333333333331`. Prices are now rounded to the five decimals the column already
   displays — a number that survives the trip — and a row whose money no longer divides says so.
   Currency columns are two decimals and land to the cent.
5. **`Qty Received` took the delivery's total on the first row of each consignment**, which
   doubles it for a delivery carrying two products. It is the consignment's own figure now, and
   absent is blank with a reason rather than nought.
6. **The preview flattened each row's explanation alongside its cells** — and one of the book's
   own columns is called `NOTES`, which silently overwrote every explanation with an empty string.
7. **One stray backslash in `workbook.html` closed a JavaScript string early**, so the whole
   inline script failed to parse and the page rendered its heading and stopped. The API was fine
   and every test passed.

That last one mattered beyond itself: **nothing in the suite was in a position to notice.** Pages
render server-side, the API tests never run a browser, and a broken template returns HTTP 200 with
the right bytes. `tests/test_templates.py` now runs `node --check` over the inline script of every
page, verified by putting the backslash back and watching it fail.

### State left behind

- Live database: Chris's rounds 1, 2 and 3, all staged. Test rounds this session created were
  deleted; delivery notes, product codes and non-evidence decisions from those runs were cleared.
- `workbook/account-sales-book.xlsx` on the volume: back at 3 rows, byte-identical to before.
- Backup volume: only the sidecar's own copies. Test snapshots removed.
- Nothing outstanding in the working tree; everything is committed.

### What Chris said, that shapes the next session

> "This looks nothing like the workbook I gave you."

See open item 1. He also asked why the suite runs hundreds of tests — he read the count as
attempts rather than as the size of the suite. Worth stating plainly when reporting: `431 passed`
is 431 checks, all run every time, not 431 tries.

## 2026-09-04 — Phase 5, and a bug that undid the double-count protection

Branch `feature/zaco-agents-system`, 30 commits ahead of `main`, `main` untouched.
**506 tests pass**, `ruff check`, `ruff format --check` and `mypy zaco` (strict, 54 files) clean.

### The defect worth reading first

`history()` selected rounds with status `RESOLVED`. Appending sets the status to `APPENDED`. So
**the moment a round was written into the book it dropped out of the history every later round is
derived from.** Three consequences, none of which announced themselves:

1. **S5 came back.** The June export reprints May's nectarine dockets verbatim; counted twice the
   book gains 65 cartons and R3,500 that never happened. That protection is `past.counted`, which
   was empty. Append May, load June, and the double count returns looking entirely normal.
2. **Opening stock restarted** at what was sent, though §6 says a consignment does not respect the
   boundary of an export.
3. **Account sales the book says were paid read as unpaid**, because `past.settled` was empty — a
   warning about a state that is not real, which S6 calls worse than no warning.

`rounds_after()` had the same blind spot from the other end. Both now use `SETTLED_STATUSES`.
Found on the live database, where round 1 is appended and round 2 saw nothing of it. **No
migration was needed to repair it** — the documents are the record and everything else is
re-derived (S1), so the same query afterwards saw 7 counted dockets and 4 carried balances.

### What was built

**The workbook page draws the workbook** (open item 1 from the last entry, and Chris's original
complaint). `read_rows` gained `with_cells=True`, widening `BookRow` to every column keyed by
**letter** — the operator's own columns have no field name and are as much a part of the row as
ours. `/workbook` now draws the file first and always; a round is drawn into that same grid,
beneath a line if it is not yet appended, highlighted in place if it is.

**Phase 5, all of §8.**

- `zaco/money/allocate.py` — largest remainder, so shares sum to the payment *exactly*. Refuses on
  no rows, all-nought weights, or any negative weight (a row whose returns exceed its sales needs
  a person, not an apportionment).
- `zaco/money/deductions.py` — the printed-deductions split. A deduction counts as naming a fruit
  **only when a product on that same statement carries one of its words**: evidence, not
  resemblance. 382900 comes out of the real file as 2781.50 / 942.50 = 3724.00 exactly.
- `zaco/resolve/reconcile.py` — the five states, over the **accumulated record** rather than one
  round. Per-round reporting called the same account sale unpaid in the round that sold it and
  unexplained in the round that paid it.
- `Nett Total` fills. 382880 pays R250 over three rows: 83.34 / 83.33 / 83.33.
- `zaco/resolve/settle.py` + migration `0005` — suppliers, terms per consignment, payments.
- `/reconciliation` and `/settlement`. Neither nav entry says "Phase 5" any more.

### Defects found and fixed, beyond the history one

- **An appended round previewed at the wrong rows.** `start = appended.first_row if appended else
  next_row` — `appended` only exists during a live append, so a GET fell through to the next
  *free* row. Round 1 occupies 5–9 and was drawn at 10–14, with every formula built for the wrong
  row, under a button labelled "See what was written". The path had never been reachable until a
  button was added for it.
- **Headings over numeric columns were left-aligned.** `td.num` existed; `th.num` did not, so 21
  headings across five templates asked for right alignment and got the default. Chris spotted it
  on a screenshot. Nothing in the suite could — a misaligned header renders HTTP 200 with correct
  bytes, the same blind spot as the stray backslash in Phase 4.
- **Two pre-existing tests were deleted** by a bad edit while splitting commits: a truncation at a
  function offset that was mid-file rather than end-of-file. Restored from `6562ce0`. The suite
  count going 447 → 445 is what caught it.

### Tests written that proved nothing, and were replaced

Recorded because it happened three times and is easy to repeat:

- `assert not (set(shares) & {... if False})` — an intersection with the empty set.
- A cross-round test comparing two sets that were both empty, because round 1 has no multi-row
  account sales at all.
- An overlap test using `/api/rounds/stage`, which does not consult history, so it passed against
  the bug it was written for.

**Every bug fix since is confirmed by reinstating the bug and watching the test fail.** That is
now the standing rule; see the `what-tests-to-write` memory.

### Decisions taken that are not in DECISIONS.md

- **A single-row account sale is filled whether or not the two sides agree.** §8's "only fully
  matched groups are filled" exists to stop untrustworthy *proportions* being used, and one row
  has none. Withholding it would leave a cell empty over a disagreement about the gross.
- **A group split across two rounds is never settled twice**, and that falls out of the same rule
  rather than needing a guard: neither round can see all its rows, so neither fills it.
- **A levy naming a fruit that is not on the statement spreads generally**, with a note saying so.
  It has to land somewhere and refusing the round would block real work.
- **Commission is bounded 0–100.** Outside that is a typing slip that would pay a supplier a
  negative amount or more than arrived.

### State left behind

- Live database: Chris's rounds 1 (appended), 2 (resolved), 3 (staged) — still the three-way split
  of one `PersonalTest/round-a` round. **Nothing on his record can reach *Settled*** even with
  terms, because those rounds carry no payment documents. Suppliers and terms tables are empty; I
  did not write demonstration data into his database.
- `workbook/account-sales-book.xlsx` on the volume: 8 rows, round 1 at 5–9. Unchanged this session.
- Working tree clean, everything pushed.

### What Chris said, that shapes the next session

He asked how hard the Nano Banana mock-ups would be under a React frontend, and chose **phases
first, frontend after**. When it happens: match that mock-up's layout closely but **keep the
current colour palette**. The one thing that will not be free is auth — a session cookie with
`credentials: "same-origin"` needs `credentials: "include"`, `allow_credentials` and
`SameSite=None; Secure`, or a token flow.

He also relayed that the tester thought unit tests "aren't really needed here", and chose **carry
on as before** — do not offer to trim or delete the suite again.

### Open items, most important first

1. **Phase 6 is where thresholds get chosen for the first time.** `NOTES.md` currently says none
   have been picked, and §13 assesses reasoning. Every weight, band and rate needs recording with
   its argument as it is made, or the note becomes wrong.
2. **`PersonalTest/README.md` predates Phase 5** and stops at "the queue stops at resolved". Its
   "what this set does not cover" list is now out of date twice over.
3. **Chris's split rounds.** Rounds 1 and 2 aside, five files up together — his to do.
4. `render.py` and `domain/model.py` both expose `display_account_sale`; one delegates.

---

## 2026-09-05 — Phases 6, 7 and 8, and two defects found by using the thing

Branch `feature/zaco-agents-system`, 37 commits ahead of `main`, `main` untouched.
**549 tests pass, nothing skipped**, `ruff check`, `ruff format --check` and `mypy zaco`
(strict, 60 files) clean. The pull request is **not** open, at Chris's instruction.

### What was built

**Phase 6 — reporting (§9).** `zaco/reporting/reports.py`, `GET /api/reports?period=all|month|week`,
`/reports`. Sourced from **dockets, not workbook rows**: a docket no payment run has named yet
forms no row, and the record has one — R800 of grapes on 2026-06-02 — so counting rows would have
left the takings R800 short while looking complete. An unknown period is refused with 422 rather
than quietly treated as all time.

**Phase 7 — agent conduct (§10).** `zaco/conduct/conduct.py`, `GET /api/conduct`, `/conduct`.
Recorded as **D15**. The not-answerable conclusion is a **field on the result**, not a paragraph
in the template — a page can be redesigned and lose a paragraph, and what is left reads as a clean
bill of health on the thing it cannot see.

**Phase 8 — both rounds through the system.** Fourteen rows appended beneath the operator's three,
round 1 at rows 5–11 and round 2 at 12–18, driven through the running stack over the real HTTP API
on an **isolated compose project** (`-p zaco_phase8`, own DB and volumes, port 8100) so nothing
touched Chris's live stack or the rounds already in it. `NOTES.md` now states every threshold with
its argument and no longer claims §§8–10 are unbuilt.

### The two defects, both found by using the system rather than by testing it

**`RoundSummaryOut.open_questions` was never assigned**, so it took the schema default of nought
on every round in the list — including one whose fourteen open questions were blocking its append.
The detail view had computed it correctly all along, so the two disagreed and the list was the one
an operator reads to decide what needs attention. Proved live: the same round went from `OPEN=0`
to `OPEN=10` once the fix was running.

**The suite used the deliverable as its fixture.** `tests/conftest.py` and two test modules copied
`workbook/account-sales-book.xlsx` and asserted against what was in it — that rows go beneath what
is already there, that the `14xxx` series ends where it ends. That file is also what the brief
asks to be committed *with both rounds processed into it*, so it grows, and seventeen tests were
really asserting against whatever had been appended last. The pristine three-row book now lives at
`tests/fixtures/account-sales-book.pristine.xlsx`.

### Three things a later session should not have to rediscover

1. **`docker compose restart app` serves stale code.** The Dockerfile `COPY`s the source in rather
   than mounting it, so a restart comes back running whatever was baked into the existing image.
   Nothing errors; a newly registered route simply 404s as though it were a mistake in the code
   just written. Use `docker compose up -d --build app`. Now written up in `docs/RUNNING.md`.
2. **The admin password is `change-me-please`, not `change-me`.** `docker-compose.yml` sets
   `ADMIN_PASSWORD`, which overrides the default in `zaco/config.py`. `docs/RUNNING.md` has said so
   all along. A 401 here is not evidence that anybody changed anything.
3. **A green run with everything skipped is not green.** The `db` marker skips when Postgres is
   unreachable. Check the summary line says `549 passed` with no `skipped`.

### What the processed book proves

- rows 1–4 **byte-for-byte unchanged**; column V, which no report fills, still empty on all 14 rows
- all **eight formula columns are formulas**, each built from the letters resolved in that file and
  referencing its own row
- **DN 14721 on rows 5 and 6**, 14880 on 11 and 13 — one delivery across two account sales is two
  rows, and `Qty Received` is written once
- opening stock carries **across the round boundary**: cherries 14 → 12, oranges 200 → 150
- AccSale 382880's R250 splits **83.34 / 83.33 / 83.33**, summing to the payment exactly
- row 11's Nett is blank with its reason recorded — see open item 1, which is where that leads


## 2026-09-06 — A React frontend, a way back into an account, and the Jinja pages removed

Branch `feature/zaco-agents-system`, `main` untouched. **561 tests pass**, `ruff check`,
`ruff format --check` (111 files) and `mypy zaco` (61 files, strict) clean. The image builds and
runs; the app is served at `/`.

### What changed

The eight-step frontend plan in
`C:\Users\Chris\.claude\plans\first-read-through-the-sparkling-meadow.md` is complete. The
interface is now React + TypeScript, built by a `node:22-alpine` stage inside the same image and
served by FastAPI from its own origin. **Fourteen Jinja templates, `app.js` and `zaco/web/routes.py`
are gone** — about 2,600 lines removed against 180 added in the final step.

Between the plan's step 7 and step 8, accounts got the thing they had never had: a way back in.

### The three layers of getting back into an account

Each exists because the one above it runs out.

1. **You know your password** — change it on your own account page.
2. **You do not** — say so from the sign-in page, which puts you on a list at the top of Accounts.
   An administrator issues a one-time link, valid four hours, and hands it over. Nothing is
   emailed; there is no mail in this system by design (D3).
3. **No administrator can sign in either** — `python -m zaco.recover you@example.com`, run on the
   server. **There is no endpoint for this and nothing imports the module.** It asks for possession
   of the server rather than of an account, and whoever has that already holds the database it
   reads and the workbook the system exists to write. It prints a link rather than setting a
   password, so the new password is typed by the person who will use it.

Layer 3 exists because Chris pointed out that layers 1 and 2 dead-end together: the first account
is seeded only on an empty database and an existing password is never reset, so with both
administrators locked out the system was unopenable with the operator's live workbook inside it.

Accounts also gained a **trail** (`account_events`). Changing the address an account signs in with
demands a typed reason, because it rewrites who every past decision appears to have come from.

### Three protections, each verified by breaking it

Removing each guard in turn failed exactly one test and nothing else:

- **single-use** — a spent link works twice
- **deactivated accounts** — somebody turned off walks back in on a link issued beforehand
- **enumeration** — `/api/auth/forgot` saying "no such account" turns the sign-in page into a way
  to find out who works here, one address at a time

### Two defects found by using it rather than by testing it

**The reset page read the server's sentence to decide whether the link was dead.** It isn't:
`use_reset` checks the link first and spends it *last*, so a password under twelve characters comes
back as a refusal with the link still perfectly good — and the page would have told the person to
go and get another one. The length is now checked client-side against the same constant, which
leaves only refusals nobody can fix by retyping.

**Moving the app to `/` would have answered mistyped API paths with a page.** While it sat under
`/app`, nothing outside that prefix reached the mount. At `/` the mount catches everything
unmatched, so `GET /api/nonsense` would have returned HTTP 200 and HTML — reported by a client as a
JSON parse error, which points at the response body rather than at the URL that was wrong.
`_is_client_route` keeps `api` and `assets` out; `test_the_api_is_not_shadowed_by_the_app` pins it.

### The development database was destroyed by the test suite

**Read this before running any subset of the suite.** The `zaco` database was truncated and
re-seeded with fixture data during this session. Chris's account and the rounds behind the rows
already in the workbook are gone and are not recoverable — there is no database dump, and the
sidecar backs up the workbook only.

**The workbook itself was never touched.** `account-sales-book.xlsx` is intact, 7,273 bytes,
unchanged since 3 September, with its three saved versions and the sidecar snapshots present.

The cause was latent from the moment `tests/test_spa_mount.py` was written, and had nothing to do
with the flip:

- `zaco/config.py`'s default `database_url` is the **development** database, `.../zaco`.
- `conftest._configure_environment` redirects that to `zaco_test`, but ran only when a test asked
  for a database fixture, and cleared `get_settings`'s cache without clearing the SQLAlchemy
  engine built from it — a module-level global in `zaco/db/base.py`, created on first use.
- The three `@needs_build` cases in `test_spa_mount.py` need no database fixture, but each builds
  a `TestClient`, which runs the app's lifespan, which opens a session.

So any run whose first file was that one bound the engine to the development database, and every
`clean_db` afterwards truncated it — reporting a row of green dots while it did. Running the whole
suite alphabetically was safe only by accident, because `test_accounts_api` happens to come first
and happens to use a database fixture. It was triggered by
`pytest tests/test_spa_mount.py tests/test_password_recovery.py tests/test_workbook_api.py`.

Three things now stop it, and the last one is the one that matters:

1. `_configure_environment` resets `base._engine` and `base._SessionLocal`, not just the settings.
2. `settings_env` is `autouse`, so it runs before every test and ordering cannot decide anything.
3. `clean_db` calls `_must_be_a_test_database`, which refuses to truncate any database not named
   `*_test` and says which one it saw. `tests/test_suite_safety.py` pins it.

Verified by putting a marker row in the live database and running the exact command that had
destroyed it: the row survived, and survived a full suite run afterwards.

### Things a later session should not have to rediscover

1. **`npm run build` is not optional outside Docker.** There is no server-rendered fallback any
   more. Without it, uvicorn serves a working API and a 404 at the root — it says so in the log.
   Documented in `docs/RUNNING.md`.
2. **`frontend/src/api/schema.d.ts` is generated and committed, and nothing regenerates it.**
   Run `npm --prefix frontend run types` with the API up after changing an endpoint's shape. It is
   deliberately not automatic: a silent regeneration turns a breaking API change into a frontend
   that compiles against the break.
3. **Never run two `pytest` invocations at once.** They share `zaco_test` and truncate between
   cases, so the second one wipes the first one's seeded admin mid-test. It presents as a dozen
   unrelated failures with a unique-constraint violation buried in the log.
4. **`jinja2` is no longer a dependency.** Removed from `pyproject.toml` and the Dockerfile with
   the templates.

### What is left

- **Hosting (Phase 4.5).** `render.yaml` is written and unexercised; it needs Chris's Render
  account. Nothing in the application changes between the two targets — only the environment.
- **The pull request.** Not opened; Chris has not asked for it.
- **The blank-Nett follow-up** from the Phase 8 entry above is still open, and is still the first
  thing worth building next.


## 2026-09-06 (later) — Preparing for Render

**Chris is deploying to Render now.** This is the live piece of work; treat anything below as the
state he is working from rather than as finished history. Phase 4.5 has been the only open phase
since Phase 8, and it was deliberately left until the local stack worked end to end so that hosting
could never be blamed for a bug that was really in the application (D3).

Nothing in the application changes between the two targets. What changed here is the description of
how to host it, and one file that could not have been right until somebody tried.

### The blocker, fixed before it could be hit

`render.yaml` said `dockerfilePath: ./Dockerfile` and `dockerContext: .`. **Neither would have
worked.** This application is a *subdirectory* of its repository — the root holds only
`ZacoAgents_Chris/` and `.github/` — and Render resolves both of those from the **repository root,
regardless of `rootDir`**. The build would have failed before it started, with no log to read.

They now name the subdirectory, and `rootDir: ZacoAgents_Chris` was added alongside — it is a
separate thing that only decides which commits trigger a build, so a change to the repo-root CI
workflow no longer redeploys the app.

`dockerContext` decides two further things that are easy to get wrong together: `.dockerignore` is
read from the *context* root, and the Dockerfile's `COPY` lines are relative to it. Both are
correct as long as the context is `ZacoAgents_Chris` and not the repo root.

**One thing is still Chris's to do:** Render looks for a blueprint at the repository root by
default, and this one is at `ZacoAgents_Chris/render.yaml`. Either point Render at that path when
creating the Blueprint, or move the file to the root — the paths inside are written from the root
either way, so they survive the move. It was not moved here because that is a change to the
repository root, and the root is not this project's to rearrange unasked.

### `.dockerignore` rewritten

The build context is now **1.5 MB of the 339 MB on disk**, and the file is organised by *why*
something is excluded rather than as one list, because the reasons are not the same:

- 335 MB of local tooling (`.venv` alone is 181 MB, `node_modules` 136 MB, `.mypy_cache` 18 MB).
- `.env` and `.env.*`, which are local by design (D3). One baked into an image would silently win
  over the hosted environment.
- `zaco/web/spa/`, `frontend/dist/`, `*.tsbuildinfo` — build artefacts that must be made by the
  `frontend` stage. Shipping a laptop's bundle is how the image and the repository stop agreeing.
- `tests/`, `PersonalTest/`, `data/`, `docs/`, `*.md`, `docker/`, `docker-compose.yml`,
  `render.yaml`, `workbook/template.xlsx` — not part of the running application and not `COPY`d.

Verified by building the image with the new file and serving `/`, `/api/health` and `/admin` from
it. Excluding something the image needed would not have been caught by the suite.

**`lookup/` is the one that must never be excluded.** Without it the image runs with an empty set
of product short codes and silently resolves nothing, which looks like a working system with more
work to do.

### Before the first deploy

`ADMIN_EMAIL` and `ADMIN_PASSWORD` are `sync: false`, so the blueprint does not carry them and they
must be set in the dashboard. The first account is seeded **only on an empty database** and an
existing password is never reset, so a value left wrong is the one you are stuck with — the way out
is `python -m zaco.recover`, which needs a shell on the server. Leave `SECRET_KEY` on
`generateValue`; the app logs a warning while the shipped default is still in use.

### Two corrections to earlier entries

1. **There is CI**, at `.github/workflows/ci.yml` — repository root, `working-directory:
   ZacoAgents_Chris`. It runs `ruff check`, `ruff format --check`, `mypy`, `alembic upgrade head`
   and `pytest -q` on every push and pull request, against a Postgres service with `DATABASE_URL`
   pointed at `zaco_test`. An earlier statement in this session that there was no CI was made after
   looking only inside `ZacoAgents_Chris/`. Note it does **not** run `npm run build`, so the
   `needs_build` tests — the SPA mount, and the one checking a reset link reaches a page — skip
   there and are exercised only locally.
2. **CI is safe from the truncation bug** described in the previous entry: it sets `DATABASE_URL`
   explicitly to a `zaco_test` database, which the new guard accepts.

### What is still true from the previous entry

The development database still holds only fixture debris — one test round, a stray
`operator@example.com`, and an admin whose password is the test fixture's `seeded-admin-password`
rather than the documented `change-me-please`. **None of that reaches Render**, which starts from
an empty managed Postgres and seeds from `ADMIN_EMAIL`/`ADMIN_PASSWORD`. The local mess and the
hosted deploy are independent problems; the hosted one does not have to wait for the local one.
