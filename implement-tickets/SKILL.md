---
name: implement-tickets
description: "Implement a dependency graph of tickets strictly one at a time with fresh sub-agents and verified integration."
disable-model-invocation: true
argument-hint: "<tickets-directory>"
---

# Implement Tickets

Implement every ticket in the provided directory according to its `Blocked by` dependencies.

This workflow only handles ticket sets that keep the integration branch green after every single ticket's integration. A ticket sequence that does not promise per-ticket green — the shared-branch extreme of an expand-contract split, where intermediate tickets stay red by design and only the final integration-verification ticket promises green — is outside this workflow; hand it to a manual per-ticket path.

Act only as the orchestrator: schedule, delegate, integrate, and verify. Never implement ticket behaviour or modify code in the main agent.

The run is unattended: never ask the user anything while the run is in progress. Decide within this skill's rules, and record anything that needs a human decision in the final report.

Each ticket must be handled by one fresh sub-agent that explicitly invokes the `implement` skill for exactly that ticket.

## Prepare

1. Validate the tickets directory.
2. Settle this run's integration branch and working tree by asking the Prepare questions below, or by the cannot-ask fallback in that section when asking is impossible.
3. Read every ticket and extract:
   - identifier
   - title
   - status
   - `Blocked by`
   - parent spec reference, when present
4. Validate that identifiers are unique, every blocker exists, and the dependency graph has no cycles.
5. Check every ticket's triage status: only `ready-for-agent` tickets enter scheduling.

Stop before changing code if validation fails.

### Prepare questions

Before dispatching any ticket, ask the user once whether this run uses a single shared git worktree for ticket git operations, together with a suggested branch name for the new integration branch.

- **Worktree chosen** — create a branch with the settled name, forked from the branch that was current when Prepare started, and use it as this run's integration branch; create and check out exactly one shared git worktree on that integration branch; perform every ticket dedicated-branch operation — create, checkout, commit, and integrate — inside that worktree, and never switch the primary working tree's branch for ticket work; a dirty primary working tree is allowed on this path.
- **Worktree declined** — ask whether the integration branch is the branch that was current when Prepare started, or a new branch forked from it with a suggested name; the primary working tree must be clean before any ticket is dispatched, or Prepare stops with a reportable error and dispatches nothing; perform ticket dedicated-branch operations in the primary working tree.

When asking the user is impossible, do not invent a worktree or a new integration branch: settle without asking as **Worktree declined** with the integration branch equal to the branch that was current when Prepare started, still requiring that primary working tree to be clean before dispatch, and record this cannot-ask fallback in the final report.

Every path still gives each ticket its own dedicated branch that merges into the settled integration branch.

Never create a separate worktree for an individual ticket.

Suggest branch names from the tickets/spec directory's basename plus a prefix that fits the work; the normative example is a `.scratch/foo-bar` directory suggesting `feature/foo-bar` for a new-feature ticket set. Other prefixes are acceptable as long as the basename survives when it can be derived; invent a name outright when it cannot. Check a candidate name for collisions before presenting it whenever a cheap Git query can answer.

Choose the worktree's disk path and every branch name so none collides with anything that already exists and every name stays human-readable; no fixed naming format is required beyond that.

Once every question above is answered, or settled by the cannot-ask fallback, ask the user nothing else for the rest of this invocation; anything that still needs a human decision goes into the final report instead. These Prepare questions run before the run is in progress, so asking them here is compatible with staying unattended afterward.

Re-invoking this skill within the same agent session, on the same tickets directory, reuses the settled integration branch and worktree choice without asking again; if the chosen worktree's directory is missing, recreate it checked out on the same integration branch without asking.

A different tickets directory, or a new agent session, runs the questions above again — this skill keeps no external record of a previous run's answers.

If creating the settled integration branch or shared worktree fails after the questions above are answered, treat it as a terminal Prepare failure: dispatch no ticket, do not fall back to a different path, remove any partial worktree it created, and report the failure together with the branch or path it attempted.

While reading the tickets during preparation, watch for signs of a non-green sequence as part of that same reading — an incidental judgement, not a separate check stage, and never a reason to dispatch a sub-agent. Signals include a tail ticket shaped as an integration-verification step that is blocked by many sibling tickets, or ticket text that mentions a shared branch or promises green only on the final ticket. On any suspicion, stop the whole run and report the suspected sequence; do not start executing any ticket.

This detection is a semantic reading and can miss. A missed non-green sequence is caught by the existing failure handling: a ticket that cannot go green ends up frozen with its branch preserved, so the loss is bounded by that single ticket's run.

Skip every ticket in any other triage status — an ineligible status is not a validation failure and does not stop the run: never execute the ticket, let its dependent descendants freeze under the frontier rule, and list the skipped tickets and the dependency chains they interrupt in the final report. Treat all excluded statuses alike — never wait on `needs-info`, never notify `ready-for-human`; exclusion is the entire handling.

Exception: a ticket whose status is `done` is not part of the skipped set. Treat it as a candidate completed blocker; the resumption check verifies whether it counts as complete.

Treat a ticket as complete only when its changes are present on the integration branch. Do not infer completion from filename order or checked boxes alone.

## Resume

Re-invoking this skill on the same tickets directory resumes the run; there is no separate resumption entry point.

The completion mark is a non-authoritative index: when the mark disagrees with the repository history, the repository wins. The recorded SHAs are the means of cross-verifying the mark against the repository.

During preparation, apply the resumption check to every ticket whose status is `done`: verify that the recorded integration commit is in the integration branch history.

- Verification passes: the ticket is complete and counts as a completed blocker. Do not re-dispatch it.
- Verification fails: stop processing that ticket and report it. Do not redo it automatically — a failed verification means something outside this workflow intervened, and no automatic handling is safe.

Tickets without a `done` status — including work left half-finished by an interrupted run — are dispatched normally in topological order, each on a new branch from the current tip of the integration branch. Never reuse a leftover branch from an earlier run and never delete it; list leftover branches in the final report among the preserved branches requiring manual follow-up.

## Schedule

Execute tickets strictly one at a time, in topological order of the `Blocked by` dependency graph. Never start a ticket while another ticket is still being implemented or integrated.

The **frontier** is every incomplete ticket whose blockers are integrated and verified. After every integration, recalculate the frontier and pick exactly one frontier ticket as the next unit of work.

For each ticket:

- create a dedicated branch from the current tip of the integration branch
- start a completely fresh sub-agent on that branch
- never reuse a sub-agent context for another ticket

The dedicated branch exists to preserve the failure scene: a failed ticket's branch is kept for human takeover.

## Delegate

Give each sub-agent the ticket reference, parent spec when available, branch, and base commit.

Use a task equivalent to:

> Explicitly invoke the `implement` skill using this host's native syntax for `<TICKET_REFERENCE>`.
> Implement exactly this ticket on the assigned branch.
> The branch starts from `<BASE_COMMIT>`, which contains all completed blockers.
> Do not implement sibling, downstream, or unrelated work.
> Do not create or merge branches.
> Commit the result and return the commit SHA and verification results.

Do not pass implementation transcripts from earlier tickets. The repository state, ticket, and spec are the source of truth.

When this run uses a worktree, start every delegated agent that writes or commits — including each ticket's sub-agent and the bounded-fix sub-agent — with that worktree as its working directory, so those commits cannot land in the primary working tree. Give ticket and parent-spec references as absolute paths resolved before entering the worktree, so gitignored ticket directories such as `.scratch/` stay readable regardless of the sub-agent's working directory. The ticket sub-agent's acceptance-checkbox ticks land on that same original absolute ticket path, independent of its worktree cwd.

## Integrate

Accept a result only when:

- the `implement` skill completed successfully
- the working tree is clean
- a commit was produced from the assigned base
- required checks passed

Here, "the working tree" is the active git working tree for ticket work: the shared worktree when this run uses one, otherwise the primary working tree. A dirty primary working tree on the worktree path does not by itself fail this check when the active worktree is otherwise clean.

Integrate the accepted ticket branch into the integration branch. After the integration:

1. run affected tests and typechecking
2. confirm the integration branch remains green
3. record the ticket commit
4. write the ticket's completion mark
5. recalculate the frontier and continue with the next ticket

The orchestrator writes the completion mark, and only after the ticket is integrated and verified. The implementing sub-agent never writes the completion mark; the sub-agent only ticks the ticket's acceptance criteria checkboxes while implementing, and checked boxes are never a completion signal.

To write the mark, set the ticket's `Status:` line to `done` and append one completion record line to the ticket's Comments section in exactly this format:

`Integrated: <integration-commit-SHA> (base: <base-commit-SHA>)`

Like the sub-agent's checkbox ticks, this write always targets the ticket's original absolute path in the tickets directory, independent of whether this run uses a worktree.

The integration commit is the integration branch tip after this ticket's integration; the base commit is the commit the ticket's branch was created from. Keep the record to this single fixed line: resumption and the integration-level review parse it mechanically.

If the failed attempt leaves uncommitted changes in the working tree, commit them as-is onto the failed attempt's branch first — a snapshot, never an edit — so the failure scene survives on that branch and the working tree returns clean before the next dispatch.

If a ticket's sub-agent fails, re-dispatch the ticket exactly once to a completely fresh sub-agent. The re-dispatch delegation must include a failure summary taken from the failed sub-agent's completion report: the approaches already attempted, why they failed, and the directions that must not be tried again. The re-dispatch follows the same rules as a first dispatch: create a new dedicated branch from the current tip of the integration branch, and never continue work on the failed attempt's branch — a clean start avoids anchoring on the half-finished attempt, and the failure summary is how the failed experience carries over. Keep the failed attempt's branch.

If the re-dispatched attempt also fails, the ticket freezes; never re-dispatch it again. Do not integrate it or start its descendants; preserve both failed attempts' branches and list them in the final report for manual cleanup, then continue with frontier tickets that do not depend on it.

## Finish

Repeat scheduling, delegation, and integration until every ticket completes or the frontier is empty.

Do not ask the user to choose ticket order.

If incomplete tickets remain with an empty frontier, report the failed or unresolved blockers.

### Integration-level review

Run the integration-level review only after every ticket in the set is integrated. If any ticket failed, froze, or was skipped, skip the review — a partial aggregate cannot be checked against the full parent spec, and its fixed point may not even be derivable. Record the skipped review and the reason in the final report, then proceed to the final verification.

The review looks for exactly two classes of cross-ticket integration blind spots and nothing else:

- **Spec coverage** — whether the aggregate change covers the parent spec completely.
- **Cross-ticket consistency** — duplicated implementations, naming divergence, and contradictory implicit assumptions across tickets.

Do not re-review single-ticket internal quality: every ticket already passed its own review during implementation, and the integration-level review never repeats it.

Each pass runs as one completely fresh sub-agent; the orchestrator never runs a review pass itself.

Both passes review the diff between the integration branch tip and one shared fixed point.

Derive the fixed point mechanically: collect the base SHA from every done ticket's completion record and take the earliest ancestor among them, judged by repository ancestry. The fixed point is the start of the whole ticket set's execution; resumption never moves it — never use the moment of the latest re-invocation as the fixed point.

**Spec coverage pass.** Give the sub-agent the fixed-point diff and the parent spec, and instruct it to check the aggregate change the way the `code-review` skill's Spec axis does. That skill is the Spec brief's single home; do not copy the brief into the delegation. When the ticket set has no parent spec, fall back to the aggregate ticket intent — the aggregation of every ticket's What to build and acceptance criteria — and never ask the user for a spec.

**Cross-ticket consistency pass.** Give the sub-agent the fixed-point diff and the list of integrated tickets, and use a brief equivalent to the following, with `<N>` replaced by the ticket count:

> This diff is the combined work of `<N>` tickets, each implemented by an isolated agent that could not see the others' work in progress. Report ONLY cross-ticket integration issues:
>
> (a) duplicated implementations — the same logic, helper, or concept implemented more than once by different tickets;
>
> (b) naming divergence — the same domain concept named differently across tickets;
>
> (c) contradictory implicit assumptions — places where two tickets' changes disagree about behaviour, data shape, or invariants, even though they merged cleanly.
>
> For each finding, cite the files/hunks and the tickets involved, and classify it as either "bounded fix" (a single mechanical fix action) or "needs decision". Do NOT report single-ticket internal quality, style opinions, or anything a per-ticket review already covers. Under 400 words.

### Findings and fixes

Route every finding from either pass by its disposition:

- **Bounded fix** — attributable to a single mechanical fix action, such as merging a duplicated implementation or unifying a divergent name: dispatch one fresh sub-agent to apply every bounded fix and commit the result. When this run uses a worktree, that fix sub-agent uses the same worktree working-directory binding as ticket sub-agents.
- **Needs decision** — anything that needs a new ticket or a product or architecture decision, and any spec-level gap: do not fix it; record it in the final report with its impact scope.

The orchestrator never fixes findings itself: code changes stay out of the main agent, review fixes included.

After the fix sub-agent completes, re-run each affected review pass once as verification. Every finding that verification produces goes into the final report and never into another fix; the fix loop is capped at exactly one round.

### Final verification and report

After the review and its fixes:

- run the repository's full required checks in the shared worktree when this run uses one, otherwise in the primary working tree
- verify the integration branch is green

Return:

- completed tickets and their commits
- failed or frozen tickets
- dependency paths interrupted by failures
- tickets skipped by status filtering and the dependency chains they interrupt
- integration-level review findings and their disposition: fixed, or needing decision with impact scope
- final verification results
- final integration commit
- the integration branch holding this run's completed work
- preserved branches requiring manual follow-up

Do not declare success unless every ticket is complete and the integration branch is green.

### Shared worktree cleanup

When this run created a worktree, remove it only after final verification has completed when that path is reached. Also remove it whenever this invocation ends earlier after the worktree was created — including when Prepare stops after settlement because ticket reading, dependency-graph validation, or non-green-sequence detection fails, and when Finish stops without reaching final verification. Removal deletes only the extra working directory: it never deletes a branch or a commit, and it never changes the primary working tree's current checkout. If removal fails, do not roll back any integration; list the leftover worktree path in the final report among the items requiring manual follow-up.
