# ZacoAgents build exercise

> **What was built lives here.** This page is the brief as handed over; the only change to it
> is this block.
>
> | | |
> |---|---|
> | [docs/RUNNING.md](docs/RUNNING.md) | How to run it, locally and hosted |
> | [docs/DECISIONS.md](docs/DECISIONS.md) | Every call made where the reports left a choice, what was rejected and why, and what is still open |
> | [NOTES.md](NOTES.md) | The short written note the brief asks for |

Build the system described in `REQUIREMENTS.md` against the documents in
`data/` and the workbook in `workbook/`.

## What is here

```
REQUIREMENTS.md    What the system must do.
data/              Reports from two market agents, covering two weeks.
workbook/          The operator's live Excel book, and a blank template.
lookup/            What is known so far about product short codes.
```

That is everything. There is no reference implementation, no expected output,
and no list of what to watch for.

## The exercise

The documents in `data/` are real exports in shape, wording, layout and
encoding. Every figure in them was invented for this exercise, but nothing about
how they are structured was made convenient.

They cover **two rounds a week apart**, because several requirements only bite
across rounds rather than inside a single file.

Read `REQUIREMENTS.md` first, and read section 3, Vocabulary, before the rest of
it. Then look at the data before you design anything. The documents will tell
you things this brief does not.

## Deliverable

1. **The working system.** Any language, any framework, any storage. Something
   we can run.
2. **The operator's workbook**, after your system has processed both rounds
   into it.
3. **A short written note.** No more than two pages. What you built, the calls
   you made and why, what you chose not to do, and anything you found in the
   data that `REQUIREMENTS.md` does not mention.

The note carries real weight. A system that gets a figure wrong but explains
what it was unsure of is worth more than one that reports every figure with
equal confidence.

## Submitting

Work on a branch and open a pull request when you are done, or hand the repo
back however was agreed. Either way:

- **Commit the workbook** after your system has processed both rounds into it.
  `workbook/account-sales-book.xlsx` is the deliverable, not just an input.
- **Fill in `NOTES.md`.** It is read closely.
- Commit as you go rather than in one lump at the end. How the work was
  sequenced is informative.
- Do not commit dependencies, virtual environments or secrets. `.gitignore`
  covers the usual ones.

## Scope and time

`REQUIREMENTS.md` describes more than anyone would finish in a sitting. That is
deliberate.

Sections 4 to 7 are the system: read the documents, get the grain right, resolve
what the reports do not carry, write the workbook. Do those properly before
anything else.

Sections 8 to 10 are what the system is for: payments, reporting, and whether
the agent has treated the money normally. Take them as far as you get.

**Depth beats coverage.** Four sections done correctly, with the awkward cases
handled and the uncertain ones flagged, beats ten sections that each work on the
happy path. If you run out of time, say in your note what you would have done
next and why it matters.

## One thing worth saying plainly

The hardest part of this is not the parsing. It is deciding what the system
should do when the documents do not answer a question, which happens more often
than you would expect from reading the brief.

A figure that is quietly wrong is worse than a field that is visibly empty. The
operator settles real money against this.
