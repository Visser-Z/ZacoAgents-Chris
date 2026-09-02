# PersonalTest — files to try the system with

Made-up documents in the agents' own formats, for checking the system by hand. They use
delivery IDs in the `22xxx` range, account sales in the `39xxxx` range and fruit that appears
nowhere in `data/`, so nothing here collides with the real rounds.

Every result below was **observed by running these files through the app**, not predicted.

> Sign in at <http://127.0.0.1:8000>. Everything except the two files in `refusals/` goes to
> **Resolution queue** (`/queue`); those two go to **Read a document** (`/rounds`), which takes
> one file at a time and stores nothing.
>
> To start from nothing at any point: `docker compose down -v && docker compose up -d --build`.
> That destroys the workbook volume too, and the app seeds a fresh copy on the next boot.

---

## 1. `round-a/` — the working round

**Select all five files together** on the Resolution queue and press *Save the round*.

| File | What it is |
|---|---|
| `01_DailySalesDetail_20260706-20260712.csv` | five deliveries, docket by docket |
| `02_ConsignmentReports_20260706-20260712.txt` | the same sales told again, by a different report |
| `03_PaymentDetails_20260706-20260714.csv` | the payment side |
| `04_AccountSales_390110.txt` | statement for account sale 390110 |
| `04b_AccountSales_390100.txt` | statement for account sale 390100 |

**What you should see:** 5 deliveries, 5 consignments, **5 rows**, 3 account sales,
260 cartons sent, 145 net, **R8,025.00** gross, and **12 open questions**.

### Things worth looking at on this screen

**The second report adds nothing.** `02` describes exactly the same sales as `01`. The totals
are identical whether you upload one of them or both, and every repeated docket is noted. Try
uploading `01` alone first and compare.

**One consignment, two rows.** The lemons (delivery `2200100Z`) sold under two account sales, so
they become two rows — opening at 80, then at **50**, never 80 twice. The 80 cartons sent are
counted once.

**A return is its own figure.** The mangoes sold 25 and had 5 come back. You get sold 25,
returned 5, net 20 — not a quiet 20.

**A sale nobody has paid for.** The watermelon docket carries payment reference `PRE*BT*0` and
date paid `0000-00-00`. It makes **no row** — a row is delivery × product × account sale and one
third of it is missing — and appears under *sold, not yet in any payment run*.

**Two product links are made without asking you.** Account sale 390110 names both
`LEMONS EUREKA CLASS 1 MEDIUM STANDARD CARTON 15kg` and `LEEU 1M CT15 LEMON EUREKA` for R900,
and both pineapple names for R1,925. That is proof, so the system merges them and shows the
evidence.

**One product link is *not* made.** Account sale 390100 has two rows both worth R1,200 — lemons
and mangoes. `MATA 1L TR04 MANGO TOMMY` could be either, so nothing is merged and it arrives as
a **question** with its reasoning. Answer it either way and watch the product code count change.

### The five delivery notes

| Delivery | Supplier Ref | Proposed | Why |
|---|---|---|---|
| `2200100Z` | `20026*14930` | **14930** | the reference half passed all three tests |
| `2200200Z` | *(blank)* | **14931** | minted — nothing to derive one from, and no flag, because a blank proves nothing |
| `2200300Z` | `20026*20026` | **14932** | minted — **flagged**: the reference half is the producer code itself |
| `2200400Z` | `20026*30055` | **14933** | minted — **flagged**: `30055` is a producer code elsewhere in this round |
| `2200500Z` | `30055*14940` | **14940** | reference half passed; the produce belongs to **producer 30055**, not Zaco |

The numbers depend on where your `14xxx` series has got to — with the shipped book at
`14690`–`14692`, minting starts at `14931` because `14930` has already been proposed.

Two of five carry a flag and three do not. That is the point: a warning on every row is a
warning nobody reads by the second week.

**The agent's own number is never used.** `04_AccountSales_390110.txt` prints
`DELIVERY NOTE NO : 203600`. It appears nowhere in any proposal.

**Try the multi-select.** `2200100Z` and `2200200Z` share an agent and a delivery date, so each
offers the other as *"same agent, same day — one load?"*. Ticking it needs a typed reason,
because nothing in the documents says they travelled together.

**Try "No DN — carried for another producer"** on `2200500Z`. It needs a reason, and the row is
then written with column A empty and the reason attached — which reads differently from a row
nobody has got to.

**Nothing writes until you approve it.** Before you touch anything, every row says
`no approved delivery note, no product short code`, and *Close the queue* is refused.

---

## 2. `refusals/` — one at a time, on **Read a document**

| File | Result |
|---|---|
| `05_notes-from-the-office.txt` | **Refused.** "This file does not read as any of the five report kinds this system handles… Nothing was taken from it." |
| `06_PaymentDetails_20260715_FarmersTrust.csv` | **Read as an Account sales statement**, confidence 1.00 |

The second one is the interesting one. It is named like a payment report, saved as `.csv`, and is
actually an account sales statement. The classifier is never given the filename, so it reads what
the file *is*.

Try `05` on the Resolution queue alongside the round-a files: **the whole round is refused**, not
just that file. Staging the rest would show a picture that looks complete and is not.

---

## 3. `round-b/` — upload after round A is closed

Answer round A's questions, press **Close the queue**, then upload these two together.

| File | What it is |
|---|---|
| `07_DailySalesDetail_20260713-20260719.csv` | reprints two of round A's lemon dockets, plus new sales |
| `08_PaymentDetails_20260713-20260719_FarmersTrust.csv` | a **narrowed** export |

**The overlap is caught.** Real exports repeat themselves — the supplied June file reprints May's
nectarines verbatim, and `07` does the same to round A's lemons. Counted again, you would gain 50
cartons and R2,100 that never happened, and the book would look completely normal. Instead you
get two alerts naming the exact dockets, and the round holds **2 rows**, not 4.

**Stock carries forward.** The lemons open at **30** — what round A left on the floor — not at 80,
and the row is marked *carried in*.

**The narrowed export says so.** `08` was run for `TSHWANE MARKET` and `Farmers Trust (Pre)` only.
You get a warning saying anything outside that is absent from the file rather than absent from
the business — because the person who ran it usually believes they took the lot.

**Only what is new is asked about.** One product code (the pawpaw) and one delivery note. The
lemons keep the code you gave them last round and are not asked about again.

---

## 4. `awkward/`

### `09_PaymentDetails_20260706-20260714_corrected.csv`

The same file as `03`, with account sale 390100 paying **R2,100.00** instead of R2,040.00 — what
a re-run after a correction looks like. Upload it **on its own** as a new round, after round A is
closed.

The record is **suspended**, showing both figures and both documents:

```
nett: 2040.00 vs 2100.00; total_deductions: 313.04 vs 260.87
```

Neither is applied over the other. The round is blocked until someone picks one **and types a
reason** — a blank reason is refused. The rest of the file is unaffected: only that one record is
held back.

You can also upload `03` and `09` together in one round for the same result.

### `10_NettPaymentAdjustments_202606.txt` — the format hazards

Read this one on **Read a document**. In one small file:

- **Non-breaking-space thousands separators mixed with commas on the same line** —
  `R 4 250.00` and `R 3,612.50`
- **A date jammed onto the reference** — `JOH*SUB*5688000/12026-06-11`, no delimiter
- **A `Total` row in the middle of the list**, not at the end
- **One payment against two references** — `20026*14901 & 14902`

All four records read correctly, the mid-list `Total` is noted and skipped rather than treated as
the end, and the bare `14902` inherits the producer code rather than being left as a fragment.

---

## What this set does not cover

- **Appending to the workbook.** That is Phase 4; the queue stops at *resolved*.
- **Reconciliation, settlement, reports and the agent conduct panel.** Phases 5 to 7.
- A **workbook** whose `STM No` matches one of these account sales, so the delivery-note reuse
  path has nothing to reuse. It is exercised by the test suite instead
  (`tests/test_dn.py::test_the_workbook_wins_over_the_reference`).

## Three defects these files found

Worth recording, because they are the reason the set exists:

1. **A minted delivery note could reissue one approved in an earlier round** — two loads under one
   number, and nothing looking wrong. Minting now avoids every DN ever approved.
2. **The Tshwane block of a Nett Payment Adjustments report lost its account sale number.** The
   file uses two shapes — `JOH*SUB*5640001/12026-04-13` jammed together and
   `PRE*BT*380101 2026-04-01` spaced apart — and only the first was handled. The second was read
   as another supplier reference, leaving real payments in the system with nothing to join on.
   **This was present in the supplied `data/` too**, and is now fixed and pinned by a test.
3. **An account sale restated in a later round was a second record, not a conflict.** Only the
   version uploaded first survived. The same comparison now holds across the round boundary.
