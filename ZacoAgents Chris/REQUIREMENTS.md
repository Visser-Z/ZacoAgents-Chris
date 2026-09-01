# ZacoAgents

**Requirements.** What the system must do. It does not tell you how to do it, and
it does not tell you where the difficulties are. Both of those are the exercise.

No language, framework, storage or interface is prescribed.

---

## 1. The business

Zaco takes fresh produce from suppliers **on consignment**. It never buys stock.
The produce is placed with a market agent at a wholesale market, the agent sells
it off the floor over days, and the agent remits the money less its own
deductions. Zaco earns a commission percentage of what comes back and passes the
remainder to the supplier.

Zaco is not present when the fruit sells. The only account anyone gets of what
happened is the set of reports the agent sends back. Those reports are in
`data/`.

The operator has always transcribed those reports by hand into one Excel
workbook, which is the book the business runs on. That workbook is in
`workbook/`.

## 2. What to build

A system that:

1. Reads a round of agent reports.
2. Resolves the facts those reports do not carry.
3. Appends the result to the operator's existing workbook, without disturbing
   what is already in it.
4. Keeps a durable record of every row it appended.
5. Answers questions from that record: what sold, what came back, what was
   paid, what is owed, and whether the agent has treated the money normally.

Two framing rules, which are requirements rather than advice:

- **The workbook is a persistent target, not an output file.** Successive rounds
  append to the same sheet. The operator opens the workbook they already have
  and saves it back. Never generate a fresh workbook in place of theirs.
- **A missing fact is never invented.** Where the reports do not carry
  something, either capture it once from the operator and remember it, or report
  the gap. Do not fill the space with a default and let that default read as a
  figure. This one is load bearing and is assessed. See section 11.

## 3. Vocabulary

Four different numbers in these documents all look like an identifier and none
of them mean the same thing.

| Term | Definition |
|---|---|
| **Delivery** | One load of produce leaving Zaco for a market. |
| **DN** | Zaco's own delivery note number for that load. Column A of the workbook. **No report carries it.** |
| **Delivery ID** | The market's own number for the arrival. It is not the DN. |
| **Supplier Ref** | Written `producer*reference`. The reference half is sometimes the DN and often is not. |
| **Producer code** | The number before the asterisk. Zaco's own is `20026`. Produce carried for another producer arrives under theirs. |
| **Consignment** | One product within a delivery, sitting on the market floor until it clears. Has a Consignment ID. |
| **Docket** | One sale off the floor: a date, a quantity, a price and a value. |
| **Account sale** | A payment run the agent closes off, covering whatever sold in that period. Has an AccSale number. This is the workbook's **STM No**, column E, and is what the payment report pays against. |
| **Market agent** | Who sold the produce. **Market**: where. |
| **Gross** | What the fruit rang up on the floor. **Nett**: what reached Zaco after the agent's deductions. |

### The grain

**One workbook row is one combination of delivery, product and account sale.**

A consignment does not sell in one go. It sits on the floor and is sold off over
days, and every few days the agent closes an account sale covering whatever went
in that run. One consignment commonly spans several account sales, and one
account sale commonly settles several consignments.

Two consequences the implementation must respect everywhere:

- A consignment cannot be one row, because its stock position changes between
  account sales.
- Any quantity belonging to the **delivery** rather than to the account sale,
  such as what was sent or how long it took to clear, must be counted **once per
  consignment**, never once per row.

## 4. The source documents

Everything in `data/` is a report from a market agent. Five kinds are present.

| Kind | Carries | Does not carry |
|---|---|---|
| **Daily Sales Detail** | Every docket: what sold, when, at what price. In its richer form it also carries the delivery date, the date paid, and the account sale each docket was paid under. | The Nett. |
| **Consignment Reports** | The same sales information in a more limited form. | The account sale a docket was paid under, so it cannot tell one payment run from the next. Also no Nett. |
| **Account sales statement** | One statement, possibly covering several products, with the Nett at statement level and a printed table of deductions. | Anything about payment runs. |
| **Payment Details** | One record per account sale: nett, deductions, VAT and gross, plus each commodity line with what was delivered, what sold, and its sales total. | Anything about individual dockets or dates of sale. |
| **Nett Payment Adjustments** | One line per account sale, giving gross and nett only. | Any product or quantity. |

Requirements:

- **Identify each document by its content, not by its filename.** A document
  loaded into the wrong place must be refused with an explanation, not parsed
  into nonsense.
- The reports arrive **as they arrive**. They are exports from someone else's
  system and you do not control their shape, their encoding, or how carefully
  the person who ran them set the filters. Your reader has to survive that.
- A report states its own scope. If an export was narrowed to one market or one
  agent rather than run for everything, the system must say so, because the
  person who ran it usually believes they took the lot.
- The same report may be exported twice with overlapping date ranges. Recording
  the same thing twice is a defect.

## 5. The workbook

`workbook/account-sales-book.xlsx` is the operator's live book. Rows append
beneath what is already in it. `workbook/template.xlsx` is a blank one.

Twenty one columns. Eight of them hold formulas that belong to the operator.
**A computed value is never written into a formula column.** When a row is
appended, its formulas are written for the new row number.

| Col | Header | What goes in it | Kind |
|---|---|---|---|
| A | DN | Zaco's delivery note number. | written |
| B | Market Agent | Who sold it. | written |
| C | Completed | The literal `Incomplete` on append. | written |
| D | Date | The earliest date across every row sharing the same DN. | written |
| E | STM No | The account sale number. | written |
| F | Description | The operator's short code for the product. | written |
| G | Qty Received | What the delivery sent. | written |
| H | Opening Stock | See section 6. | written |
| I | Frui Price/crt | `=IFERROR(O{r}*70%,"-")` | **formula** |
| J | Cartons Sold | See section 6. | written |
| K | Baby Stock | `=H{r}-J{r}` | **formula** |
| L | Price | Priced so that `J*L` recovers the money. | written |
| M | Gross Total | `=SUM(J{r}*L{r})` | **formula** |
| N | Nett Total | From the payment side. | written |
| O | Nett Price/crt | `=IFERROR(N{r}/J{r},"-")` | **formula** |
| P | Z R/crt | `=IFERROR(O{r}-I{r},"-")` | **formula** |
| Q | Z Total | `=N{r}-S{r}` | **formula** |
| R | % Markup | `=IFERROR(P{r}/O{r},"-")` | **formula** |
| S | Frui Curr Sales Value | `=I{r}*J{r}` | **formula** |
| T | Status | The account sale's own date, as `DD.MM`. | written |
| U | NOTES | The operator's own margin. | **never written** |

Number formats on appended rows must match the existing sheet.

### Column I

Column I is the price per carton that is **not** Zaco's, written as the seventy
percent default. It is a formula in a cell rather than a value computed behind
the operator, so a row on different terms is corrected by typing the agreed per
carton price over it and everything downstream follows.

Note this is not the same thing as settlement (section 8), which must refuse to
compute what a supplier is owed at a default rate. A default in a spreadsheet
cell is a visible, editable suggestion. A default in a payable is a fabrication.

### Handling the file

- **Nothing may be located by position.** Real workbooks do not match the
  template: the data sheet may not be first, and columns get reordered,
  inserted or renamed. Locate the sheet and every column by header text.
- **Rows are appended, never rebuilt.**
- **Cell values are read leniently.** A surprise value in a numeric column must
  not crash the read.
- **Column U is read back and written back unchanged.** Nothing derives it and
  nothing may overwrite it.
- A file with no recognisable data sheet is rejected with an explanation.

## 6. What the figures must mean

### Returns

A docket with a negative quantity is a **return**: fruit back on the floor,
reversing a sale already booked.

- The workbook columns stay **net**, because column J feeds `K = H - J` and the
  stock only balances if what came back is taken off the sold figure. Column L
  must be priced over that same net.
- The sale and the return both happened. Keep both as their own figures, held
  positive, so that a month which sold a lot and had some come back can be told
  apart from one that quietly sold less.
- **Absent is not zero.** Where a source could not report returns at all, the
  figure is absent. Zero means the report showed it and nothing came back.

### Opening stock

A **running balance per consignment**, not a figure taken from one file. The
first row opens at what was sent. Each later row opens at what the row before it
left behind.

A consignment does not respect the boundary of an export. It may begin selling
in one round and continue in the next. Its stock position must be right in both.

A consignment that cannot be identified cannot be tracked, and its rows must be
left alone rather than pooled with unrelated ones.

Where a row sold more than was on the floor, say so. Do not correct it. This
happens in the real book too.

### Splitting one Nett across products

An account sales statement prints a single Nett for a statement that may cover
several products. Recreate each row's share from the statement's **own printed
deductions table**. Do not derive rates of your own; split the printed totals.

- A deduction that applies generally spreads across the rows it covers, in
  proportion to each row's value.
- **A deduction named for a fruit lands only on the rows for that fruit.**
  Splitting a plum levy proportionally puts part of it on the grapes.
- The shares must sum to the printed Nett **exactly**, to the cent.
- If the printed deductions cannot be reconciled to the printed Nett, do not
  produce a figure. Say so instead.
- Nothing is apportioned silently. An apportioned figure is marked as one and
  stays editable.

### Which money figure

**Value is gross**, cartons sold times unit price, because the sales reports
leave the Nett blank and it arrives only from the payment side.

Gross is never substituted for Nett in settlement. The gross is the market's
sale value, not Zaco's money, and settling a supplier on it would pay away the
agent's commission as well as Zaco's own.

### Which name a product is counted under

Everything that groups by product must group by the same thing, so that a
ranking, a recommendation and a signal shown next to a row all agree. The
operator's short code is assigned by hand and belongs to the Excel column; it is
not always present.

## 7. Resolving what the reports do not carry

Four things must be filled in before a row can be written.

**The product short code.** The mapping from a raw product name to the
operator's code cannot be derived from the reports. `lookup/product-codes.json`
holds what is known so far and is deliberately far from complete. Unresolved
products are put to the operator, and the answer is remembered.

**The delivery note number.** Column A is Zaco's own DN and no report carries
it. One DN can cover several market deliveries, so it cannot be derived even in
principle. It must be captured once per delivery and reused. There is, however,
information already in the operator's workbook that can recover part of the
mapping without anyone typing anything; finding it is part of the exercise.

Where there is **positive evidence** that a reference is not a delivery note,
say so on that row. Only on positive evidence. A warning on every row is a
warning nobody reads by the second week, so a build that flags indiscriminately
is worse than one that flags nothing.

**The grouping date**, column D, which depends on the whole batch rather than on
one row.

**Opening stock**, per section 6.

## 8. Payments, reconciliation and settlement

### Reconciliation

Accumulated sales are reconciled against the payment reports, which is how the
Nett arrives. Where the sales side names the account sale a docket was paid
under, that is an exact join and must be used in preference to matching on
anything softer.

Report, per account sale, what the sales side says was sold under it against
what the payment side says was paid for it, and whether those agree. Agreement
is to the cent, within R0.01.

The states that must be distinguishable: fully reconciled; sold but not yet in
any payment run; paid with no sales behind it; and the two ways the two sides
can disagree.

Where an account sale carries a gross and a nett but no commodity breakdown at
all, it can never reconcile. Report it rather than letting its money vanish.

### Filling the Nett

An account sale settles several rows at once, so its Nett is split between them
**by sales value**. A row that names more than one account sale receives the sum
of its share of each.

**The shares must add up to the payment exactly.** Rounding each share to the
cent will not do that on its own.

Only fully matched groups are filled. A partially sold group would otherwise
receive a Nett for produce not all paid for yet.

### Settlement

```
market buyer pays
  -> agent deducts commission, levies and VAT      (payment report)
    -> NETT lands with Zaco                        (payment report)
      -> Zaco keeps its agreed percentage          (recorded by this system)
        -> the remainder is owed to the supplier   (computed by this system)
```

Everything above the Nett line the reports state. Everything below it exists
only in this system: the agents see Zaco as the supplier and know nothing about
the farmers behind it. Suppliers appear in no report and must be recorded.

Terms are agreed per delivery line, as a percentage of the Nett.

Two requirements that are easy to get wrong:

- **A consignment with no recorded commission produces no settlement at all**,
  rather than one computed at a default rate.
- **Unsold stock creates no liability.** On consignment the supplier is paid on
  what sold. Cartons that never moved cost the supplier, not Zaco. This is the
  opposite of a buy and resell business.

Report per supplier what they earned, are owed, have been paid, and how many
cartons they handed over that never sold. What was handed over belongs to the
delivery.

Consignments the system cannot speak for, whether awaiting terms or awaiting
payment, are reported separately rather than folded into a total.

## 9. Reporting

Over the recorded history, scoped to all time, a month, or a week.

**Headline figures.** Cartons and takings. Report what sold, what came back and
the net, and a return rate. Be careful what the rate is a share of.

**Rankings.** Products by value, banded so the vital few are distinguishable
from the long tail. Totals by market and by agent.

**Per product.** What a carton fetched, how much of what was sent actually sold,
and how long it took to move. Sell through and time on market belong to the
delivery, not to the account sale.

**Commission**, over the consignments with agreed terms. State the coverage
alongside the figure. Commission over a fifth of the business is a useful number
only if you know it is a fifth.

**What to take on.** A ranked view of which lines are worth accepting from
suppliers again. There is no budget in this: nothing is bought, and what is
scarce is market slots, handling and supplier relationships spent on produce
that then fails to move. Until a commission is agreed, you are ranking on
proxies for what Zaco will earn; once terms exist you can rank on what it
actually earned. Say which of the two a given result used.

The signals, the weighting and the banding are yours to choose and to justify.
The requirement is that the result is **computed and reproducible**: the same
history in gives the same answer out, and every score traces to the figures
shown beside it. Real money is settled off the back of this.

## 10. Has the agent treated the money normally

Zaco is not on the floor. The only leverage is what the reports say, so be exact
about which questions they can answer.

**Answerable from the reports:** how much of the sale the agent kept, and how
much of what was sent never sold. Judge the first against what this business
itself normally pays rather than against an outside benchmark, so it stays
meaningful if the agent's terms change. Do not judge either on a sample too
small to have a normal.

**Not answerable from the reports:** whether the price recorded is the price the
fruit actually made. Look at the data before deciding whether you agree.

If you conclude something is not answerable, **that conclusion must travel with
the figures**, not sit in a comment. A panel that only ever reports what it can
check reads as a clean bill of health on the thing it is blind to.

Anything flagged carries the figures that raised it. None of it is an
accusation; a high deduction has innocent explanations.

## 11. Judgment

Several requirements above are of the form "do not produce a figure you cannot
stand behind". They are deliberate and they are the part of this exercise most
often failed, because an empty field looks like an unfinished feature and a
plausible number looks like a working one.

Where you decide the honest answer is "not known", make that visible in the
output rather than in the code. Where you decide to produce a figure that rests
on an assumption, say so next to it and let the operator overrule it.

You will find more of these than are listed here. Finding them is the exercise.

## 12. Not required

- Buying, purchasing or stock valuation. Nothing is bought.
- Moving money. Settlement is recorded and reported, not executed.
- Authentication beyond whatever your storage choice implies.
- A polished interface. A plain one that shows the right figures beats a
  handsome one that shows the wrong ones.
- Handling report formats other than the five described.

## 13. What is assessed

In roughly this order:

1. **The data model.** Whether the grain is right, and whether figures that
   belong to a delivery are counted once.
2. **Robustness of the readers.** Whether they survive the documents as
   supplied, and whether they fail loudly rather than quietly when they cannot.
3. **Correctness of the money.** To the cent.
4. **Judgment.** Whether the system refuses to state what it does not know, and
   whether it says so in a way the operator would actually notice.
5. **The workbook.** Whether the operator's file survives contact with it.
6. **Reasoning.** A short written note on the calls you made and why. Where you
   chose thresholds or weights, say what they are and why. Where you found
   something in the data that this document does not mention, say so; that is
   worth more than any feature.
