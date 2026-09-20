# SolveSpace

<div align="center">

![SolveSpace](https://github.projectnova.download/public/project/solvespace.svg)

</div>

A private competitive-programming practice workspace.

I use this to practise for algorithm contests. It collects problems, keeps my solutions next to the
problem statement, and runs submitted code against the official test cases so I can see which
attempts actually pass before I move on.

The point is to remove every reason not to practise. If setting up a problem takes longer than
solving it, the practice does not happen.

## What it does

**A problem library that builds itself.** A scraper pulls problems and their test cases straight into
the database, so the workspace fills up without anyone hand-copying statements. Statements are
enriched with worked-through hints and reference solutions, which is what makes a problem worth
revisiting weeks later when the original attempt has been forgotten.

**Code runs somewhere harmless.** Submitted code is executed inside an isolated sandbox with a hard
memory cap, a CPU time limit, no network access, and a ceiling on process count. A runaway loop or an
accidental infinite allocation becomes a failed test case rather than a dead machine. This is the
part worth trusting: it is the reason it is safe to run code that is known to be broken.

**An editor and a run button.** Write an attempt next to the problem, run it against the official
cases, and get a verdict per case. No switching windows, no re-uploading a file.

**Progress you can look at.** Solutions are kept per problem, so it is clear at a glance what has
been solved and what has not, and which problems are worth another attempt.

## Running it

```bash
cp .env.example .env
# then fill in the values it documents, and start the stack
docker compose up -d --build
```

Leaving the enrichment settings blank runs the workspace without generated hints, which is fine if
you only want to solve problems.

## Documentation

Full documentation is served by the stack at `/documentation/`, and the sources are in
[`documentation/docs`](documentation/docs).

It covers the four-stage scraper pipeline, the sandbox limits and how they are enforced, the
database schema, and the execution API.
