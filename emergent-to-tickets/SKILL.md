---
name: emergent-to-tickets
description: Break a plan, spec, or the current conversation into tracer-bullet tickets published to the configured tracker, by loading the official to-tickets prompt in full as the runtime baseline process and the shared emergent-design skill as the philosophy that process judges ticket content by.
disable-model-invocation: true
---

This skill wraps the official `to-tickets` skill: at runtime it loads that skill's complete `SKILL.md` as the baseline process — through this runtime's formal skill loading, or failing that from the official baseline installed beside this wrapper — and loads the shared `emergent-design` skill as the philosophy the tickets that process produces are judged by. It carries no copy of either.

## Authority loading

Both authorities load completely into the current context before the baseline process starts. Either load failing ends the run with no ticket published, not even a partial set: a description, a summary, a paraphrase, or memory never stands in for either authority.

1. Ask this runtime's formal skill-loading mechanism for the skill whose canonical name is `to-tickets`, and take the complete body it returns as the baseline process. A description, a summary, a catalog entry, or any other partial result is not a load, and the list of available skills already in this context decides nothing about whether the skill exists — an official baseline a user has to name by hand is kept out of that list on purpose.
2. When this runtime offers no formal skill-loading mechanism, or that mechanism will not load `to-tickets`, read `../to-tickets/SKILL.md` resolved from this skill's own installed directory. That sibling of this wrapper is the only place the fallback looks: no runtime skill root is interpreted, no working directory is consulted, and no search of the filesystem for a file of that name is ever run.
3. Take that sibling as the baseline only after parsing its frontmatter and finding a canonical `name` of exactly `to-tickets`, and only after reading its entire contents into the current context. A matching directory name, display name, or description establishes no authority, and a body that cannot be read to its end has not been loaded.
4. If neither the formal load nor the sibling read puts the complete official `to-tickets` body in this context, stop here, report that the baseline authority could not be loaded in full, and end the run without publishing a ticket. That report names the authority that is missing, not the locations this skill tried.
5. Formally load the complete `emergent-design` skill through this runtime's skill-loading mechanism. If the load fails — the skill is missing or incomplete — stop here, report the load error, and end the run without publishing a ticket.
6. Execute the baseline process with the remaining sections of this skill applied as constraints on its ticket content. The baseline remains authoritative for process flow and publication behaviour; a ticket is publishable only when it also satisfies every applicable requirement below.

## The run's source

Every source the baseline accepts stays acceptable here: the conversation on its own, a plan on its own, or a reference the user passes in. This skill adds no document a caller must produce first, and a ticket names a spec only when a spec was genuinely this run's source.

A `spec.md` becomes this run's parent spec in one of two ways: the user hands this run that file, or this session has just written one whose location this run already knows and the user turns from it straight to splitting tickets. A `spec.md` that merely sits somewhere in the repository is not this run's parent spec, and no search goes looking for a candidate — a file nobody pointed at says nothing about the work this run was asked to split, so promoting one would hand every ticket upstream requirements the user never set.

## The parent spec in every ticket

When this run has a parent spec, a ticket is finished only once that ticket, read on its own, sends its implementer to that spec and tells them to read it for the requirements this ticket sits under. Every published ticket meets that on its own, because that is how each one gets picked up: one file, one fresh implementer, with no sibling ticket and no summary of the batch in front of them.

The shape is this run's call — a link, a path inside a sentence, the whole spec or the parts of it this ticket answers to — whatever a reader holding that single file can actually follow, given how the spec reads and what the tracker renders.

This sits on top of what a ticket already says, not in place of it. What the ticket delivers, how its implementer will know it is done, and which tickets gate it all stay on the ticket; the spec is where its upstream requirements were settled, not a substitute for saying what this one piece of work is.

## Where the philosophy applies

The `emergent-design` skill loaded above is the only statement of the philosophy this run uses; this skill keeps no second copy, summary, or checklist of it, and applies it as loaded when judging the sentences below.

- **What a ticket binds.** The loaded philosophy identifies which choices need human authority; it does not answer them. A ticket's text binds its implementer only where the conversation ratified the choice, where a declared authority or a verified unrelaxable constraint fixes it, or where the ticket restates one of those as work an implementer can execute and check. That restating chooses nothing new: wording a settled decision so an implementer can act on it and verify it is not the same as picking an answer nobody reached.
- **What stays out of a ticket.** The modules, classes, files, data structures, internal seams, and responsibility placements the conversation only explored stay out of the ticket's requirements, however thin a ticket looks without them: the implementer settles those against real code, tests, and integration feedback once the work is under way.
