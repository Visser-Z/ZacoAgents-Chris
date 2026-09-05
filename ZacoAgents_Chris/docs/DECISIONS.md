# Decisions

Answers to the questions `REQUIREMENTS.md` and the data left open, agreed with the solution
engineer before any code was written. Recorded here so that every figure the system produces can
be traced to a decision someone actually made, rather than to a default nobody chose.

Each decision states **what was decided**, and where it matters, **what was rejected and why**.
Open questions are at the bottom — they are surfaced in the UI rather than guessed at.

---

## D1 — Stack

**Python 3.12 + FastAPI, API-first.** Everything is exposed under `/api/*` as JSON with a
generated OpenAPI schema. The built-in interface is a thin Jinja + HTMX client that calls only
those endpoints.

*Why:* `openpyxl` is the only mature library that can append to an existing `.xlsx` while
preserving the operator's formulas, styles and untouched columns — which is assessed item 5 in
§13. Building API-first means a React or Flutter frontend can be added later with nothing but
CORS and the schema; no server rewrite.

*Rejected:* TypeScript/Next.js — the JavaScript xlsx libraries are noticeably worse at
preserving an existing workbook. Streamlit — too weak for a blocking resolution queue and hard
to test.

## D2 — Storage

**Postgres**, money as `NUMERIC(14,2)`, Alembic migrations. `Decimal` end to end in Python; no
float ever touches a currency value. The workbook itself lives on a named persistent volume.

*Why:* §8 requires agreement "to the cent, within R0.01", and the Nett shares must sum to the
payment **exactly**. Float cannot promise that.

## D3 — Deployment: local first, then hosted

The system runs end to end on `docker compose up` on a local machine — Postgres, named volume,
backup sidecar, seeded admin — **before any hosting is configured**. Hosting is then a switch,
not a rewrite: the same `Dockerfile` and the same code go to Render (web service + managed
Postgres + mounted disk), with only environment variables differing.

Local remains a first-class target permanently, not a scaffold that rots. If the application
code ever needs changing to deploy, that is a portability bug to fix, not a hosting special case
to add.

*Note:* `REQUIREMENTS.md` §12 says a polished interface and authentication are not required.
Hosting is required here regardless of that, by decision of the solution engineer.

## D4 — Backups

The timestamped snapshot of the workbook is a **step inside the append transaction**:
snapshot → append → commit, or roll all of it back. Retention keeps N versions with one-click
rollback in the UI.

*Rejected:* a sidecar container watching the volume. Two reasons. First, a Render disk mounts to
exactly one service, so a sidecar cannot share the volume — the same is true of Fly volumes and
Railway volumes; only a VPS running compose directly supports the pattern. Second, and more
importantly, a watcher can snapshot a file **mid-write**; a snapshot inside the transaction
cannot. The compose file still ships a sidecar for local/VPS parity, but it is not the guarantee.

## D5 — Resolution: a blocking queue

A round is parsed and **staged**. Unresolved items are listed as a queue. **Nothing is appended
to the workbook until every item is answered or explicitly deferred.** Answers are remembered so
the same question is never asked twice.

*Why:* §2 — "a missing fact is never invented" — is load-bearing and assessed. Appending rows
with gaps to be filled later means a half-written row sits in the operator's live book.

## D6 — Scope

All of §4–§10, depth-first in the order given. Each layer starts only when the one below it
verifies against both rounds of data.

## D7 — STM No format

**A bare number where one exists (`382405`); the full reference as text where it does not
(`5644200/1`).** Internally, joins always use the canonical `(agent, full reference)` pair — the
workbook column is display only, so the display form carries no correctness risk.

*Why:* the operator's existing rows hold bare numbers (`381900`, `381950`), so this matches the
book. Farmers Trust references are `PRE*BT*382405`; Subtropico's are `JOH*SUB*5644200/1` and have
no numeric form.

*Rejected:* dropping the `/n` suffix to make everything look numeric. `5640001/1` and
`5640001/2` are **two separate April payment runs** worth R5,100 and R3,230. Dropping the suffix
merges R8,330 into one statement number. This is a real collision in the supplied data, not a
hypothetical.

*Also decided:* **`0` is never written.** Workbook row 3 holds `STM No = 0`, and round 2 carries
a docket with payment reference `PRE*BT*0` and date paid `0000-00-00`. `0` is the operator's own
"not paid yet" marker. A docket with no account sale cannot form a row at all — a row *is*
delivery × product × account sale — so it stays in "sold, not yet in any payment run" until a
payment report names it.

## D8 — The delivery note number

**The DN is never taken from the agent's `DELIVERY NOTE NO` field.** That field
(`DELIVERY NOTE NO : 203003` on the account sales statements) is in the agent's `203xxx` series —
the same series as the payment reports' FMS IDs `203451`–`203477`. Zaco's own DNs are `14xxx`.
Reading it into column A would produce a workbook that looks complete and is wrong in every row.

The resolution order is:

1. **Reuse** a DN where the workbook already links one (via account sale, supplier ref or
   delivery). Never invented, purely evidential.
2. Otherwise **propose the supplier ref's reference half**, if it passes all three tests:
   in the DN number range, **and** not a known producer code, **and** not equal to its own
   producer half.
3. Otherwise **mint the next free number** in the `14xxx` series.

**Every proposal in steps 2 and 3 requires explicit operator approval before it is written.**
The queue supports assigning **one DN to several deliveries in a single action**.

*Why the multi-assign matters:* deliveries `1183200Z`, `1183201Z` and `1183202Z` — pears,
peaches, strawberries, refs `14885`/`14886`/`14887` — share a delivery date, a sale date and a
single account sale (382880, one payment of R300). Those are very plausibly one truck under one
DN. Adopting the ref half automatically would create three DNs where the operator has one, and
column D, sell-through and unsold-carton figures would all fragment.

*Known limitation, stated plainly:* the workbook holds account sales `381900`/`381950`, and the
supplied data holds `382399`–`382999`. **They do not overlap, so step 1 resolves 0 of the 12
deliveries in these two rounds.** The join is still correct and still built — it pays from round
three onward. Today the workbook's only contribution is establishing the `14xxx` number space.

*Risk accepted:* a DN presumably already exists on a physical delivery note that left with the
truck. A minted number may disagree with that paper. Requiring approval makes it a decision
rather than a fabrication — the same logic §5 applies to column I's 70% default — and D9 records
which numbers were minted so a later dispute can tell them apart.

## D9 — DN provenance

Column A holds a clean number, so the operator's filters, sorts and formulas keep working.
**Who approved it, when, and whether it was transcribed, ref-derived or system-minted** is held
in the system and shown in the UI and in reports. Nothing pollutes the operator's sheet.

## D10 — DN flags

A row is flagged "this reference is provably not a delivery note" **only on positive evidence.**

**Corrected in Phase 3, once the readers had actually run.** There are 11 deliveries, not 12,
and the flag falls on **2** of them:

| Supplier Ref | Delivery | Evidence |
|---|---|---|
| `20026*20026` (apples) | `1183050Z` | reference half equals Zaco's own producer code |
| `20026*14013` (plums) | `1183001Z` | `14013` is a producer code — the producer half of `14013*14710` |

`20026*00000` is real and is still counter-evidence, but it appears **only on the payment side**
(FMS `203452` and `203454`), and the payment record names no delivery. The nectarine delivery it
probably belongs to, `1181705Z`, carries a **blank** Supplier Ref in every sales document.

That distinction is kept rather than smoothed over. A blank is **absence**, and "provably not a
delivery note" is a claim; making it about a blank would be asserting something no document
supports. Both deliveries end up with a minted number — the same answer for different reasons,
and the queue says which.

The other nine carry no flag. §7 is explicit: "a warning on every row is a warning nobody reads
by the second week."

*Note:* `14xxx` is **not** exclusively DN space — `14013` is a producer code and is also five
digits starting `14`. That is why the ref-half test in D8 has three conditions and not one.

## D11 — Produce carried for another producer

The documents do not say whether Zaco issues its own delivery note for produce it carries for a
different producer (`14013*14710`, grapes for producer 14013). **The queue asks, per delivery.**

*"No DN — carried for producer 14013"* is a **valid recorded answer**, not a blank. The row is
written with column A visibly empty and the reason attached, so the emptiness reads as a decision
rather than as an unfinished feature.

## D12 — Duplicate and overlapping exports

Identity of a docket is **composite**: consignment + docket number + date sold + quantity +
payment reference.

*Why composite:* docket numbers repeat legitimately. `PRE*B6E01C39001*06Z` appears in **both
rounds** for consignment `118312006Z` with different dates, quantities and account sales.
Deduping on docket number alone silently deletes a real R900 sale.

Two cases, handled differently:

- **Same identity, every figure identical** → skipped automatically, **with a visible alert on
  the round summary**. Never a silent log line.
- **Same identity, any figure differs** → that **record** is suspended — not the whole file.
  Both sources are shown side by side. The operator picks one and **must type a reason**. The
  choice and the reason are stored and displayed next to every figure derived from it.

*Why the record and not the file:* round 2's Daily Sales legitimately repeats two round-1 lines
inside a file that also carries nine new consignments. Suspending the file would block the new
work over two identical rows, and the operator would re-decide the same skips every week.

*What this catches:* `PaymentDetails_20260603-20260608_FarmersTrust.csv` is a **narrowed
re-export** (`Market,TSHWANE MARKET,,Agent,Farmers Trust (Pre)`) overlapping the full `.txt` for
the same date range. Its FMS IDs `203451`–`203453` collide with **different** records in the
round-1 CSV, so FMS ID is not a key either — the account sale number is.

## D13 — Suppliers and commission

The registers are **seeded with nothing**. Suppliers appear in no report; the agents see Zaco as
the supplier and know nothing about the farmers behind it, so a supplier exists because a person
entered one or it does not exist at all.

*Built in Phase 5* (`0005_settlement`): `suppliers`, `commission_terms` keyed on the consignment
because that is the delivery line, and `supplier_payments`. Until then this section described an
intention and read as though it described the code.

- **A consignment with no recorded commission produces no settlement at all** — never one
  computed at a default rate.
- Those consignments appear in an **"awaiting terms"** report with their cartons and nett shown,
  **never folded into a total**.
- Commission reporting **always states its coverage** alongside the figure.
- **Unsold stock creates no liability.** On consignment the supplier is paid on what sold;
  cartons that never moved cost the supplier, not Zaco.

## D14 — Accounts and permissions

Admin invites a **specific email address**. Every person gets their own account. Permissions are
granular per account: ingest rounds / resolve queue / append to workbook / record settlement
terms / view reports / admin. An allowed-email-domain rule gates **who may be invited** — it is
never an identity.

*Rejected:* a shared account keyed to an email domain. It would destroy the thing D12 exists to
provide: "chose the FarmersTrust export because X" is worth nothing if the record says a *domain*
decided. Every queue answer, DN approval, duplicate decision and append is stamped with a person.

---

## D15 — What "normally" means when judging an agent

Section 10 asks whether an agent has treated the money normally, and leaves "normally" to us.
Three choices, all of them about not manufacturing a finding out of a sample size.

**The normal is the whole business's, not each agent's own.** An agent measured against their own
history is their own yardstick, so one who has always kept too much looks perfectly typical --
which is the case most worth catching. The cost is that a record containing one agent lets that
agent define the normal, and the panel says so rather than pretending otherwise.

**It is a median.** On the supplied record the mean share kept is 17.4% against a median of 15.0%,
because the 60% on AccSale `382875` is already inside the mean. A yardstick partly made of the
outlier it is meant to expose is the wrong yardstick.

**A consignment still selling has not failed to sell.** One consignment of oranges last sold on
2026-06-05, the final day the record covers, with 120 of 200 cartons unsold -- four fifths of
everything its agent had not shifted. Counting those as produce that failed to move would say
something false about an agent whose fruit is simply still on the floor, so a consignment whose
last sale falls within two days of the end of the record is set aside, counted and named. On this
record that leaves Subtropico two finished consignments, below the threshold, so it is **not
judged** on what did not sell -- and the panel gives that as the reason rather than staying quiet,
because silence there reads as a pass.

*Rejected:* a threshold in percentage points. A business normally paying 5% and one normally
paying 30% cannot share a band measured in points. The threshold is relative -- half again as much
as normal -- so it travels with whatever the normal turns out to be.

*Rejected:* showing only the flagged lines. How ordinary the ordinary ones are is the entire basis
for the comparison, and a panel showing three lines out of eighteen gives the reader no way to see
it. The threshold governs emphasis, never visibility.

---

## Not yet answered

These are open. They are surfaced in the interface rather than guessed at, and this section is
updated as they are settled.

1. **Are deliveries `1183200Z`, `1183201Z` and `1183202Z` one load or three?** Pears, peaches and
   strawberries, delivered the same day, sold the same day, paid under one account sale. Only the
   operator knows whether one delivery note covered them. Until answered, the queue offers the
   multi-assign but does not presume it. **Still open.** Processing both rounds took each
   delivery's own supplier reference — `14885`, `14886`, `14887` — because each carries one, which
   is evidence where the one-truck reading is inference. If they were one load, the three rows are
   right and only column A is wrong, on three rows, recoverably.

2. **Does Zaco issue a DN for another producer's produce?** See D11. Currently asked per
   delivery.

3. **Is the `14xxx` DN series contiguous?** Still open, and Phase 3 chose the safe reading:
   minting goes **above everything known**, never into the gaps. A gap is at least as likely to
   be a delivery note written on paper and never entered as it is to be free, and reusing one
   would put two loads under one number in the book the business settles money against. With no
   workbook and no approved DN there is no series at all, and minting **refuses** rather than
   inventing `14000` — the queue asks for the number instead.

4. **What does `AGENT COMM % : 7.50` mean on the account sales statements?** No settlement in the
   data reconciles to 7.5%. Actual deductions run ~15% of gross, with outliers at 16.67%, 20.3%
   and one at 60% (AccSale 382875: R1,350 gross → R540 nett). Until this is understood, the §10
   conduct panel judges deductions against **this business's own observed normal**, not against
   the printed 7.5%, and says so.

5. **What market is `Destination` in the round-1 Daily Sales export?** The header for the
   Subtropico block reads `Destination` where the consignment report says `JOBURG MKT - TFRESH`.
   The market is recovered from a sibling report keyed on agent where one exists; where none
   does, the field is left empty and flagged rather than assumed.

---

## Settled while building Phase 3

**S1 — What the durable record actually stores.** A round is saved as the **documents
themselves**, byte for byte, and the deliveries, consignments and rows are re-derived from them
whenever the round is looked at. What the agent sent is the only thing that cannot be
recomputed; everything else is a consequence of it. A correction to a reader then improves the
whole history rather than leaving stale derived rows behind it, and a stored balance can never
drift from what the documents say while still adding up. Answers — codes, links, approved
delivery notes, settled disagreements — are stored, because those are the part no document
contains.

**S2 — Where captured product codes live.** In the database. `lookup/product-codes.json` is a
**seed**, read at boot and never written back: it is an input the operator supplied, and a system
that edits its own inputs leaves a trail nobody can follow. Where the two disagree the database
wins, and the full list is downloadable so the operator can update their own file if they want.

**S3 — Product identity is global; the questions are not.** Every product name any round has
contained is remembered, so the sales name and the statement name for one fruit can be offered as
a link even when they arrive weeks apart — the plums sell in one round and their statement lands
in the next. The **queue**, though, only ever asks about products in the round in front of it.
Blocking a round on a product that appears nowhere in it would be a queue nobody could clear.

**S4 — A link a document proved is written down.** Account sale 382405 names both
`CHERRIES OTHER CLASS 1 LARGE (HALF TRAY 2.5kg)` and `CHOT 1L HT25 CHERRY OTHER` for R400. That
statement is in one round only, and the cherries go on selling in the next. Re-deriving the proof
each round would mean the cherries losing their short code the moment the document that proved it
is no longer in front of us, so proven links are stored — marked as evidence rather than as
somebody's judgement, so the two are never confused.

**S5 — The overlap between rounds is real, and it double-counts.**
`DailySalesDetail_20260601-20260608.csv` **reprints, verbatim**, two nectarine dockets that
`DailySalesDetail_20260525-20260531.csv` already carried. Read as two independent rounds, the
book gains 65 cartons and R3,500 that never happened — and looks entirely normal doing it.
Deduplication within one round was not enough: the composite docket identity of D12 now holds
across the round boundary too, and every sale a resolved round counted is skipped, visibly, when
a later export prints it again.

**S6 — A statement and its payment record are one account sale.** The statement prints `382405`;
the payment side and every docket write `PRE*BT*382405`. Kept apart, one payment run became two
records and the second was reported as "paid but no sales document accounts for it" — a warning
about a state that is not real, which is worse than no warning at all. They are matched only when
**exactly one** payment reference ends with the statement's number: two agents could each close
an account sale numbered 382405, and quietly picking one would put a statement's nett against
another agent's sales.

---

## Things found in the data that `REQUIREMENTS.md` does not mention

Recorded here as they were found; expanded on in `NOTES.md`.

1. The live workbook has **23 columns, not 21** — `Buyer note` at C and `Packhouse` at V — and
   its data sheet is `Sheet1`, the **third** sheet. Every column letter in §5 is wrong for the
   real file, which is exactly why §5 says nothing may be located by position.
2. The statement field named `DELIVERY NOTE NO` is the agent's number, not Zaco's (D8).
3. Docket numbers are not unique (D12).
4. `lookup/product-codes.json` is keyed on the **account-sales** product vocabulary
   (`CHOT 1L HT25 CHERRY OTHER`) while nearly every row arrives with the **daily-sales**
   vocabulary (`CHERRIES OTHER CLASS 1 LARGE (HALF TRAY 2.5kg)`). Same fruit, two namespaces.
5. AccSale `382900` appears in **no other document** — two products, and a plums levy that must
   land only on the plum rows (`2781.50` / `942.50`, summing to exactly `3724.00`).
6. AccSale `382999` carries a gross and a nett and **no commodity lines at all**; the file also
   appears truncated mid-record.
7. Encoding and format hazards, all real: a BOM on one CSV; every line of another wrapped in an
   outer pair of quotes so the whole line is one field; U+00A0 and comma thousands separators
   **on the same line**; a `Total` row in the middle of a list; a date jammed against a reference
   (`JOH*SUB*5640001/12026-04-13`); three date formats plus `0000-00-00`.
8. `20026*14705 & 14706` — one payment against two references, proving DN↔delivery is
   one-to-many and cannot be derived even in principle.
9. **The two Daily Sales Detail exports overlap.** The June file reprints May's nectarine dockets
   unchanged (S5). Nothing in the brief suggests the exports are disjoint, and they are not.
10. The workbook's `Baby Stock` is `=I-K` in the live file — `Opening Stock` minus `Cartons Sold`
    — not the `=H-J` the brief's column letters imply. Another consequence of finding 1.
