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
  web/        Jinja templates, thin clients over /api/*
  db/         models.py + migrations/versions/0001..0004
tests/        431 tests
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
| 4 — the workbook (§5) | **done in substance, unfinished on screen** — see the open items |
| 4.5 — promote to Render | not started; needs Chris's Render account |
| 5 — reconciliation, Nett, settlement (§8) | not started |
| 6 — reporting (§9) | not started |
| 7 — agent conduct (§10) | not started |
| 8 — process both rounds, commit the book, write NOTES.md, open the PR | not started |

## Open items, most important first

### 1. The Workbook page does not show the workbook

**This is the next session's job and Chris raised it directly.** He opened `/workbook`, saw a
four-row summary panel and two empty sections, and said it "looks nothing like the workbook I
gave you."

He is right, and the cause is a design mistake rather than a bug. The grid exists and works, but
it only renders **inside a preview of a round that is ready to append** — and there are no ready
rounds, so the page shows nothing resembling a spreadsheet. The page currently answers "what is
the state of the book" when the operator came to see the book.

What it should probably do — the next session should decide, not take this as settled:

- Draw **the book's existing rows** in the same grid, always, straight from
  `zaco/workbook/locate.py:read_rows` — that is rows 2–4 of `Sheet1` today, with their real
  values and the operator's `NOTES` text visible.
- Append the preview rows **beneath them**, visually separated, so the operator sees where the
  round lands in the file they know.
- Keep the letters-and-headers row, the sticky header and the sticky row-number column, which
  already work.
- `read_rows` currently returns only `dn / stm_no / description / date` — it will need to return
  every column to draw the book. That is a small change to `BookRow` and one to `read_rows`.

Everything needed is already in place: `SheetLayout.headers` carries the book's own header text,
`SheetLayout.columns` the order, and `app.css` has the `.grid`, `.chip` and `.legend` styles.

### 2. Chris's demo data is split across three rounds

Rounds 1, 2 and 3 in the live database each hold part of one round: the sales file alone, the
consignment report alone, then the three payment and statement files. The five `PersonalTest/
round-a` files are meant to go up **together**. Split like that, the consignment report has no
sales to agree with and the statements have no rows to attach to.

Tell him to put rounds 1 and 2 aside (Resolution queue → *Put the round aside*, with a reason)
and upload all five at once. Expected then: 5 deliveries, 5 rows, R8,025.00, 12 open questions.
Do not do it for him without asking — they are his rounds.

### 3. Phase 5 fills the column Phase 4 deliberately left blank

`Nett Total` is written only when exactly one row sits under an account sale. Where a payment run
covers several rows the cell is blank and the grid says `SPLIT ACROSS N ROWS`, because
apportioning it has to sum to the payment exactly and that is §8's job. The largest-remainder
allocator, the fruit-named-deduction rule (finding 8: plums `3000 − 172.50 − 46 = 2781.50`,
nectarines `1000 − 57.50 = 942.50`, summing to exactly `3724.00`) and the five reconciliation
states all belong there.

### 4. Smaller things noted and not done

- `read_rows` reads four columns; the grid will want all of them (see item 1).
- The compose backup sidecar's copies are named `sidecar-*` and are deliberately **not** offered
  as rollback targets — a timer-driven copy can catch the file mid-write, which is the whole
  reason D4 puts the snapshot inside the append. If that ever changes, say why in the UI.
- The append marks the round before writing and rolls both back on failure, but a database commit
  that fails *after* a successful file write would leave the book ahead of the record. Guarded by
  the append-once check and visible in the version list; not otherwise handled.
- `render.py` and `domain/model.py` both expose `display_account_sale`; the second is canonical
  and the first delegates. Leave it that way or remove the shim, but not both.

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
