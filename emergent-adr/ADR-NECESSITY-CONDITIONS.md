# ADR necessity conditions (ADR 必要性條件)

This document is the sole authority for the judgment semantics of the ADR necessity conditions and the shared evidence principles. Its consumers are the main agent's ADR necessity self-check and the independent `check-should-write-adr` review, which judge whether a candidate decision merits long-term preservation as an ADR. Each loads this document as the only source of the condition semantics: the condition content must not be copied, rewritten, or summarized, and neither memory nor an older version may stand in for it. ADR quality review is not a consumer: it reviews an already-written ADR without the conversation that formed the decision, which these conditions require as evidence.

This document defines only what is judged and what it takes to pass. How each consumer obtains evidence, at which point it reviews, its input and output formats, its sub-agent orchestration, and its flow ordering are maintained by each consumer's own contract and are not written into this document.

Each condition is expressed through four sections: "Core concept", "Positive evidence required", "Explicitly non-qualifying boundaries", and "Judgment requirements". These four sections govern the content of the judgment; they are a reading structure, not a form to fill back in: filling every section, or surface similarity to some case, never constitutes grounds for passing.

## Shared rules

The following rules apply to the judgment of every condition:

- **Judge only on verifiable facts.** A judgment may rest only on established facts: information the user provided, the codebase, still-effective ADR decisions, and other verifiable material. Reasonable derivation from established facts is allowed, but unestablished facts, reactions, behaviors, or predictions must not be fabricated to make up qualification.
- **When uncertain, the condition does not pass.** When evidence is insufficient, certainty cannot be reached, or only a possibility of risk exists, the condition fails. A wrongly accepted ADR stays in the repository long-term and keeps accruing quality-review, supersession-scan, and reading-maintenance costs; a wrongful rejection has a clear recovery path (re-judge after the facts are supplemented, or hand it to the user for a ruling), so the default is strict.
- **Each condition establishes its own causal reason.** Every condition must have its own causal account: point to candidate-specific established facts and explain why those facts make this condition hold. Restating the condition name, applying an abstract slogan, or leaning on another condition's pass does not constitute a reason.
- **After the prerequisite checks pass, evaluate every condition in full.** Once a candidate passes its prerequisite checks and enters condition judgment, every condition defined at that time must be evaluated in full, and all failing items must be reported at once; the remaining conditions must not be skipped after the first failure. A condition may be marked unevaluated only when a prerequisite check blocked entry into condition judgment.
- **Only passing every condition qualifies.** A candidate meets ADR necessity only when every condition has positive evidence and passes; failing any single condition means the candidate does not qualify.

## Condition: Hard to reverse

### Core concept

This condition holds only when, by the capabilities verifiable at review time, the party responsible for the change cannot — through actions it alone has the authority to control, over a transition with a definite end point — reliably eliminate the dependencies, legacy state, and ongoing obligations the original choice left behind, or cannot keep satisfying existing requirements it has no authority to relax on its own. It looks at whether the transition can reliably end, not at how large the work appears.

### Positive evidence required

- Established facts show a dependency, legacy state, or ongoing obligation that the party responsible for the change cannot eliminate on its own, or an existing requirement it has no authority to relax on its own. The established facts usable here are limited to information the user provided, the codebase, still-effective ADR decisions, and other verifiable material.
- A business impact falls within this condition's judgment scope only when those sources have already established it as a constraint the project must obey.
- Released externally visible features and behaviors count as existing requirements the party responsible for the change has no authority to relax on its own, until a product or design role with decision authority explicitly allows them to change or degrade.

### Explicitly non-qualifying boundaries

- File count, code volume, refactor scope, estimated effort, or the mere need to redo work never suffice to prove hard to reverse; if existing methods can reliably transform mechanically and verify that all existing requirements are still satisfied, no amount of engineering effort qualifies.
- Release by itself does not protect internal implementation choices: as long as replacing the internal implementation can still reliably prove the externally visible features and behaviors unchanged, having been released does not constitute hard to reverse.
- Insufficient evidence, inability to prove that reversal is easy, or a mere possibility of risk must not be treated as qualifying; customer reactions, the company's tolerance, dependents' behavior, future usage scale, or other unestablished facts and predictions must not be fabricated.

### Judgment requirements

- Hard-to-reverse arising purely from architecture, migration, and verification capability is judged by the AI, tooling, alternatives, and verification capabilities verifiable at review time; do not presume future capabilities will improve, and do not make the current verdict permanent — when capabilities change, the same decision may receive a different result.
- If preserving the existing requirements would have to rely on semantic migration whose completeness cannot be proven mechanically plus broad manual verification, judge by the core concept whether that transition already exceeds the scope of change that can reliably converge.
- When judging a candidate decision not yet written, judge by its explicitly ratified applicable scope: the requirements, dependencies, and verification capabilities that scope can directly establish once the decision lands normally, without inventing usage scale, external dependents, or implementation choices not yet decided; when judging an existing ADR, judge primarily by the implementation, requirements, and dependencies that exist now, and adopt the same pre-write perspective when the decision is not yet implemented.

## Condition: Surprising without context

### Core concept

This condition holds only when a reasonable future maintainer, lacking the candidate decision's necessary context, would take another recognizable approach as the default or correct direction and could therefore mistake the current deliberate choice for a problem to fix. It cares about defied expectations and the risk of mistaken correction, not about whether the artifact preserves the full discussion history.

### Positive evidence required

- Identify the recognizable alternative approach a reasonable future maintainer would take, and produce verifiable established facts proving that this expectation is actually grounded; reasonable inference from confirmed facts is allowed.

### Explicitly non-qualifying boundaries

- Merely not knowing the full rationale, lacking a complete explanation, or wanting to understand the backstory never suffices to qualify.
- Model intuition without supporting evidence, personal preference, or guesswork must not fill in the grounds for "a reasonable maintainer would expect a different approach".

### Judgment requirements

- The judgment must spell out this causal chain: which necessary context is missing, which alternative approach a reasonable maintainer would therefore take as the default or correct direction, and how that puts the current deliberate choice at risk of being corrected as a problem; missing any link means the condition does not hold.

## Condition: real trade-off

### Core concept

This condition holds only when the user, in the conversation that formed the decision, weighed differing benefits and drawbacks among explicitly raised viable options and made a choice. A trade-off means the weighing that actually happened while the decision was formed, not which alternatives the final choice could objectively be compared against.

### Positive evidence required

- At least one alternative and its benefits and drawbacks were explicitly raised in the conversation that formed the decision and actually entered the user's consideration.
- Before ratification, the conversation explicitly presented the viable options and each one's significant benefits and drawbacks, and the user afterwards clearly chose one of the options; the user is not required to personally restate which benefits and drawbacks they accepted or gave up.
- The viable options each retain a significant benefit the other cannot provide at the same time — one weighty enough to affect the decision — so that choosing one option genuinely gives up the other option's benefit.
- A benefit or drawback counts as significant enough to form a real trade-off only when, in the conversation that formed the decision, it was linked to a goal, need, constraint, risk, or evaluation criterion the user had previously expressed, or the user explicitly stated it as something they value.
- An alternative counts as a viable option forming a real trade-off only when the conversation that formed the decision already contains confirmed facts sufficient to support that it does not violate known, non-negotiable constraints; completing a prototype or full validation beforehand is not required.

### Explicitly non-qualifying boundaries

- An objectively viable alternative that was only discovered after the fact and never raised in the conversation does not count as that decision's trade-off.
- If one option is no worse than the other on every known significant dimension and better on at least one, the two do not constitute a trade-off.
- The user asking the agent to judge or choose on their behalf does not count as the user clearly choosing, nor does it prove the user weighed the options' benefits and drawbacks; regardless of whether the question is objectively critical, the option the agent ultimately settled on must not by itself satisfy this condition.
- When neither basis of significance exists (a link to decision grounds the user previously expressed, or the user's explicit statement of valuing it), do not infer on your own that an objective difference carries decision significance for the user.
- An alternative that can only be imagined in theory, with no facts yet supporting it, does not suffice as a viable option.

### Judgment requirements

- The judgment must locate the weighing that actually happened in the conversation that formed the decision: which viable options and significant benefits and drawbacks were explicitly presented, and where the user clearly settled on one of them.
- Having earlier handed the judgment or choice to the agent does not permanently disqualify the decision from forming a real trade-off; as long as the user, after the options and their significant benefits and drawbacks have been explicitly presented, finally and clearly selects one of the options, the minimum evidence bar for "the choice was made by the user" is met; the other bars — viability, significance, and mutual forgoing — must still each hold.
