# ZacoAgents

**Functional specification.** This document describes a system to be built. It states
what the system must do and the rules it must obey. It does not prescribe a language,
a framework, a database or a deployment. Those are the implementer's choice.

Read the vocabulary section before anything else. Most of the difficulty in this
domain is that four different numbers all look like an identifier and none of them
mean the same thing.

---

## 1. The business

Zaco takes fresh produce from suppliers **on consignment**. It never buys stock. The
produce is placed with a market agent at a wholesale market, the agent sells it off
the floor over days, and the agent remits the money less its own deductions. Zaco
earns a commission percentage of what comes back and passes the remainder to the
supplier.

Zaco is not present when the fruit sells. The only account anyone gets of what
happened is the set of reports the agent sends back.

The operator has always transcribed those reports by hand into one Excel workbook,
which is the book the business actually runs on.

### What the system must do

Read a round of reports, resolve the facts the reports do not carry, append rows to
the operator's existing workbook without disturbing the formulas already in it, and
record the same rows to a durable history that everything else answers from.

### Two framing rules

1. **The workbook is a persistent target, not an output file.** Successive rounds of
   reports append to the same sheet. The operator opens the workbook they already
   have and saves it back. The system never generates a fresh workbook from scratch
   in place of theirs.

2. **A missing fact is never invented.** Where the reports do not carry something,
   the system either asks for it once and remembers the answer, or reports the gap.
   It does not fill the space with a default and let that default read as a figure.
   Section 13 lists every place this rule bites.

### Out of scope

- Buying stock. There is no cost of goods, no spend to net off, no budget to divide.
- Paying anyone. Settlement is recorded and reported. Money moves outside the system.
- Judging whether a price was fair. See section 11 for why this is a boundary and
  not an omission.
- Anything the reports do not print and the operator has not entered. There is no
  second source.

---

## 2. Vocabulary

| Term | Definition |
|---|---|
| **Delivery** | One load of produce leaving Zaco for a market. |
| **DN** | Zaco's own delivery note number for that load. Column A of the workbook. **No export carries it.** |
| **Delivery ID** | The market's own number for the arrival, e.g. `1181705Z`. Not the DN. |
| **Supplier Ref** | Written `producer*reference`, e.g. `20026*14847`. The reference half is sometimes the DN and often is not. |
| **Producer code** | The number before the asterisk. Zaco's is `20026`. Produce carried for another producer arrives under theirs, so the prefix must not be assumed. |
| **Consignment** | One product within a delivery, sitting on the market floor until it clears. Identified by a Consignment ID, e.g. `118170501Z`. |
| **Docket** | One sale off the floor: a date, a quantity, a price and a value. A docket with a **negative quantity is a return**, reversing a sale already booked. |
| **Account sale** | A payment run the agent closes off, covering whatever sold in that period. Identified by an AccSale number, e.g. `PRE*BT*387517`. This is the workbook's **STM No** (column E) and is what the payment report pays against. |
| **Market agent** | Who sold the produce, e.g. Farmers Trust, Subtropico. |
| **Market** | Where it was sold, e.g. Tshwane Market, Joburg Market. |
| **Gross** | What the fruit rang up on the floor. |
| **Nett** | What reached Zaco after the agent's commission, levies and VAT. |

### The grain

**One workbook row is one combination of delivery, product and account sale.**

A consignment does not sell in one go. It sits on the floor and is sold off over
days, and every few days the agent closes an account sale covering whatever went in
that run. One consignment therefore commonly spans two to five account sales.
Measured across one June of real data, 43 of 81 consignments spanned exactly one and
the rest spanned up to five.

Two consequences that the implementation must respect everywhere:

- A consignment cannot be one row, because its stock position changes between
  account sales.
- Any quantity belonging to the **delivery** rather than to the account sale (what
  was sent, how long it took to clear) must be counted **once per consignment**,
  never once per row. Several rows of one consignment all repeat the same Qty Sent.
  Summing that column over an account sale split trebles what was sent. On real June
  data that turns 4 487 cartons sent into 13 060 and reports 76% unsold instead of
  30%.

---

## 3. Input formats

Five document formats must be recognised. **Detection is by content, never by
filename.** A document loaded into the wrong place is refused with an explanation
rather than parsed into nonsense.

| Format | Carries | Cannot say |
|---|---|---|
| **Daily Sales Detail (CSV)** | Every docket, with delivery date, date paid, and the account sale each docket was paid under. | The Nett. Sales record only. |
| **Daily Sales Detail (PDF)** | The same dockets, as a picture of a table. | The account sale a docket was paid under, so it cannot split a consignment into payment runs. Also no Nett. |
| **Account sales statement (PDF)** | One statement, possibly several products, with the Nett at statement level and a printed deductions table. | Anything about payment runs. |
| **Payment Details (CSV or PDF)** | One record per account sale: Nett, deductions, VAT, gross, plus each commodity line with delivered, sold and sales total. | Anything about individual dockets or dates of sale. |
| **Nett Payment Adjustments (PDF)** | One line per account sale: gross and nett only. | Any product or quantity at all. Purely financial. |

**The CSV is preferred wherever there is a choice.** A PDF is a picture of a table,
so every value has to be recovered from whitespace and column positions, which is
the source of every layout defect. The CSV is the table. It also names the account
sale on every docket, which is a direct join between a sale and its payment.

### 3.1 Daily Sales Detail, PDF

Detected when at least two of these appear: `Daily Sales Detail`,
`Consignment Reports`, `Delivery ID:`.

One consignment block looks like this:

```
TSHWANE MARKET      Farmers Trust (Pre)
Delivery ID: 1181705Z Supplier Ref:  Qty Sent: 71 Qty Amended To: Qty Avail: 70
Consignment ID: 118170501Z Comment:
Product:  NECTARINES OTHER CLASS 1 MEDIUM MULTI LAYER TRAYER 11kg
  Date Sold  Docket Number Qty Sold Market Avg   Price     Sales Value
2026-07-27 PRE*B6G27S89670*01Z  1        R 0.00       R 50.00   R 50.00
                                1                               R 50.00
```

The last line is the block's own subtotal and is not a docket.

Parsing notes:

- The document splits into one block per `Delivery ID:` line.
- The market and agent line (`MARKET  Agent (Region)`) sits above the Delivery ID
  line. **One report can carry several agents**, so the agent belongs to the row and
  not to the file. Take the nearest such line above the block.
- Delivery and Consignment IDs carry a trailing letter. Keep the digits only.
- Supplier Ref is often blank on older exports.
- The Product line runs to end of line, and on some exports a neighbouring column
  bleeds a bare number onto it, e.g.
  `GRAPES STARLIGHT CLASS 2 NO SIZE (PUNNET 5kg) 10`. Strip a trailing bare number
  **only when it follows a closing bracket**. Left in, the same product reads as two
  different products, splitting its totals and stopping it matching the payment
  report. No genuine product name ends in a bare number.

### 3.2 Daily Sales Detail, CSV

Detected when the first 800 characters contain `date sold`, `docket number` and
`sales value`.

```
"Delivery Date","Date Sold","Date Paid","Docket Number","Payment Reference","Qty Sold","Market Avg",Price,"Sales Value"
"TSHWANE MARKET","Farmers Trust (Pre)"
"Delivery ID : ",1180699Z,"Supplier Ref : ",20026*14799,"Qty Sent : ",14,"Qty Amended To : ",
"Consignment ID :",118069901Z
"Product :","CHERRIES OTHER CLASS 1 LARGE (HALF TRAY 2.5kg)"
2026-05-27,2026-05-27,2026-05-29,PRE*B6E27C39125*01Z,PRE*BT*382405,3,0.00,200.00,600.00
2026-05-27,2026-05-28,2026-05-29,PRE*06E28B40280*01Z,PRE*BT*382405,-1,0.00,200.00,-200.00
2026-05-27,2026-05-29,2026-06-01,PRE*B6E29BT2574*01Z,PRE*BT*382860,1,0.00,200.00,200.00
" "," "," "," "," ",3,,200.00,600
```

Two things that will break a naive reader:

- **Most real exports are double encoded.** The whole line sits inside one quoted
  field with every inner quote doubled, so a nine column data row reads back as a
  single cell. A standard CSV reader is right to do that, and every parser
  downstream then matches nothing and reports **zero rows rather than an error**. In
  a sample of 14 real weekly files, 11 parsed as empty. A row that comes back as one
  cell containing commas must be re-read as CSV to recover its columns. A genuine
  one column row has no commas and passes through untouched.
- **Rows that are totals or repeated headers are not data.** Skip them explicitly by
  what they say (`total sales`, `daily total`, `grand total`, a lone `Line No`, a
  lone `Delivery Date`), never by position. An extra blank line must not shift the
  parse.

A docket awaiting payment carries a **placeholder** reference, not a blank one: the
real export writes `PRE*BT*0` with a Date Paid of `0000-00-00`. Taken literally,
every unpaid consignment across every delivery pools under one imaginary account
sale. Recognise it by having no statement number in it, so any other placeholder the
export invents is caught the same way.

### 3.3 Account sales statement, PDF

The older format. Values sit next to stable labels even though their positions
shift, so match on labels rather than coordinates.

Labels: `REFNO`, `ACCOUNT SALES NO`, `DATE`, `DATE RECEIVED`, `PRODUCT`,
`QUANTITY RECEIVED`, `QUANTITY B/F`, `NETT AMOUNT`, `GROSS AMOUNT`,
`** TOTAL SOLD **`, and a price breakdown table whose `QUANTITY` total is the
cartons sold.

Traps:

- `ACCOUNT SALES NO` must not match `PREVIOUS ACCOUNT SALES NO`.
- `DATE :` must not match `DATE RECEIVED :`.
- There are three different `QUANTITY` labels. Cartons sold is the price table
  total, not `QUANTITY RECEIVED` and not `QUANTITY B/F`.
- `** TOTAL SOLD **` is the current statement's figure. A separate cumulative
  `TOTAL SOLD :` appears further down and is not it.

**One statement can hold several products.** Each product section opens with its own
`MARKET GRN :` line carrying its own quantities, product and price table, and a
section's price table can continue across a page break. Each section becomes one row
sharing the statement's identifiers and dates. `NETT AMOUNT` exists only at
statement level, so see section 8.3 for how it is split.

### 3.4 Payment Details

Detected when the first 800 characters contain `acc sales number` and
`gross payments`.

```
"FMS ID","Supplier Ref","Acc Sales Number",Date,"Nett Payment","Total Deductions","Deduction VAT","Gross Payments","Payment Ref"
Market,"TSHWANE MARKET",,Agent,"Farmers Trust (Pre)"

203464,20026*14585,PRE*BT*392828,2026-08-05,2304.40,361.35,54.25,2720.00,

,,,"Line No","Supplier Ref",Commodity,Delivered,Sold,"Sales Total"
,,,02,20026*14585,"NECTARINES OTHER CLASS 1 LARGE MULTI LAYER TRAYER 5.00 kg",43,10,2720.00
```

**The export states its own scope**, in one of two shapes:

```
Market,"TSHWANE MARKET",,Agent,"Farmers Trust (Pre)"
Destination,"Subtropico (Jhb)"
```

The second names only the agent, so the market stays unknown rather than being
guessed. An unfiltered export says `ALL`. Anything else means whole markets or
agents were left out and the file cannot be trusted as a complete picture, which is
worth saying out loud because the person who ran the export usually believes they
took everything.

The header is **not** always unique. One weekly export can hold several sections one
after another, each with its own header. Reading only the first would report such a
file as narrowed to one agent while half its money belonged to another. Scan the
whole file and count it as narrowed only when it declares a single specific scope
throughout.

Some account sales carry a gross and a nett with **no commodity lines at all**.
See section 9.4.

### 3.5 Nett Payment Adjustments, PDF

Detected when at least two of `Nett Payment Adjustments`, `AccSale Number`,
`Nett Payments`, `Supplier Ref` appear.

```
20026*14847 PRE*BT*387517 2026-07-01 R 2 700.00 R 401.72 R 60.27 R 2 238.01
20026*14565 & 14980 JOH*SUB*5644102/12026-07-13 R 6 000.00 R 771.56 ...
```

Columns are Supplier Ref, AccSale Number, Date, Gross, Total Deductions, Deduction
VAT, Nett.

Two traps:

- The second market's AccSale carries an adjustment sequence (`/1`) and is printed
  **glued to the date** with no separating space: `5644102/12026-07-13`.
- One account sale can appear on several adjustment lines (`/1`, `/2`), so its true
  Nett and Gross are the **sum** across those lines.

### 3.6 Identifier conversions

| From | To | Rule |
|---|---|---|
| `PRE*BT*387517` | `387517` | Digits of the last `*` segment, dropping any `/n` sequence. |
| `JOH*SUB*5644102/1` | `5644102` | Same rule. |
| `20026*14847` | DN `14847` | First number after the `*`. |
| `20026*14565 & 14980` | DN `14565` | Combined refs keep the first. |
| `20026*14847` | producer `20026` | The number before the `*`. |
| `1181705Z` | `1181705` | Digits only. |

---

## 4. The workbook

One sheet, twenty one columns, one row per account sale per product. Eight columns
hold formulas that belong to the operator. **A computed value is never written into
a formula column.** When a row is appended, its formulas are rewritten for the new
row number.

| Col | Header | Source or rule | Kind |
|---|---|---|---|
| A | DN | Zaco's delivery note number. Captured, never derived. | written |
| B | Market Agent | From the report header. Per row, not per file. | written |
| C | Completed | Literal `Incomplete` on append. | written |
| D | Date | Earliest date across every row sharing the same DN. | written |
| E | STM No | The account sale number. | written |
| F | Description | The operator's short code for the product. | written |
| G | Qty Received | What the delivery sent. Same on every row of the consignment. | written |
| H | Opening Stock | Running balance. See 8.2. | written |
| I | Frui Price/crt | `=IFERROR(O{r}*70%,"-")` | **formula** |
| J | Cartons Sold | Net of returns. See 8.1. | written |
| K | Baby Stock | `=H{r}-J{r}` | **formula** |
| L | Price | Sales value divided by cartons sold. | written |
| M | Gross Total | `=SUM(J{r}*L{r})` | **formula** |
| N | Nett Total | From the payment side. Empty with a warning where none has landed. | written |
| O | Nett Price/crt | `=IFERROR(N{r}/J{r},"-")` | **formula** |
| P | Z R/crt | `=IFERROR(O{r}-I{r},"-")` | **formula** |
| Q | Z Total | `=N{r}-S{r}` | **formula** |
| R | % Markup | `=IFERROR(P{r}/O{r},"-")` | **formula** |
| S | Frui Curr Sales Value | `=I{r}*J{r}` | **formula** |
| T | Status | The account sale's own date as `DD.MM`. | written |
| U | NOTES | The operator's own margin. | **never written** |

Number formats applied to appended rows so they match the existing sheet:

```
D  d-mmm          I  #,##0.00      N  #,##0.00      R  0%
G  #,##0          J  #,##0         O  #,##0.00      S  #,##0.00
H  #,##0          K  #,##0         P  #,##0.00
L  #,##0.00000    M  #,##0.00      Q  #,##0.00
```

### 4.1 The chain hangs on column I

Column I is the price per carton that is **not** Zaco's, written as the seventy
percent default. Because it is a formula in a cell rather than a value computed
behind the operator, a row on different terms is corrected by typing the agreed per
carton price over it, and everything downstream follows.

That is how the historical book is kept: 268 of 339 rows sit at exactly thirty
percent, and the rest carry a hand entered figure in I.

Note the deliberate difference from settlement (section 10), which **refuses** to
compute what a supplier is owed at a default rate. A default in a spreadsheet cell
is a visible, editable suggestion. A default in a payable is a fabrication. Both
behaviours are correct and they are not in conflict.

### 4.2 How the file is handled

- **Nothing is located by position.** The data sheet and every column are found by
  their header text, matched on a normalised form (case, spacing and punctuation
  removed). Real workbooks do not match the template: the data sheet may not be
  first, and columns get reordered or inserted.
- A row counts as the header row when it matches at least **6** of the template
  headers, scanning the first **10** rows of a sheet. High enough that a lone
  `Date` or `Price` in some unrelated sheet never wins. Columns **A** and **E** are
  required; without them the file is rejected as unrecognised.
- **Cell values are coerced leniently.** A surprise string in a numeric column reads
  as empty, never as a crash.
- **Rows are appended, never rebuilt.** New rows go beneath what is already there,
  ordered by DN (blanks last), then product, then settlement order, then account
  sale.
- **Formulas are rewritten against the workbook's actual layout**, so a sheet whose
  columns sit in different positions receives formulas pointing at the right cells.
- **Column U is read back and written back unchanged.** Nothing derives it and
  nothing may overwrite it.

### 4.3 The pivot sheet

A native Excel pivot table is rebuilt on its own sheet on every export, so it always
covers the full data range including rows just appended.

**Its cache is deliberately left empty and marked stale**, with refresh on load. A
pivot in a file has two halves: the table definition and a cached copy of the source
data. Writing that cache ships a second copy of every figure, which goes out of date
the moment a row is appended. Leaving it invalid makes Excel rebuild from the sheet
on open, so there is only ever one copy of the truth.

The writer version must be declared as a version Excel recognises. A default of zero
makes Excel read the file as damaged and offer to repair it, which is worse than
having no pivot at all because it makes the operator distrust the whole workbook.

---

## 5. The pipeline

A **round** is one drop of files, which may mix sales reports and adjustment
reports. These steps run in order because each depends on the one before, and
several can only be settled once the whole round is in view.

1. **Read each file**, detecting its format from its content. An adjustment report
   contributes figures rather than rows.
2. **Resolve the product short code.** Exact lookup first, then a keyword rule by
   fruit type so common products select themselves. Unresolved products are flagged
   as errors, and whatever the operator answers is remembered for next time.
3. **Fill the DN.** See section 6.
4. **Flag an unproven DN**, on positive evidence only. See 6.2.
5. **Resolve column D** across the whole batch, since it is the earliest date among
   every row sharing a DN.
6. **Carry opening stock forward** across the whole round, told what each
   consignment had already sold in earlier rounds. See 8.2.
7. **Flag impossible stock**, where a row sold more than was on the floor.
8. **Flag duplicates** against the saved history, so the same report processed twice
   is caught before it is saved.
9. **Fill the Nett** from any adjustment report dropped in the same round, matched
   by account sale number.
10. **Review.** Every unresolved value is editable in place.
11. **Append and record.** The workbook is written and handed back, and the same
    rows are recorded to the durable history.

### 5.1 Flags

Every row carries a list of flags. Each names the field in question so the review
screen can highlight the offending cell, and carries a severity.

| Severity | Effect |
|---|---|
| `error` | **Blocks the append** until a human resolves it. |
| `warning` | Does not block. The value is editable and the row can be saved. |

A flag also carries a **code** where the reason matters to the interface. Several
different warnings can land on the same field: a statement already in the history
and a statement not paid yet both attach to the account sale number, and telling
them apart by reading the message text would break the moment the wording changed.

### 5.2 Failure behaviour

**The workbook is the deliverable.** If the history write fails, the operator still
gets their file, and is told which database change is outstanding and that nothing
has been lost.

The history write is **never retried against an older key** in the hope of getting
something through. An older key would keep the first product on an account sale and
drop the rest without a word. Better to record nothing and say why.

A database that is behind the code must be reported **before** a round is reviewed,
not after the operator presses save. Otherwise the first sign is a failed save, once
the work of a round has already been spent.

---

## 6. Recovering the delivery note number

Column A is Zaco's own DN. **No export carries it.**

The market's exports give a Delivery ID and a Supplier Ref, and the Supplier Ref
only sometimes holds the DN. Measured against the operator's own book over June, 26
of 43 statements agreed and 17 did not, because that field held a producer code seen
across three different deliveries, or a placeholder (`20026*20026`, the producer code
repeated), or another number entirely. In those cases the real DN is nowhere in the
export.

One Zaco DN can also cover several market deliveries. DN 14841 covers both delivery
1178361 and delivery 1180695. **So it cannot be derived even in principle.**

### 6.1 How it is filled

Three sources, in order of authority:

1. **Captured before.** A Delivery ID to DN mapping recorded from a previous round
   wins over everything else. A correction made on the review screen is more
   deliberate than a value read out of a sheet.
2. **Recovered from the open workbook, typing nothing.** The workbook holds DN with
   account sale. The export holds Delivery ID with account sale. The account sale is
   common to both, so joining them produces Delivery ID to DN for free. Measured on
   the real book against the June export: 49 account sales bridged, **15 of 15
   deliveries recovered with no conflicts**, which answers every row and corrects
   the 30 that were wrong.
   Two cases are refused rather than guessed: an account sale covering more than one
   delivery, which cannot be split, and a delivery whose account sales disagree
   about the DN, which means one side is wrong and a coin toss would bury it.
3. **The Supplier Ref**, as a starting value, with the Delivery ID as a fallback
   where the Supplier Ref is absent.

Newly recovered mappings are saved, so the next round does not depend on that
workbook being open or on the operator opening the same one.

### 6.2 Flagging an unproven DN

Flag **only on positive evidence**, never on suspicion. A warning on every row is a
warning nobody reads by the second week.

The evidence that counts:

- The reference is missing.
- The reference is a number used as a **producer code** somewhere in this round.
  June carries both `14013*14798` and `20026*14013`, so 14013 is a producer and the
  14013 in the second is not a delivery.
- The reference falls **outside the range** of DNs already on file. Only applied
  once at least 10 DNs are known, below which there is no reliable range.

A row whose Delivery ID is already in the captured mapping is never flagged.

**Deliberately not used as evidence:** a reference appearing under two different
Delivery IDs. One Zaco DN genuinely covers several market deliveries, so that test
called 35 correct rows wrong out of the 57 it flagged.

---

## 7. Product short codes

The workbook's Description column holds the operator's own short code, for example
`NECTARINES OTHER CLASS 1 MEDIUM MULTI LAYER TRAYER 11kg` becomes `IMP Nect`.

This mapping cannot be derived from the statements. It is built up: whenever an
unseen product appears, the review screen asks for its code and the answer is stored
for next time. Matching is on collapsed whitespace and upper case so trivial spacing
differences hit.

**Keyword rules** pick a code straight from the fruit named in the product string so
common products self select. The first rule whose keywords all appear wins:

| Keywords | Code |
|---|---|
| GRAPE + WHITE / SUGRA / PRIME / THOMPSON | Imp White Grapes |
| GRAPE + CRIMSON / RED / FLAME / PINK | Imp Pink Grapes |
| NECTARINE | IMP Nect |
| CHERR | Imp Cherries 5kg |
| PLUM | Imp Plums |
| APPLE | Imp Apples |
| PEAR | Imp Pears |
| PEACH | Imp Peaches |
| ORANGE | Imp Oranges |
| STRAWBERR | Strawberries |
| GRAPEFRUIT | Grapefruit 15kg |

These are starting defaults. Anything the operator corrects is saved and wins next
time.

**Products deliberately left out of the rules**: the operator's book gives exotic
citrus and granadillas two codes each, and a grape whose name carries no colour
cannot be told apart at all. Those go to the review screen rather than being
guessed.

---

## 8. Rules the figures obey

### 8.1 Returns

A docket with a negative quantity is a **return**: fruit back on the floor,
reversing a sale already booked.

The workbook columns stay **net**, because column J feeds `K = H - J` and the stock
only balances if what came back is taken off the sold figure. Column L must also be
priced over the same net, or `M = J * L` no longer recovers the money.

But the sale and the return both happened, so **both are kept as their own positive
figures beside the net**. Without that, a month that sold 3 448 cartons and had 280
come back is indistinguishable from one that quietly sold 3 168.

Rules:

- Classify a docket by the **sign of its quantity**. A return's value prints
  negative alongside it.
- Both returned figures are held **positive**: 280 returned, never minus 280.
- **Absent is not zero.** Absent means the source could not tell: the account sales
  statement, a row read back out of a workbook, or history recorded before returns
  were captured. Zero means the report showed the figure and nothing came back.
  Defaulting the old history to zero would claim it had no returns when the truth is
  that it never looked.

### 8.2 Opening stock

A **running balance per consignment**, not a figure taken from one file.

```
sent 120  ->  opening 120, sold 115, left 5
              opening   5, sold   5, left 0
```

Rows of one consignment are ordered by the account sale's own date, then by account
sale number. The first opens at what was sent minus what that consignment had
already sold in earlier rounds. Each later row opens at what the row before it left.

Carrying stock forward **inside one file** was right for 33 of 35 rows checked
against the historical sheet. The two that were wrong were both consignments that
had started selling the month before. So the carry forward runs once over everything
a round has, and is told what each consignment had already sold before the round
began.

A consignment with no identifier cannot be tracked across files, so its rows are
left exactly as the parser set them rather than pooled with unrelated rows that
share a blank identifier.

**Impossible stock** (a row selling more than was on the floor) is flagged as a
warning, not corrected. The historical sheet has these too: a delivery amended after
the fact, or a return booked against the wrong consignment. It is worth saying
because Baby Stock is a formula and a negative leftover would otherwise appear in
the sheet with no explanation.

### 8.3 Splitting one Nett across several products

The account sales statement prints a single Nett for a statement that may cover six
products, and `NETT AMOUNT` exists only at statement level.

Each row's share is recreated from the statement's **own printed deductions table**.
No rates are re-derived, only the printed totals are split, so the method is robust
to whatever fees and levies appear.

1. Each printed deduction total (including VAT) is redistributed over the rows it
   applies to, in proportion to each row's price table value.
2. A **named product levy** (PLUMS LEVY, NECTARIEN LEVY) lands only on rows whose
   product string contains that fruit word. Generic words (MARKET, AGENT, FEE, LEVY,
   BANK, VAT) are ignored for this test. Proportional splitting of a product levy
   would be wrong: a plum levy has nothing to do with the grape lines.
3. Each row's Nett is its gross value minus its deduction shares.
4. The rounding residual is absorbed by the **highest value row**, so the shares sum
   to the printed `NETT AMOUNT` **exactly**.

**Fallback:** if the printed deductions do not reconcile to the printed Nett within
**R1.00**, every row reverts to zero with a warning rather than carrying a number
nobody can trace.

Every apportioned row carries a warning and stays editable. Nothing is apportioned
silently. Single product statements are unchanged: the full Nett goes on the one
row.

### 8.4 Statement level cross checks

Reported once, on the first row of a statement, as warnings:

- `** TOTAL SOLD **` against the sum of the product tables' cartons.
- `GROSS AMOUNT` against the sum of cartons times price, within a tolerance of
  `0.05 + 0.01 * total cartons`. Averaged prices are rounded to two decimals, so the
  tolerance has to scale with volume.

### 8.5 Which name a product is counted under

Analytics, the take on list and the signal shown beside a product on the review
screen all group on the **raw product name**, not the operator's short code.

The code is assigned by hand and belongs to the Excel column. Grouping on it split
one fruit into two separate lines the moment a row had no code assigned yet, so the
same product ranked twice, appeared twice in the take on list, and matched neither
signal. The raw name is also what consignment deals are keyed on, so grouping on it
makes all of them agree.

Fall back to the short code where the raw product is missing, then to `Unknown`.

### 8.6 Which money figure is used

**Value is gross**, cartons sold multiplied by unit price, because the sales reports
leave the Nett blank and it only arrives from the payment side.

**Nett is never substituted for by gross in settlement.** The gross is the market's
sale value, not Zaco's money, and settling a supplier on it would pay away the
market agent's commission as well as Zaco's own.

An account sale recorded as **zero is refused** and stored as unknown. Two rows once
reached a saved workbook claiming to be statement 0, from a blank cell coerced
through a number conversion. A zero statement cannot be matched to a payment, and
recorded as one it becomes a bucket that unrelated rows collide in.

---

## 9. Analytics

Computed over the recorded history, scoped to all time, a calendar month
(`YYYY-MM`), or an ISO week (`YYYY-Www`). Week is the finer scope and wins when both
are given. Undated rows drop out of any filtered view but remain in the unfiltered
one.

Trend granularity follows the scope: a single week charts by day, a single month by
week, and the all time view by month.

A row is bucketed for trends by the first of these that is present: the group date
(column D), the invoice date, the date received, then when it was recorded.

### 9.1 Headline figures

Cartons and takings are each reported **three ways**: what sold, what came back, and
the net. The net keeps the established name because it is what the workbook holds
and what everything else is built on.

```
cartons sold      = net cartons + cartons returned
cartons returned  = as captured, positive
total cartons     = net, as the workbook holds it
gross value       = net value + returns value
returns value     = as captured, positive
total value       = net
return rate       = cartons returned / cartons sold
```

The rate is measured against **what sold**, not against the net. 280 back out of
3 448 sold is 8.1%. Dividing by the 3 168 that stuck gives 8.8% and flatters the
month.

Where nothing was returned, the interface shows its plain figures rather than
carrying an "and 0 returned" that means nothing.

### 9.2 Rankings

- **Best sellers** by gross value, each banded A, B or C by the cumulative value
  share **reached before** that item: under 0.80 is A, under 0.95 is B, otherwise C.
  Banding on the share before the item keeps the single biggest seller in class A
  even when it alone clears eighty percent.
- **By market** and **by agent**, straight totals. A row with no market or agent is
  bucketed as `Unknown` rather than dropped.

### 9.3 Per product performance

| Figure | Rule |
|---|---|
| Value, cartons | Summed per row. |
| Consignments | Rows grouped into deliveries. Rows with no consignment id each form their own group, since they were one row per consignment already. |
| Average price | Value divided by cartons. |
| **Sell through** | Sold divided by sent, over consignments reporting **both** figures, counting each delivery **once**. Mixing in rows that sold but recorded no sent quantity pushes the ratio above 100%, which is nonsense the assistant then repeats. |
| Days to sell | Arrival to last sale. `0` means it cleared same day. Absent where the report did not carry both dates. |
| Consignment days to sell | Runs to the last sale of the **latest** row, not the average of its rows. Averaging understates how long the fruit actually sat there. |

### 9.4 Commission coverage

Commission is computed only over rows with agreed terms, and the payload **states
how many of the total that covers**. Commission over a fifth of the business is a
useful number only if you know it is a fifth. Every figure computed over a subset
reports the size of that subset alongside it.

---

## 10. Reconciliation and settlement

### 10.1 The exact join

The CSV names, on every docket, the account sale it was paid under. That is a direct
key between a sale and its payment and replaces matching on supplier reference plus
product name plus value. No normalising, no near misses.

Each row stores its own share as `reference=value`, and a consignment sold across
two runs keeps both.

| Status | Condition |
|---|---|
| `unpaid` | Payment gross is zero or less. Sold, not yet in a payment run. |
| `no_sales` | Paid, with no accumulated sales rows. |
| `matched` | Sales and payment agree within **R0.01**. |
| `outstanding` | Sales total is less than payment gross. |
| `over` | Sales total exceeds payment gross. |

### 10.2 Filling the Nett

An account sale settles several rows at once, so its Nett is split between them **by
sales value**. That is how the operator's book does it: two product rows on one
statement carry Netts in exactly the ratio of their gross. A row naming more than one
reference receives the sum of its share of each.

Shares are rounded to the cent and the **largest row absorbs the residual**, so the
rows on a statement add up to the payment exactly. Without that, a three product
statement can miss by a cent and read as a discrepancy when nothing is wrong.

### 10.3 The fallback

Where there is no payment reference, match on **Supplier Ref plus product**,
comparing summed daily sales against the payment gross. Product names must be
normalised across the two reports' different spellings of the same commodity: drop
brackets, weight tokens (`5kg`, `5.00 kg`), other punctuation, and case. So
`NECTARINES ... LARGE (MULTI LAYER TRAYER 5kg)` and
`NECTARINES ... LARGE MULTI LAYER TRAYER 5.00 kg` become the same key.

**Only fully matched groups are filled.** A partially sold group would otherwise
receive a Nett for produce not all paid for yet.

### 10.4 Payments that can never reconcile

Some account sales carry a gross and a nett with no commodity breakdown at all.
There is no product to match them against, so they are reported as **unattributed**
with their totals and count. Left out, their money vanishes from the picture and the
gap looks like a matching failure rather than a gap in the source document.

### 10.5 Settlement

```
market buyer pays
  -> agent deducts commission, levies and VAT      (payment report)
    -> NETT lands with Zaco                        (payment report)
      -> Zaco keeps its agreed percentage          (recorded here)
        -> the remainder is owed to the supplier   (computed here)
```

Everything above the Nett line the market reports state. Everything below it exists
only in this system: the market agents see Zaco as the supplier and know nothing
about the farmers behind it. Suppliers are absent from every export.

Deals are struck **per delivery line**, keyed on supplier reference plus product.

Two refusals:

- **Nothing is inferred from an absent deal.** A consignment with no recorded
  commission produces **no settlement at all**, rather than one computed at a
  default rate. Quietly assuming thirty percent manufactures a debt to a real person
  out of a missing form field. The thirty percent default exists only as a
  suggestion when recording a new deal.
- **Unsold stock creates no liability.** On consignment the supplier is paid on what
  sold. Cartons that never moved cost the supplier, not Zaco. This is the opposite
  of a buy and resell business and is the single biggest reason cost based
  arithmetic does not belong here.

A settled amount records **what was actually paid**, which may differ from the
computed figure by a rounding, an advance, or something agreed between the two of
them.

Per supplier, report earned, owed, paid, and cartons handed over that never sold.
What was handed over belongs to the delivery, so it is counted **once** even where
several account sales came off it, or a supplier appears to have brought three times
what they did.

Consignments the system cannot speak for are reported **separately** rather than
folded into a total: those awaiting terms and those awaiting payment. Their money is
missing from every figure above them, and that is stated rather than left to be
discovered.

---

## 11. Agent integrity

The agent takes the produce, sells it over days, and remits gross less deductions.
Zaco is not there. The only leverage is what the reports say, so be exact about
which questions they can answer.

### Answerable

The **deduction rate**, `1 - nett / gross`. Over real June data the median is 15.0%
and 120 of 161 account sales sit between 14% and 16%, so a line well outside that
band is a real question with a number attached.

The baseline is **this business's own median**, not a fixed figure, so it stays
meaningful if the agent's terms change.

| Constant | Value | Meaning |
|---|---|---|
| Minimum priced lines for a median | 8 | Below this there is no going rate to compare to. |
| Over median threshold | 5 percentage points | Above the going rate, worth a question. |
| Severe rate | 50% | The agent kept more than it remitted, whatever the median says. |
| Assumed rate with no history | 15% | Only ever used to describe a lone line. |
| Unsold majority | 50% | One consignment selling this share or less. |
| Product unsold notable | 25% | A product's overall unsold share worth a glance. Real figures run 7% (unremarkable) to 51% (worth asking about). |
| Minimum cartons for price spread | 3 | A single carton dumped at R1 is real and belongs in the unsold figure. In a price spread it reports "107x" and drowns the comparison. |

A row whose Nett is zero against a positive gross is severe: nothing came back at
all.

Per product unsold share is a **different claim** from a bad consignment. A chip
built from consignment level figures said "85% not sold" against oranges whose real
figure was 7%, because one bad consignment was read as the whole product.

### Not answerable

**Whether the price recorded is the price the fruit actually made.** 98% of docket
prices are exact multiples of R10, only 2 of 485 dockets carry any cents, one month
uses 31 distinct prices, and the same commodity on the same day spans up to 5.6
times. Floor negotiation does not produce that, and genuine end of day clearance is
indistinguishable from under reporting the good sales. The report has a `Market Avg`
column that would settle it and the export leaves it at `0.00` in every line.

**This limitation must travel with the figures, in the payload, not in
documentation.** A panel that only ever reports what it *can* check reads as a clean
bill of health on the one thing it is blind to.

Every flag carries the figures that raised it. **Nothing here is called fraud,
because nothing here can prove it.** A high deduction has innocent explanations: a
commodity levy, a return, a part paid run. These are questions with numbers
attached, not accusations.

---

## 12. What to take on

Not a shopping list, and there is no budget in it. Zaco pays nothing to acquire
stock. What is scarce is the market slots, the handling and the supplier
relationships spent on produce that then fails to move.

The question: of everything a supplier could offer, which lines actually clear, and
which earn the most commission per carton handled.

### Weights

| Signal | Without terms | With terms |
|---|---|---|
| Commission per carton | not available | 0.45 |
| Clearance (share of what was sent that sold) | 0.30 | 0.15 |
| Speed (how quickly it moved) | 0.25 | 0.15 |
| Price (what a carton fetched) | 0.20 | 0.05 |
| Earnings (what it brought in overall) | 0.15 | 0.10 |
| Recency (still selling, or season over) | 0.10 | 0.10 |

Until a commission is recorded these are all **proxies**. Once terms exist,
commission per carton is not a proxy for the earnings, it **is** the earnings, and
it already contains the sale price and the agreed rate together, so it leads and the
proxies drop back. Every payload states which of the two basis it used.

### Scoring

- Each signal is scaled to 0 to 1 against the **observed maximum in this business**,
  not an outside benchmark.
- Speed: `1 - (average days to sell / 14)`. A consignment taking 14 days or more
  scores nothing.
- Recency: `1 - (days since last sale / 45)`.
- Unknown clearance scores **0.5**, not 0 and not 1. Unknown speed likewise. Missing
  evidence is not assumed good.
- The weighted score is multiplied by a confidence of
  `min(1.0, 0.6 + 0.2 * consignments)`. One consignment is a data point, not a
  pattern. Applied to the score rather than as a band cap, so the ranking and the
  bands never disagree. A higher scoring line sitting in a lower band reads as a bug
  even when the reason is sound.

### Bands

Assigned **by rank, subject to a floor**, over the products with any history:

- Critical: the top **15%**, provided the score is at least **0.50**.
- High: the next **35%**, provided the score is at least **0.38**.
- Low: everything else.

Bands are by rank because scores across a real season sit in a narrow range, 0.3 to
0.7 over three months of this business. Fixed cut offs put nearly everything in one
band and the list stops being a priority list. The floors stop a weak season
promoting a bad line just for being least bad.

**Attention share** is apportioned only across Critical and High lines, weighted by
`(score - 0.38)^2`, that is by how far each sits **above the bar** rather than by
raw score. Splitting on raw scores hands every product a near identical share, which
is not a recommendation. Pushing effort into a Low line is the thing this list
exists to prevent.

### Reasons

Each line carries plain statements of why it scored as it did, in weight order, so
every score traces to the figures beside it. A line with fewer than **2**
consignments is marked as provisional.

**The levels are computed, not generated.** The same history in gives the same
levels out, every time. Real money is settled off the back of them.

---

## 13. Deliberate refusals

These are the behaviours most likely to be got wrong, and each has been argued for
rather than left undone.

| Refusal | Why |
|---|---|
| No Nett is invented where the report does not print one. | The field is left empty with a warning and the operator enters it, or reconciliation fills it from the payment side. |
| No settlement is computed at a default rate. | A missing form field is not a debt to a real person. |
| No delivery note number is guessed. | One DN can cover several market deliveries, so it cannot be derived even in principle. |
| No unsold stock becomes a liability. | On consignment that loss lands on the supplier. It still ranks heavily in advice, because produce that does not move earns nothing and burns a market slot. |
| No price is judged. | The reports cannot answer it, and the column that would is exported empty. |
| No warning is raised on suspicion. | A flag on every row is a flag nobody reads by the second week. |
| No pivot cache is written. | A cached second copy of every figure goes stale the moment a row is appended. |
| No history write is retried against an older key. | It would keep the first product on an account sale and drop the rest without a word. |
| No returned docket is dropped, and none is folded away. | Dropping it overstates the month. Folding it into the net hides that it happened. |
| No product levy is split proportionally. | A plum levy has nothing to do with the grape lines on the same statement. |
| No account sale is recorded as zero. | A zero statement cannot be matched to a payment and becomes a bucket unrelated rows collide in. |

---

## 14. Records to keep

| Record | Holds | Keyed on |
|---|---|---|
| **Statements** | Every row appended to the workbook. The history behind analytics, reconciliation and settlement. | Market agent, account sale, consignment |
| **Product codes** | The raw product string as printed, mapped to the operator's short code. | The product string, normalised |
| **Delivery notes** | The market's Delivery ID mapped to Zaco's DN. | Delivery ID |
| **Suppliers** | Whose produce it actually is, and their default rate. | Name |
| **Consignment deals** | The commission agreed on a line, and whether the supplier has been settled and for how much. | Supplier reference and product |
| **Profiles** | Who may use the system, and whether they are staff or an admin. | User |

Rules:

- The statements key must be **the account sale together with the consignment**, not
  the account sale alone. One account sale settles several consignments, and one
  consignment is settled over several account sales. Keying on the account sale
  alone silently drops every row of a multi product statement after the first.
- Where a consignment identifier is unknown, store a sentinel rather than a null.
  A null is distinct from every other null in SQL, which would let the same row be
  recorded again and again and defeat the uniqueness guard.
- Every read and write runs **as the caller**, so row level access rules apply
  rather than being bypassed by a privileged key. Authentication answers who you
  are. Access rules answer what you may touch. Only the second protects a row.
- A processed statement is a financial record. Staff may record and delete their
  own. Changing one is reserved for an admin.
- Deleting history is scoped to a month or a week. There is **no delete everything**
  path.
- Signup is by invitation. Nobody promotes themselves.

---

## 15. Assistant

The operator asks a question in ordinary English and gets an answer grounded in the
recorded history.

- **No arithmetic on money is done by the model.** Every total, ranking and trend in
  the prompt is computed deterministically by the same code behind the analytics,
  and handed to the model as established fact alongside the underlying rows for
  detail questions. The model's job is language: understanding what was asked and
  explaining the answer. That keeps the figures exact while letting the question be
  open ended.
- **Read only by design.** Nothing it does can write to the workbook or the history.
  A wrong answer costs a re ask, never a corrupted financial record.
- Rows sent verbatim are capped (2 000 is sufficient) to bound cost and latency. The
  totals still cover everything, not just the rows sent.
- Where anything was returned, the context says so explicitly rather than letting a
  net figure stand as the whole story.

---

## 16. Acceptance criteria

Each of these is checkable against the described behaviour.

### Parsing

1. A double encoded weekly CSV, where every line arrives as a single quoted cell,
   parses to the correct number of rows rather than to zero.
2. A Daily Sales PDF whose Product line ends `(PUNNET 5kg) 10` yields the product
   without the trailing `10`, and a product genuinely containing a number elsewhere
   is untouched.
3. A report carrying two different market agents assigns each row its own agent.
4. `JOH*SUB*5644102/12026-07-13` yields account sale `5644102` and date
   `2026-07-13`.
5. An account sale appearing on adjustment lines `/1` and `/2` resolves to the sum
   of both.
6. A docket with reference `PRE*BT*0` and date paid `0000-00-00` is treated as
   unpaid, not as a reference.

### Grain and stock

7. A consignment whose dockets name two different account sales produces **two**
   rows, both carrying the consignment's Qty Sent, ordered so the second opens at
   what the first left.
   Given 120 sent, 115 sold under the first and 5 under the second:
   row one opens at 120, row two opens at 5.
8. Cartons sent across a consignment settled over three account sales counts the
   delivery **once**, not three times.
9. A consignment first seen this round opens at its full Qty Sent. One that sold in
   an earlier round opens at Qty Sent minus what was already sold.

### Returns

10. A consignment with a docket of `+10 @ R200` and a docket of `-10 @ R200` yields
    cartons sold `0`, cartons returned `10`, returns value `2000.00`, all positive.
11. A consignment with no negative dockets reports cartons returned `0`, not absent.
12. A row from a source that cannot report returns leaves both figures **absent**,
    and analytics reads absent as nothing returned without claiming it as evidence.
13. Over a month of 3 448 sold, 280 returned and R593 067.80 rung up against
    R90 100.00 returned, the headline figures read:
    cartons sold `3 448`, returned `280`, net `3 168`, gross value `593 067.80`,
    returns value `90 100.00`, net value `502 967.80`, return rate `0.0812`.

### Money

14. A statement whose printed deductions reconcile to its printed Nett splits that
    Nett across its product rows so the shares sum to the printed figure **exactly**
    to the cent, with a named fruit levy landing only on that fruit's rows.
15. A statement whose printed deductions miss the printed Nett by more than R1.00
    leaves every row at zero with a warning.
16. An account sale settling three rows splits its Nett by sales value with the
    largest row absorbing the residual, so the three sum to the payment exactly.
17. A payment record with no commodity lines is reported as unattributed, with its
    gross and nett included in that figure and excluded from matched totals.

### Product identity

18. Two rows of the same raw product, one with a short code and one without, group
    as **one** product in analytics, in the take on list, and in the signal shown on
    the review screen.
19. The workbook's Description column still receives the short code.

### Workbook

20. Appending to a workbook whose columns have been reordered writes each value
    under the right header and writes formulas pointing at the right cells.
21. No formula column ever receives a literal value.
22. Column U survives a read and write cycle unchanged.
23. A file with no recognisable header row is rejected with an explanation, not
    parsed into the wrong columns.

### Refusals

24. A consignment with no recorded commission produces no settlement line at all,
    and its Nett is reported as unattributed rather than counted as earnings.
25. A row whose Supplier Ref is a number used as a producer code elsewhere in the
    round is flagged. A row whose reference merely appears under two Delivery IDs is
    **not**.
26. Attempting to record an account sale of `0` stores it as unknown.

### Behaviour under failure

27. When the history cannot be written, the workbook is still returned, and the
    message names what is outstanding and says nothing has been lost.
28. A database missing a required column is reported **before** the round is
    reviewed.

---

## 17. Known limits

These are limitations of the source documents, not defects to fix in the build.

- The **account sales PDF path cannot produce the one row per account sale grain**,
  because that format prints no payment reference. Its rows key column E on the
  Consignment ID instead. Prefer the CSV wherever there is a choice.
- **History recorded before returns were captured reports nothing returned.** That
  is what the record knew. It is not evidence that nothing was returned.
- Whether **column D should be a delivery date rather than a sale date** is
  confirmed for the CSV path only. On the PDF path it is an assumption, because that
  report does not print a delivery date.
- The **Market Avg column is empty in every export**, so the price a carton fetched
  cannot be verified. The fix is for the market to populate it.
- The **product short code lookup grows by hand.** Keyword rules cover the common
  fruit. A name carrying no distinguishing word cannot be classified at all and goes
  to review.
- On the Daily Sales PDF path, whether **Qty Sent maps to Qty Received and Qty Avail
  to Opening Stock** is reverse engineered from a filled sheet and has not been
  confirmed against a matched document pair for every agent.

---

*Figures quoted from real data, such as the 15% median deduction rate and the 30%
commission default, are observations from the operator's own history rather than
settings. The system recomputes them from whatever history it holds.*
