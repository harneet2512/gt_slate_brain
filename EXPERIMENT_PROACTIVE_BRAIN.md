# Experiment: GT as a Proactive Brain

**Started:** 2026-05-29 · **Repo:** gt_slate_brain (independent of GroundTruth)

## The shift

GroundTruth today is **reactive**: 2 of its 3 injection points (`post_view`,
`post_edit`) only annotate a file the agent *already chose* to touch. Only the
brief is proactive. But GT sits in the observation stream — it sees every action
and observation, and controls the text the agent reads next. So it *can* lead,
not just react. This experiment explores making GT a **proactive brain**.

## The reframe (what "proactive" must and must NOT mean)

"Proactive" naively means *"tell the agent where to look / what the bug is."*
**That is the most dangerous thing GT can do** and we reject it:

- Reactive annotation is low-risk: a wrong note on a file the agent already opened
  is shrugged off.
- Proactive steering is high-risk: if GT says "look at X / the bug is in Y" and is
  wrong (and 70–80% of graph edges are `name_match` — wrong often), GT drags a
  frontier agent **off its own correct path**. **Wrong-proactive ≫ wrong-reactive.**
- The agent finds the gold file ~88% of the time alone. Localization is not the
  bottleneck — so steering it is high-risk for low reward.

So the real shift is on two sharper axes, **not** "reactive → steer":

1. **Stateless → stateful.** Today each hook knows only the current file. The brain
   maintains `required scope = (task intent ∩ graph)` vs `progress = what the agent
   has done`, and proactively surfaces the **delta** at the moment it matters
   (after a contract-changing edit; before submit) — e.g. *"you changed `f`'s
   signature; callers A, B in other files still call the old shape."*
2. **Facts, not strategy.** Proactive only about *verifiable graph facts* ("this
   edit breaks caller X" — checkable). Never about *strategy* ("you should do Y").
   GroundTruth already de-prescribed its L5 layer for this reason.

## Why this is the lever

GT's only real information advantage is the **global map** (call graph, blast
radius, co-change, contracts). The agent does *local* search and rebuilds structure
one file-read at a time. The real bottlenecks are post-localization — incomplete
fixes, missed callers, scope misses, broken contracts — exactly where a global view
beats local search.

## The safety gate (non-negotiable)

Proactive injection fires **only on verified-provenance edges** (`same_file` /
`import` / `lsp`), **never `name_match`**. A proactive `name_match` is the poison
case. Correct-or-quiet is *stricter* here than in reactive mode.

## Open question (unresolved — forks the architecture)

- **(a) Anticipate the agent's next *need*** — pre-fetch context before it asks
  (mostly the brief, done continuously). Lower lever.
- **(b) Catch what the agent is *missing*** — scope / completeness / contract gaps
  its local view can't see. The real lever (current hypothesis).

Decision pending before any implementation.

## Confidence

- reactive → proactive is the right *direction*: **high**
- naive "steer the agent" is a trap: **high**
- the win is scope/completeness/contract enforcement specifically: **moderate**
  (needs validation, not assumed)
