# Notes

## What I built

A Python 3.12 / FastAPI service over Postgres, API-first, with a thin Jinja + HTMX interface over
its own `/api/*` endpoints. `docker compose up --build`, then <http://localhost:8000>;
[docs/RUNNING.md](docs/RUNNING.md) has the detail and [docs/DECISIONS.md](docs/DECISIONS.md) has
every call with what was rejected and why.

It reads a round of agent reports, resolves what the reports do not carry, and appends to the
operator's live book. Five readers plus a classifier that is never shown the filename; the
delivery → consignment → docket model, with the workbook row as *(delivery, product, account
sale)*; a **blocking** resolution queue; and an append that locates the sheet and every column by
header text, writes the eight formula columns as formulas built from the letters resolved in
*that* file, and takes a snapshot as a step inside the transaction so a failure rolls the file and
the record back together.

A round is stored as **the documents themselves**; deliveries, rows and balances are re-derived on
every read. What the agent sent is the only thing that cannot be recomputed, so a correction to a
reader improves the whole history rather than leaving stale rows behind it. The answers are
stored — short codes, product links, approved delivery notes, settled disagreements — because
those are the part no document contains, and each carries the person who gave it.

Money is `Decimal` end to end, `NUMERIC(14,2)` in Postgres, and crosses the wire as a **string** so
no client can turn it into a float.

## Calls I made, and why

**The DN is never taken from the agent's `DELIVERY NOTE NO` field.** That field is in the agent's
`203xxx` series — the same series as the payment reports' FMS IDs. Zaco's are `14xxx`. Reading it
into column A produces a book that looks complete and is wrong in every row. Instead: reuse a DN
the workbook already links, else propose the supplier ref's reference half if it passes three
tests (in range, **and** not a known producer code, **and** not equal to its own producer half),
else mint the next free number. Every proposal needs explicit approval, and the queue can assign
one DN to several deliveries — `1183200Z`/`1183201Z`/`1183202Z` share a delivery date, a sale date
and one account sale, and are very plausibly one truck.

**Minting goes above everything known, never into the gaps.** A gap is at least as likely to be a
note written on paper and never entered as it is to be free, and reusing one puts two loads under
one number. With no workbook and no approved DN there is no series at all, and minting **refuses**
rather than inventing `14000`.

**A row is flagged "this reference is provably not a delivery note" only on positive evidence** —
2 of 11 deliveries here. §7 is explicit that a warning on every row is a warning nobody reads by
the second week. A *blank* supplier ref is absence, not evidence, and is not flagged; it still
ends up minted, and the queue says which reason applied.

**Docket identity is composite** — consignment + docket number + date sold + quantity + payment
reference. Docket numbers repeat legitimately: `PRE*B6E01C39001*06Z` appears in both rounds for
one consignment with different dates and account sales, and deduping on the number alone silently
deletes a real R900 sale. Identical duplicates are skipped with a **visible alert**, never a log
line. Any figure differing suspends **that record**, not the file, shows both sources, and demands
a typed reason.

**The queue blocks.** Nothing is appended until every question is answered. Appending rows with
gaps to fill later leaves a half-written row in the live book.

**No commission means no settlement**, never one at a default rate. Column I's 70% is a different
thing: a visible, editable suggestion in a spreadsheet cell. A default in a payable is a
fabrication.

I have **not** yet chosen any threshold, weight or banding, because §9 and §10 are not built. Where
the system would need one today it refuses instead.

## What I found in the data

1. **The live book has 23 columns, not 21**, with `Buyer note` at C and `Packhouse` at V, and its
   data is on `Sheet1`, the *third* sheet. Every column letter in §5 is wrong for the real file —
   `Baby Stock` is `=I{r}-K{r}`, not `=H{r}-J{r}`. This is precisely why §5 forbids position.
2. **The two Daily Sales exports overlap.** The June file reprints May's nectarine dockets
   verbatim. Read as independent rounds the book gains 65 cartons and R3,500 that never happened,
   and looks entirely normal doing it.
3. **`lookup/product-codes.json` is keyed on the account-sales vocabulary**
   (`CHOT 1L HT25 CHERRY OTHER`) while nearly every row arrives in the daily-sales vocabulary
   (`CHERRIES OTHER CLASS 1 LARGE (HALF TRAY 2.5kg)`). Same fruit, two namespaces.
4. **`STM No = 0` is the operator's own "not paid yet" marker** (row 3 of the book), and a docket
   carries `PRE*BT*0` with `0000-00-00`. `0` is never written.
5. **`5640001/1` and `5640001/2` are two separate April runs**, R5,100 and R3,230. Dropping the
   `/n` suffix to make it look numeric merges R8,330 into one statement.
6. **`20026*14705 & 14706`** — one payment against two references, proving DN↔delivery is
   one-to-many and cannot be derived even in principle.
7. **AccSale 382900 appears in no other document**, and its plums levy must land only on the plum
   rows: `3000 − 172.50 − 46 = 2781.50` and `1000 − 57.50 = 942.50`, summing to exactly `3724.00`.
8. **AccSale 382999 carries a gross and a nett and no commodity lines at all**, in a file that also
   appears truncated mid-record. It can never reconcile and must be reported, not lost.
9. **AccSale 382875: R1,350 gross → R540 nett — the agent kept 60%.** Everything else runs ~15%.
   The statements separately print `AGENT COMM % : 7.50`, which reconciles with nothing.
10. **`PaymentDetails_20260603-20260608_FarmersTrust.csv` is a narrowed re-export** of the same
    dates, and its FMS IDs collide with *different* records — so FMS ID is not a key either.
11. **Format hazards, all real:** a BOM; every line of one CSV wrapped in an outer pair of quotes;
 U+00A0 and comma thousands separators on the same line; a `Total` row mid-list; a date jammed
    onto a reference (`JOH*SUB*5640001/12026-04-13`); three date formats plus `0000-00-00`.
12. **`14xxx` is not exclusively DN space** — `14013` is a producer code and is also five digits
    starting `14`. That is why the ref-half test has three conditions.
13. **A bug in the supplied data's Nett Payment Adjustments, found late.** The file uses two shapes
    on one page — `JOH*SUB*5640001/12026-04-13` jammed and `PRE*BT*380101 2026-04-01` spaced. Only
    the first was handled, leaving real payments in the system with nothing to join on.
14. **`openpyxl` converts a `Decimal` to a float on the way into the file.** 400 ÷ 3 was stored as
    `133.33333333333331`. Prices are rounded to the five decimals the column already displays, and
    a row whose money no longer divides says so.
15. **No formula in the supplied book has a cached result** — not even the pre-existing rows. The
    file has never been opened and saved by Excel, so the formulas have never been calculated.

## What I did not do

**§8 reconciliation, the Nett split and settlement; §9 reporting; §10 agent conduct.** They are
designed, not built. The consequence is visible rather than hidden: where an account sale settles
one row the Nett is written, and where it covers several the cell is **blank** and the grid says
`SPLIT ACROSS N ROWS`, because apportioning it must sum to the payment exactly and that is §8's
job. I would build that next — the largest-remainder allocator and the printed-deductions split
are where the money stops being merely parsed and starts being owed.

Also not done: hosting (the stack runs locally end to end; `render.yaml` is written, unexercised).

## What I am unsure of

- **Every minted delivery note.** A DN presumably exists on paper that left with the truck. Approval
  makes it a decision rather than a fabrication, and the system records which numbers it minted, but
  I would not settle against one without checking the physical note.
- **Whether `1183200Z`/`1183201Z`/`1183202Z` are one load or three.** Only the operator knows.
- **What `AGENT COMM % : 7.50` means.** Until it is understood, conduct must be judged against this
  business's own observed normal, not the printed figure.
- **Any figure derived from AccSale 382999**, whose file appears truncated.
- **The market for the Subtropico block in round 1**, where the header reads `Destination`. It is
  recovered from a sibling report keyed on agent where one exists, and left empty and flagged
  where none does.
- **How the system actually suposed to look like** I should have done more reaserch on how this type of system looks, but was to earger to start working on it.
