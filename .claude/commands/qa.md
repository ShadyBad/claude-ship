---
name: qa
description: The hands-on quality pass — pull a shipped slice, actually use it, and turn what you notice into tickets. Everything upstream checks whether the code is correct; nothing upstream checks whether it is good. Tests pass on interfaces nobody would want to use. That judgment is the one input an agent cannot generate, and this command exists to make it cheap and to make sure it survives the session. Entry point for the qa-queue skill. Findings become tickets and are never fixed in the QA session.
argument-hint: [<ticket-id>] | list | pass <ticket-id> | fail <ticket-id> | note "<finding>"
---

# /qa — Injecting Taste

Entry point for the `qa-queue` skill. Last stop in the loop, and the one that feeds it.

```
/spec  →  /to-tickets  →  /implement  →  /qa  ──┐
              ▲                                  │
              └────────── findings ──────────────┘
```

## Invocation

```
/qa                          # next needs-qa ticket, with run instructions
/qa <ticket-id>              # a specific ticket
/qa list                     # everything awaiting QA
/qa pass <ticket-id>         # accept: needs-qa -> done, dependents unblock
/qa fail <ticket-id>         # findings become tickets; the slice stays needs-qa
/qa note "<finding>"         # file one finding without a full session
```

## The rule

**Findings become tickets. They are never fixed here.**

The temptation is real — the bug is right there, the context is loaded, it is two lines. But that context is the far end of a long session, holding a full pipeline's sediment, which is the worst place to exercise judgment. And a fix applied here skips the TDD loop, the judges, and done-gate: it is the only path in the system that lands unreviewed code.

Write it down, file it, send `/implement` back to work.

## What a session looks like

You get told exactly how to exercise the slice — the command, the URL, the input that reaches the new path — plus what is deliberately out of scope, so half the session is not spent re-reporting work already queued.

Then Claude goes quiet. It will not narrate what should happen; being told what to look for is exactly what destroys the value of an unprimed reaction.

For each thing you mention, two questions only: **blocking or polish**, and **which ticket does this block**. Then it is filed, verbatim, before it is categorized — "the progress output is noisy" is data, "improve progress output formatting" is a paraphrase that already lost the complaint.

## Taste findings count

"This works but the empty state is depressing" needs no defect to justify it. It gets filed as polish, in your words. An agent will never generate that ticket on its own, which is the entire reason this command exists.

## Verdict

- No blocking findings → `pass`. The ticket goes `done` and its dependents unblock.
- Blocking findings → the slice stays `needs-qa`, the new tickets are inserted as blockers, and you are told plainly which downstream work just became unreachable.

`needs-qa` never unblocks dependents. That is what stops a batch from stacking three slices on top of one you have not laid hands on.

## Constraints

- Never fixes anything.
- Never marks a ticket `done` with a blocking finding open.
- Never files a finding the ticket declared out of scope without asking first.
