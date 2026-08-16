---
name: emergent-implement-tickets
description: "Implement a dependency graph of tickets strictly one at a time with fresh sub-agents and verified integration."
disable-model-invocation: true
argument-hint: "<tickets-directory>"
---

# Emergent Implement Tickets

Implement every ticket in the provided directory according to its `Blocked by` dependencies.

This workflow only handles ticket sets that keep the integration branch green after every single ticket's integration. A ticket sequence that does not promise per-ticket green — the shared-branch extreme of an expand-contract split, where intermediate tickets stay red by design and only the final integration-verification ticket promises green — is outside this workflow; hand it to a manual per-ticket path.

Act only as the orchestrator: schedule, delegate, integrate, and verify. Never implement ticket behaviour or modify code in the main agent.

The run is unattended: never ask the user anything while the run is in progress. Decide within this skill's rules, and record anything that needs a human decision in the final report.

Each ticket must be handled by one fresh sub-agent that explicitly invokes the `emergent-implement` skill for exactly that ticket.

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

### Related Draft ADR input

For the local tracker layout, resolve the parent spec as the `spec.md` in the feature directory immediately containing the supplied tickets directory.

A missing parent spec, an absent Related Draft ADRs section, or an empty section is an empty finalization list and does not prevent the ticket workflow from running.

Only machine-generated Related Draft ADR rows form the finalization set; headings, prose, active rows, and other content never enter it.

Here, the explicit repository root is the repository root of the active git working tree for ticket work.

Before ticket dispatch, validate the complete non-empty list against the explicit repository root: preserve row order and reject repeated identities, repeated paths, paths outside the root, and multiple lifecycle folders.

This validation runs after the pre-existing same-task file changes gate has completed and every transplanted file is in place: run before that, it reads a transplanted draft ADR as a missing lifecycle folder and stops the whole run before dispatch.

A zero lifecycle folder identity is already complete — and excluded from the finalization list without counting as validation failure — when that identity's path once existed in the current branch history and a commit on that branch deleted it; without such history, zero folders remain a validation failure that stops the entire run before implementation starts.

Resolve every listed ADR path as repository-root-relative; reject absolute paths and resolve accepted paths from the explicit repository root.

A validation failure stops the entire run before implementation starts; never deduplicate, invent a lifecycle state, or defer this validation to finalization. Checking the current branch history for a recorded deletion of that identity is factual verification for the zero-folder exception above, not guessing and not deferral.

The lifecycle folders on the integration branch are the resume authority.

On resume, and when collecting drafts for the single finalization call, resolve each ADR identity on the integration branch through exactly one lifecycle folder: `draft/` is pending; `active/` and `archived/` are already complete and never re-run; a zero-folder identity whose path once existed in the integration branch history and was deleted by a commit on that branch is already complete and never re-run; zero folders without that deletion history, or multiple folders, are invalid and must be reported without inventing a state.

### Prepare questions

Before dispatching any ticket, ask the user once whether this run uses a single shared git worktree for ticket git operations, together with a suggested branch name for the new integration branch.

- **Worktree chosen** — create a branch with the settled name, forked from the branch that was current when Prepare started, and use it as this run's integration branch; create and check out exactly one shared git worktree on that integration branch; perform every ticket dedicated-branch operation — create, checkout, commit, and integrate — inside that worktree, and never switch the primary working tree's branch for ticket work; a dirty primary working tree is allowed on this path.
- **Worktree declined** — ask whether the integration branch is the branch that was current when Prepare started, or a new branch forked from it with a suggested name; the primary working tree must be clean before any ticket is dispatched, or Prepare stops with a reportable error and dispatches nothing; perform ticket dedicated-branch operations in the primary working tree.

When asking the user is impossible, do not invent a worktree or a new integration branch: settle without asking as **Worktree declined** with the integration branch equal to the branch that was current when Prepare started, still requiring that primary working tree to be clean before dispatch, and record this cannot-ask fallback in the final report.

Every path still gives each ticket its own dedicated branch that merges into the settled integration branch.

Never create a separate worktree for an individual ticket.

Suggest branch names from the tickets/spec directory's basename plus a prefix that fits the work; the normative example is a `.scratch/foo-bar` directory suggesting `feature/foo-bar` for a new-feature ticket set. Other prefixes are acceptable as long as the basename survives when it can be derived; invent a name outright when it cannot. Check a candidate name for collisions before presenting it whenever a cheap Git query can answer.

Choose the worktree's disk path and every branch name so none collides with anything that already exists and every name stays human-readable; no fixed naming format is required beyond that.

**Pre-existing same-task file changes.** Ask this last, after the worktree question above is settled: this is the Prepare question group's final question.

The settled integration branch already exists when this gate runs, and so does the shared worktree on the path that chose one: settling the question above is what creates them.

Scan the primary working tree — the tree Prepare started in — for candidates, and never scan a shared worktree in its place: a worktree created moments ago holds no uncommitted change, so following the worktree choice here would yield no candidate at all on the very route this gate exists for. The candidates are every uncommitted change in that primary working tree, one candidate per file and untracked files included; a gitignored path is never a candidate.

When the scan finds no candidate at all, skip this whole gate: present no list and ask nothing.

Separate the candidates into two kinds:

- **Named by the parent spec** — an uncommitted ADR file that the parent spec's Related Draft ADRs section names is settled as a pre-existing same-task file change by that listing alone: transplant it without asking, and list it in its own area of the presented list, marked as transplanted automatically.
- **Everything else** — judge each remaining candidate against this ticket set's own task and place it in exactly one of three groups: **suggested to transplant**, **suggested to leave**, and **undecided**.

A missing parent spec, an absent Related Draft ADRs section, or an empty section leaves the first kind empty and sends every candidate through that judgement; it never fails this gate.

A candidate the judgement cannot settle belongs in **undecided** and stays there: never resolve it into **suggested to transplant** or **suggested to leave**, which would hide that uncertainty inside a list that reads as already decided.

Present all three groups to the user, visually separated from each other, and never merge two of them or leave one out — an empty **undecided** group is shown as empty. Give every candidate one line saying what changed in it, and never a full diff.

Show a numbered action matrix; never require the user to retype a file path. On a **Worktree chosen** run, each non-locked candidate's action is **Transplant** or **Leave**; on a **Worktree declined** run, it is **Transplant** or **Stash**.

Lock every parent-spec-named ADR to **Transplant**. Default **suggested to transplant** to **Transplant** and **suggested to leave** to the other action available on this path; give **undecided** no default.

Offer these direct choices: **Transplant all**; **accept the proposed actions** and decide only candidates still undecided; apply the other available action to every adjustable candidate; adjust individual numbered actions; or stop without changing any candidate or stash state.

Advance only on the user's explicit ruling over that list: this is a user ruling point, not a notification.

Before changing any candidate or stash state, show the exact final **Transplant**, **Stash**, and **Leave** lists that apply to this path and advance only on explicit confirmation.

The worktree choice stays fixed after this action matrix is shown; no candidate action reopens it.

One exemption: when the parent-spec-named kind took every candidate and all three judgement groups are empty, there is nothing to rule on — present the automatically transplanted files as a notification and continue without asking.

Asking here is a Prepare question and stays compatible with the unattended run: that contract bans questions once the run is in progress, not this file-by-file ruling taken before any ticket is dispatched.

When asking the user is impossible, transplant no candidate at all — the ADR files the parent spec names included — and leave every candidate where the scan found it.

That leaves the cannot-ask fallback above untouched: the primary working tree it settles on must still be clean before any ticket is dispatched.

Nothing moves on a ruling nobody gave — this gate exists precisely because the judgement behind it can be wrong — so a candidate no one could rule on stops such a run through that clean-tree demand instead of riding along unconfirmed.

**Candidate custody.** Apply the confirmed actions by the path settled above:

- **Worktree chosen** — leave every **Leave**-assigned candidate untouched in the primary working tree: ticket work happens inside the shared worktree, so those candidates affect nothing in this run.
- **Worktree declined** — before creating the pre-existing same-task file changes transplant commit, put every **Stash**-assigned candidate into one separately identifiable stash containing exactly those approved paths, including approved untracked paths.

The stash scope is the user's explicitly confirmed **Stash** list; never add another path merely to make the tree clean.

Verify that the stash identifier resolves, that it contains every approved path and no other path, that those paths are no longer dirty or untracked in the primary working tree, and that every **Transplant**-assigned candidate is unchanged.

Create the pre-existing same-task file changes transplant commit only after every stash verification above passes. On any failure, stop state-changing work, preserve every stash artifact, and report each candidate's verified or unresolved location.

The stash becomes user-owned as soon as it is created: never apply, pop, drop, restore, replace, or re-stash it during this run.

If the user restores it during the run and that makes the active working tree — the primary working tree on this path — dirty, the existing clean-tree verification stops and reports the run; do not undo the user's action.

Commit every **Transplant**-assigned file — the confirmed selection plus the ADR files locked above — onto this run's settled integration branch and leave no copy behind: each transplanted change is gone from the primary working tree as an uncommitted change afterwards, and lives only in the pre-existing same-task file changes transplant commit. When the settled integration branch is the branch that was current when Prepare started, that same branch receives them and transplanting degrades to an in-place commit.

Choose how to make that commit freely: this prompt requires only that the transplanted files end up committed on the settled integration branch, and names no command, tool, or skill for getting them there.

Make that commit without asking the user anything: the ruling above already settled its scope, and no remaining detail of it is worth another interruption.

Immediately after that commit succeeds and before later Prepare validation, record each transplanted path's post-transplant primary-working-tree fingerprint: existence, file type and mode, content, and index and working-tree status.

Before ticket reading, verify every candidate against its confirmed custody: each **Transplant**-assigned change is committed on the settled integration branch with no uncommitted copy in the primary working tree; each **Stash**-assigned change is in the verified stash; each **Leave**-assigned change is unchanged in the primary working tree. Dispatch nothing until every candidate passes.

Once every question above is answered, or settled by the cannot-ask fallback, ask the user nothing else for the rest of this invocation; anything that still needs a human decision goes into the final report instead. These Prepare questions run before the run is in progress, so asking them here is compatible with staying unattended afterward.

Re-invoking this skill within the same agent session, on the same tickets directory, reuses the settled integration branch and worktree choice without asking again; if the chosen worktree's directory is missing, recreate it checked out on the same integration branch without asking.

A different tickets directory, or a new agent session, runs the questions above again — this skill keeps no external record of a previous run's answers.

The pre-existing same-task file changes gate is outside that reuse: every invocation runs it again in its own Prepare, from a fresh scan, and never carries over the ruling an earlier invocation took.

The two answers differ in kind. The settled integration branch and worktree choice is a setting — asked once and then fixed for the run, which is what makes a second invocation right to reuse it. The candidate list is no such setting but a reading of what the primary working tree holds at that moment, and an interrupted run is exactly the case where that tree has moved on since, so an inherited ruling would rule on files that are no longer the ones in front of the user.

Keep no record of which candidates the user selected: nothing of that ruling survives for a later re-run to read.

If creating the settled integration branch or shared worktree fails at the worktree question's settlement — the moment that creates them — treat it as a terminal Prepare failure: dispatch no ticket, do not fall back to a different path, remove any partial worktree it created, and report the failure together with the branch or path it attempted.

While reading the tickets during preparation, watch for signs of a non-green sequence as part of that same reading — an incidental judgement, not a separate check stage, and never a reason to dispatch a sub-agent. Signals include a tail ticket shaped as an integration-verification step that is blocked by many sibling tickets, or ticket text that mentions a shared branch or promises green only on the final ticket. On any suspicion, stop the whole run and report the suspected sequence; do not start executing any ticket.

This detection is a semantic reading and can miss. A missed non-green sequence is caught by the existing failure handling: a ticket that cannot go green ends up frozen with its branch preserved, so the loss is bounded by that single ticket's run.

Skip every ticket in any other triage status — an ineligible status is not a validation failure and does not stop the run: never execute the ticket, let its dependent descendants freeze under the frontier rule, and list the skipped tickets and the dependency chains they interrupt in the final report. Treat all excluded statuses alike — never wait on `needs-info`, never notify `ready-for-human`; exclusion is the entire handling.

Exception: a ticket whose status is `done` is not part of the skipped set. Treat it as a candidate completed blocker; the resumption check verifies whether it counts as complete.

Treat a ticket as complete only when its changes are present on the integration branch. Do not infer completion from filename order or checked boxes alone.

### Rollback after the pre-existing same-task file changes transplant commit

When Prepare fails after the pre-existing same-task file changes transplant commit is already made, restore only the transplanted changes to their pre-gate uncommitted state; leave every approved stash untouched.

Every terminal Prepare failure after the pre-existing same-task file changes transplant commit was created successfully triggers this rollback. This includes every ticket-reading and extracted-graph validation failure — duplicate identifiers, missing blockers, and dependency cycles — plus non-green sequence detection and Related Draft ADR list validation.

Creating the shared worktree or integration branch and creating or verifying an approved stash all finish before the pre-existing same-task file changes transplant commit exists, so their failures never trigger this rollback.

When the pre-existing same-task file changes transplant commit's own execution fails, there is no successful commit to roll back: skip the three phases and locate and verify every candidate before any cleanup. Preserve the shared worktree whenever it holds a candidate's only verified copy or any candidate's custody is unresolved; report every verified location and every unresolved candidate.

This is the one rollback in this skill, and it does not soften the rule that a failure scene is preserved rather than undone: a failed ticket's branch is a scene kept for a human to read, while the pre-existing same-task file changes transplant commit is not a scene at all — it is the user's own uncommitted work moved somewhere else.

Roll back in exactly three phases, and never reorder them:

Before phase 1, verify that the settled integration branch still points at the pre-existing same-task file changes transplant commit; if not, stop without writing back or moving the branch, and report the expected and observed tips.

1. **Verify every path first** — confirm that every path due to be written back still matches its recorded post-transplant primary-working-tree fingerprint.
2. **Write back only once every path has passed** — put every transplanted file's content back in the primary working tree; on an in-place transplant the content never left, so this phase has nothing to write back.
3. **Undo the pre-existing same-task file changes transplant commit last** — return the settled integration branch to the tip it had before that commit.

That order is the only one on which "never overwrite, stop loudly" holds: while the pre-existing same-task file changes transplant commit still stands, every transplanted change has one copy that is certain to be findable, whereas undoing it before the paths are written back would leave every path not yet written reachable through the reflog alone.

A verification that finds any path no longer matching its recorded fingerprint — another session in the same repository rewrote a file of that name, say — stops the rollback there and reports it: write back no file, do not undo the pre-existing same-task file changes transplant commit, and never overwrite what that path holds now.

That stop's end state is the state the rollback began from: every transplanted change still lives intact in that pre-existing same-task file changes transplant commit on the settled integration branch.

Report that stop with all three of the end state above, every path that no longer matches, and the pre-existing same-task file changes transplant commit's identifier: the user takes the leftover from there by hand, and cannot without those three.

A rollback that runs to the end leaves the same change in exactly one place — the primary working tree — and no commit copy of it anywhere: a transplanted change is moved rather than copied, and moving it back keeps that true. On the branch that was current when Prepare started, this is what keeps an unimplemented draft ADR from staying on it for good.

Rolling back deletes no branch and removes no shared worktree: both were settled before this gate ran and neither is something this gate moved, so their cleanup stays with the existing failure handling and shared-worktree cleanup rules.

The rollback itself is not atomic: an interruption partway through — the agent dying, the user aborting — leaves a half-finished state that needs a human to sort out, and the report says which phase it stopped in.

Because undoing the commit comes last, an interruption during verification or write-back always leaves the pre-existing same-task file changes transplant commit standing, so every transplanted change stays certain to be findable.

That guarantee covers an interrupted rollback only, never a completed one: a completed rollback has already undone the pre-existing same-task file changes transplant commit, and the changes are back in the primary working tree.

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

> Explicitly invoke the `emergent-implement` skill using this host's native syntax for `<TICKET_REFERENCE>`.
> Implement exactly this ticket on the assigned branch.
> The branch starts from `<BASE_COMMIT>`, which contains all completed blockers.
> Do not implement sibling, downstream, or unrelated work.
> Do not create or merge branches.
> Commit the result and return the commit SHA when the ticket completes, or when a user-decision blocker leaves material ruling-independent work; when no such work exists, produce no commit — never fabricate one.
> In every case, return the `Outcome:` line and verification results.

Do not pass implementation transcripts from earlier tickets. The repository state, ticket, and spec are the source of truth.

When this run uses a worktree, start every delegated agent that writes or commits — including each ticket's sub-agent and the bounded-fix sub-agent — with that worktree as its working directory, so those commits cannot land in the primary working tree. Give ticket and parent-spec references as absolute paths resolved before entering the worktree, so gitignored ticket directories such as `.scratch/` stay readable regardless of the sub-agent's working directory. The ticket sub-agent's acceptance-checkbox ticks land on that same original absolute ticket path, independent of its worktree cwd.

## Integrate

Every sub-agent return begins with exactly one `Outcome:` line — `Outcome: completed`, `Outcome: user-decision blocker`, or `Outcome: failed` — and that line alone routes the result: a completed result follows the acceptance rules below, a failed result follows the failed-attempt rules below, and a user-decision blocker result follows the user-decision blocker section — a pending human ruling is not an implementation failure and never enters the failed-attempt re-dispatch.

Accept a result only when:

- the `emergent-implement` skill completed successfully
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

### user-decision blocker

A user-decision blocker return means the ticket needs a human ruling: the sub-agent has already completed and verified every unaffected part, and its report carries each pending decision — the concrete question, why it belongs to the human side of the decision boundary, and the unfinished work waiting on it — plus the verification performed on the completed unaffected work, and either an unblocked-work commit SHA or the explicit statement that no material ruling-independent work existed.

When the report names an unblocked-work commit, integrate it only when:

- it derives from the assigned base
- the working tree is clean
- the relevant checks pass

After integrating it, confirm the integration branch remains green.

After this verification succeeds, append one unblocked-work integration record to the ticket's Comments section in exactly this format:

`Integrated unblocked work: <integration-commit-SHA> (base: <base-commit-SHA>)`

The integration commit is the integration branch tip after integrating the unblocked work; the base commit is the assigned base from which that attempt derived. Keep the record to this single fixed line: it preserves the provenance needed by the integration-level review without presenting the ticket as complete. From that moment every later ticket branch starts from an integration tip that already contains the shared progress.

When the report states that no material ruling-independent work existed, there is nothing to integrate: never demand or fabricate a commit.

If any of those checks fails, or the integration branch does not stay green, do not share the commit: restore the integration branch to its pre-integration tip when needed, keep the ticket's branch as the preserved scene, list it among the preserved branches requiring manual follow-up, and still record the pending decision below.

An integrated unblocked-work commit is shared progress, never completion: do not set the ticket's `Status:` line to `done`, do not write a completion record, do not count the ticket as a completed blocker, and keep its dependency descendants out of the frontier.

Record the unresolved state on its existing carriers, and nowhere else:

- set the ticket's `Status:` line to `ready-for-human`
- append each pending decision, exactly as the report states it, to the ticket's Comments section
- when unblocked work was integrated, keep its fixed integration record above in Comments; integration-branch history carries the work itself

Like the completion mark, these writes target the ticket's original absolute path in the tickets directory.

After recording the blocker — with or without an integrated commit — recalculate the frontier and continue with frontier tickets that do not depend on it until no frontier ticket remains. Pending decisions wait for the final report; they never interrupt the remaining autonomous work.

Resumption is decision-backed: the human writes the ruling into the parent spec when one exists, otherwise into the ticket, and returns the ticket's `Status:` line to `ready-for-agent`. The next run dispatches it like any other ticket from the current tip of the integration branch — a tip that already contains every integrated unblocked-work commit; never reuse the earlier attempt's branch, and never re-integrate or cherry-pick progress already on the integration branch.

## Finish

Repeat scheduling, delegation, and integration until every ticket completes or the frontier is empty.

Do not ask the user to choose ticket order.

If incomplete tickets remain with an empty frontier, report the failed or unresolved blockers.

### Integration-level review

Run the integration-level review only after every ticket in the set is integrated. If any ticket remains incomplete when scheduling stops, record both the spec coverage and cross-ticket consistency passes as **skipped**, each with a concrete reason identifying the partial aggregate. Never relabel either pass as **not applicable**. A partial aggregate cannot be checked against the full parent spec, and its fixed point may not even be derivable; proceed to the final verification after recording both skipped results.

Decide review applicability from the number of tickets in the complete set validated from the supplied tickets directory during Prepare. This count includes all verified `done` tickets from before this invocation; never use the number dispatched in this invocation, the number still incomplete, or the current Frontier size.

For a complete aggregate, select the passes mechanically:

- **Two or more tickets** — run both the spec coverage and cross-ticket consistency passes.
- **Exactly one ticket with a parent spec** — run only the spec coverage pass. Do not dispatch a cross-ticket consistency reviewer; record that pass as **not applicable** because no second ticket exists to compare.
- **Exactly one ticket without a parent spec** — dispatch no integration-level reviewer. Record the spec coverage pass as **not applicable** because there is no aggregate coverage basis independent of that ticket, and the cross-ticket consistency pass as **not applicable** because there is no second ticket to compare.

For review applicability, reuse the parent-spec presence resolved during Prepare. Do not run another repository search or compare the parent spec and ticket for semantic equivalence.

A **not applicable** pass is a normal terminal result. It satisfies the integration-level review terminal-results gate and does not by itself block final verification, Related Draft ADR finalization, or full success.

A **skipped** pass remains an abnormal result caused by a partial aggregate; the existing finalization and success restrictions remain unchanged.

Every single-ticket path continues to final verification after its review passes reach terminal results, and the integration branch must remain green.

The review looks for exactly two classes of cross-ticket integration blind spots and nothing else:

- **Spec coverage** — whether the aggregate change covers the parent spec completely.
- **Cross-ticket consistency** — duplicated implementations, naming divergence, and contradictory implicit assumptions across tickets.

Do not re-review single-ticket internal quality: every ticket already passed its own review during implementation, and the integration-level review never repeats it.

Each applicable pass runs as one completely fresh sub-agent; the orchestrator never runs a review pass itself.

Every applicable pass reviews the diff between the integration branch tip and one shared fixed point.

Derive the fixed point mechanically: collect the base SHA from every done ticket's completion record and every unblocked-work integration record, then take the earliest ancestor among them, judged by repository ancestry. The fixed point is the start of the whole ticket set's execution; resumption never moves it — never use the moment of the latest re-invocation as the fixed point.

**Spec coverage pass.** When applicable, give the sub-agent the fixed-point diff and the parent spec, and instruct it to check the aggregate change the way the `code-review` skill's Spec axis does. That skill is the Spec brief's single home; do not copy the brief into the delegation. For a complete set of two or more tickets with no parent spec, fall back to the aggregate ticket intent — the aggregation of every ticket's What to build and acceptance criteria — and never ask the user for a spec.

**Cross-ticket consistency pass.** When applicable, give the sub-agent the fixed-point diff and the list of integrated tickets, and use a brief equivalent to the following, with `<N>` replaced by the ticket count:

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

### Related draft ADR finalization

Related draft ADR finalization is a build closeout, not a ticket, and never delegates to emergent-implement.

Begin related draft ADR finalization only after every ticket is integrated and verified with no failed, frozen, skipped, interrupted, or unverifiable ticket, both integration-level review passes and their bounded-fix verification have reached terminal results, required checks are green on the integration branch, and no remaining finding leaves aggregate implementation ground truth unsettled.

If the finalization gate fails, invoke no ADR operation: leave every lifecycle state unchanged and report every row with the same gate-failure reason and all applicable blocking findings, if any.

Use the settled active working tree for every ADR finalization; never create an additional worktree for ADR finalization.

For every listed ADR, record its initial lifecycle state. An `active/` or `archived/` identity, or a zero-folder identity completed by the deletion-history exception, is already complete and is not passed into the call. An invalid zero-folder or multiple-folder re-check is a failed identity: do not invent a state, keep the integration branch unchanged, verify the active working tree is clean, and continue only when that verification succeeds.

Collect every still-pending Related Draft ADR into one call.
When no draft remains pending, invoke no ADR operation and skip finalization-branch creation.

Create one human-readable collision-free finalization branch from the current integration tip that covers that single call.
Declare to the operation that the disposition scope is Git-recoverable and isolated from unrelated changes.
Pass `disposition_scope_git_recoverable_and_isolated` as true on that call.
Invoke the `emergent-adr` skill's complete finalize-draft-adrs operation once with every pending draft path for this closeout; never split that call into lower-level revise and promote-draft-to-active calls, and never invoke the operation once per draft.
Ordering and exclusivity among the drafts belong entirely to that operation.

Accept the finalization branch only when all three hold: the operation returned a readable summary listing every included draft's terminal state; every draft in that summary is one of the three legal terminals deleted, promoted, or unresolved; and the branch diff changes files only inside the `draft/`, `active/`, and `archived/` lifecycle directories (directory-boundary criterion — adds, deletes, moves, frontmatter, and body edits inside those three directories are all allowed).
When those three hold, merge the finalization branch into the integration branch even if some drafts are unresolved.

For a failed mechanical acceptance, keep the finalization branch unmerged; stage and commit any uncommitted or untracked changes as-is as a failure-scene snapshot, never edit, discard, or carry them into another branch; continue only after that snapshot is durable, the integration branch is restored to its pre-attempt tip, and the active working tree is verified clean.

If branch creation or checkout fails, do not invoke the ADR operation: keep attempted false and return to the integration branch through the same restoration and clean-tree gate before continuing.

Record branch creation or checkout failure as a branch-stage error, operation or result-commit failure as an operation-stage error, failure-scene snapshot commit failure or return-to-integration or clean verification failure as a recovery-stage error, and merge or merge-abort failure as a merge-stage error.

On merge failure, never resolve a merge automatically: abort the merge, preserve the finalization branch, and continue only after the integration branch is restored to its pre-attempt tip and the active working tree is verified clean.

If failure-scene snapshotting, merge abort, branch restoration, or clean-tree verification cannot complete, stop remaining ADR finalization, preserve the current branch, active working tree, and available reports for manual recovery, and do not attempt worktree cleanup.

For every ADR included in the closeout, report initial and final lifecycle state plus its terminal state from the summary and that draft's end-to-end report. Record branch, operation, merge, and recovery stages once at the single-call level; every stage records its state, artifact identifiers, and error.

Set attempted to true exactly when the single finalize-draft-adrs call begins; while attempted is false, operation terminal status and structured report path are null and a reason is required.

When attempted is true, retain current-run terminal status and report path when produced; if either is absent because the operation failed, record the operation-stage error.

On resume, never search or reconstruct historical OS-tmp reports; use only current-run artifacts.

After the finalize-draft-adrs call finishes (or is skipped because nothing was pending), perform only read-only mechanical validation and reporting; do not run another integration review, dispatch bounded fixes, or start another write-capable stage.

The final report records the shared-worktree cleanup outcome and any preserved branch or worktree path.

Return:

- completed tickets and their commits
- failed or frozen tickets
- dependency paths interrupted by failures
- tickets skipped by status filtering and the dependency chains they interrupt
- every pending decision, aggregated: the recorded decision from each `ready-for-human` ticket, the dependency chains waiting on it, and where the ruling belongs
- integrated unblocked-work commits and their still-incomplete source tickets
- every file the pre-existing same-task file changes transplant commit transplanted out of the primary working tree
- the pre-existing same-task file changes transplant commit's identifier
- the approved stash's identifier, exact file list, and whether that identifier still resolves at report time; if it does not resolve, report only that fact and never infer whether the user applied, popped, or dropped it
- each integration-level review pass's **completed**, **not applicable**, or **skipped** status and the concrete reason for that status
- integration-level review findings and their disposition: fixed, or needing decision with impact scope
- final verification results
- final integration commit
- the integration branch holding this run's completed work
- related draft ADR finalization records and the full-success or partial-completion verdict
- preserved branches requiring manual follow-up

Do not declare success unless every ticket is complete and the integration branch is green.

Report partial completion whenever any finalization draft ends unresolved or otherwise fails to reach a completed terminal during this run and is not already complete by lifecycle state. Report full success only when every draft is either already complete by lifecycle state or reached a completed terminal (deleted or promoted) during this run — never when any draft remains unresolved.

### Shared worktree cleanup

After normal finalization or a losslessly recovered failure, remove the shared worktree only after finalization and its read-only checks finish; if lossless recovery failed, do not remove it, and if normal cleanup fails, report the leftover path without rolling back integrations.

Before any early shared-worktree removal, require the candidate custody gate to have passed. Preserve the shared worktree when it holds a candidate's only verified copy or any candidate's custody is unresolved, and report why it was preserved.

When this run created a worktree, remove it only after final verification has completed when that path is reached. For a run with ADR finalization, complete that stage and its read-only checks before this removal. Except for a finalization stopped after failed lossless recovery, which preserves its shared worktree and Git state for manual recovery, also remove it whenever this invocation ends earlier after the worktree was created — including when Prepare stops after settlement because ticket reading, dependency-graph validation, or non-green-sequence detection fails, and when Finish stops without reaching final verification. Removal deletes only the extra working directory: it never deletes a branch or a commit, and it never changes the primary working tree's current checkout. If removal fails, do not roll back any integration; list the leftover worktree path in the final report among the items requiring manual follow-up. Record the cleanup outcome.
