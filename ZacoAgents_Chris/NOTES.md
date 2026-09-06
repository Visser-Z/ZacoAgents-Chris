# Notes

## What I built

A Python 3.12 / FastAPI service over Postgres, API-first, with a React interface over its own
`/api/*` endpoints, built into the image and served from the same origin. `docker compose up --build`, then <http://localhost:8000>;
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

On top of that record: a **reconciliation** board with five distinguishable states, a
largest-remainder **allocator** so a payment split across rows sums to the payment exactly, a
**settlement** view that refuses to produce a figure for a consignment with no agreed commission,
**reporting** over all time or a month or a week, and an **agent conduct** panel. The last three
all run over the accumulated record rather than one round, because an agent's normal and a
business's opening stock are exactly the things a single round is too small to establish.

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

**Every threshold, with its argument.** §9 and §13 both ask for these, so each is a named constant
sitting next to the reason for it rather than a number inside an expression.

- **The return rate is returned over cartons *sold*, not net.** If 100 sold and 20 came back, the
  share of sales that reversed is 20%, not the 25% that 20/80 gives. The denominator is printed
  beside the rate, because the two are different claims and a reader cannot tell them apart unaided.
- **Product bands are cumulative-value Pareto at 80% and 95%**, recomputed from the data every
  time rather than fixed at "top 5". **Under five lines nothing is banded at all**: three lines
  cannot have a vital few, and banding them dresses an arbitrary cut as a finding.
- **"What to take on" ranks on one ratio, not a blend** — money per carton *sent*, not per carton
  sold. Nothing is bought here, so what is scarce is the market slot and the handling spent on
  produce that then fails to move. One ratio traces to the figures beside it in a way a weighting
  of three signals does not. It switches to what Zaco actually earned the moment terms exist, and
  says which of the two it used.
- **Conduct is judged against the median of this business's own record, not the mean.** The mean
  share kept across the supplied rounds is 17.4% against a median of 15.0%, because AccSale
  382875's 60% is already inside the mean. A yardstick partly made of the outlier it is meant to
  expose is the wrong yardstick.
- **The normal is the whole business's, not each agent's own.** An agent measured against their own
  history is their own yardstick, so one who has always kept too much looks perfectly typical.
  Where the record holds one agent, that agent defines the normal and the panel says so.
- **A share kept is flagged at half again the normal**, relative rather than in percentage points:
  a business normally paying 5% and one paying 30% cannot share a band measured in points. On this
  record it flags 382875 alone. The two sales modestly above normal are keeping R5 and R13.70 more
  than normal on small sales, which a fixed handling charge explains.
- **Under five observations, nothing is judged**, and the panel gives that as the reason. §10 says
  not to judge on a sample too small to have a normal, and silence there would read as a pass.
- **A consignment that last sold within two days of the end of the record is treated as still
  selling** and set aside from "what never sold". One consignment of oranges last sold on the final
  day the record covers with 120 of 200 cartons unsold — four fifths of everything its agent had
  not shifted. Counting those as produce that failed to move says something false about fruit that
  is simply still on the floor.

The flagging threshold governs **emphasis, never visibility**: every account sale is listed either
way, because how ordinary the ordinary ones are is the entire basis for the comparison.

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
15. **A sale and its payment can land in different rounds.** `JOH*SUB*5644210/1` sells in round 1
    and is not accounted for by any payment document until round 2. At append time the honest
    answer for its Nett was "not known", so the cell was left blank with the reason recorded —
    and the row is now permanently blank in the book even though the record has since learned the
    figure. See *What I did not do*.
16. **No formula in the supplied book has a cached result** — not even the pre-existing rows. The
    file has never been opened and saved by Excel, so the formulas have never been calculated.

## What I did not do

**A row appended before its payment arrives is never revisited.** `JOH*SUB*5644210/1` sold in
round 1, so row 11 of the committed book has a blank `Nett Total`; its payment arrived in round 2
and the reconciliation board now shows it settled at R1,500 with a Nett of R1,275. Both halves are
correct on their own and nothing joins them. Not rewriting an appended row is deliberate — the
book is the operator's and the system's whole claim is that it does not disturb it — but the
missing piece is a screen that says *these appended rows have a blank the record can now fill*,
offering it as a fresh append rather than an edit. That is the first thing I would build next: it
is R1,275 the operator would otherwise have to notice by hand.

**Hosting.** The stack runs locally end to end, and `render.yaml` is being taken to Render now.
The one thing it could not have been right about until somebody tried it: this application is a
*subdirectory* of its repository, and Render resolves the Docker paths from the repository root
whatever `rootDir` says. See [docs/RUNNING.md](docs/RUNNING.md).

**A considered interface.** The pages are plain by choice — §12 says a plain one showing the right
figures beats a handsome one showing the wrong ones — but plain is not the same as designed, and I
would not claim the second. The React port replaced the server-rendered pages and fixed what was
plainly wrong rather than merely plain: the navigation never said which page you were on, `esc()`
was pasted into eight files, and eighteen `window.alert()` calls were the error strategy.

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
- **Six of the product short codes in column G are mine, not the operator's.**
  `lookup/product-codes.json` carries two; the rest — `Golden Del 12.5kg`, `Crimson Grapes 5kg`,
  `Valencia 15kg`, `Angelino 5kg`, `Star Ruby 15kg`, `Hass Avo 4kg`, `Packhams 12.5kg`,
  `Peaches 5kg`, `Strawberries 250g` — no supplied document contains, and the queue is right to
  block until someone gives them. I answered as the operator would have to. They follow the shape
  of the existing rows but deliberately drop their `Imp` prefix, which reads as *imported* and is
  a claim nothing in the data supports. Every one is a label, not a figure: none of them touches
  the money.
- **How the system actually suposed to look like** I should have done more reaserch on how this type of system looks, but was to earger to start working on it.
