# SolveSpace

A private competitive-programming practice workspace.

I use this to practise for algorithm contests. It collects problems, keeps my solutions together
with the problem statement, and runs submitted code against the official test cases so I can see
which attempts actually pass before I move on.

## What it does

- **A problem library that builds itself.** A scraper pulls problems and their test cases into the
  database, so the workspace fills up without hand-copying anything. Statements are enriched with
  worked-through hints and reference solutions, which is what makes a problem useful to revisit
  weeks later.
- **Code runs somewhere harmless.** Submitted code is executed in an isolated sandbox with a hard
  memory cap, a CPU limit, no network access, and a process ceiling. A runaway loop or an infinite
  allocation is a failed test case, not a dead machine.
- **An editor and a run button.** Write an attempt next to the problem, run it against the official
  cases, and get a verdict per case.
- **Progress you can look at.** Solutions are kept per problem, so it is clear what has been solved
  and what has not.

## Running it

```bash
cp .env.example .env
# then fill in the values it documents, and start the stack
docker compose up -d --build
```

`.env.example` lists every variable. Leaving the enrichment settings blank runs the workspace
without the AI-generated hints, which is fine for solving.

## Documentation

Full documentation is served by the stack at `/documentation/`, and the sources are in
[`documentation/docs`](documentation/docs).
