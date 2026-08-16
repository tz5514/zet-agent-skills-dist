---
name: emergent-design
description: Shared engineering philosophy of emergent design. Use when deciding what humans must settle before implementation versus what should emerge through code, tests, and integration feedback; when deciding which long-lived or one-shot carrier should own a piece of information, including whether an ADR is an appropriate carrier at all; or when another skill needs the emergent-design model.
---

# Emergent Design

Emergent design treats implementation as a design-and-learning stage, not transcription of a completed blueprint. Humans settle the commitments only they can own; the rest of the design forms through code, tests, and integration feedback, kept on course by an engineering control system. This skill is all reference — principles and causal relationships to judge with, not a procedure to run.

## Two failure extremes

Emergent design rejects both ends of the spectrum:

- **Complete up-front design** is defensive. It can raise the floor, but it lowers the ceiling on implementation-time judgment, and its detailed plans start going stale the moment real code diverges.
- **Unconstrained improvisation** — vibe coding — loses predictability, understandability, and sustained maintainability.

## Layers of sayability

Design knowledge has layers of sayability. Some of it can be stated reliably before any code exists; much of it becomes sayable only once implementation evidence — real code, real callers, real tests, real integration — exists. Forcing the unsayable to be settled up front produces guesses dressed as decisions, and guesses are what go stale. Implementation is where that missing design knowledge is learned.

Absence of code is not evidence that future code cannot express a decision. At planning time, judge each carrier by what it will be able to express once it exists, not by what happens to exist today.

## The human-decision boundary

A decision needs humans up front when it creates a shared commitment or requires human authority, risk ownership, or cross-boundary coordination:

- externally observable or caller-visible contracts
- cross-ticket dependencies and shared seams
- non-negotiable product, compatibility, security, or legal constraints
- choices the user explicitly fixes
- testing seams that need prior agreement, so intended behavior can be exercised and the TDD/implementation feedback loop can begin

Prior agreement covers the testing seams needed to exercise intended behavior; private and internal replacement seams remain free to emerge. Labels do not decide: calling a choice "architecture", "prototype", or "implementation detail" does not by itself make it an up-front human decision. A choice that creates none of the commitments above remains eligible to form through the codebase, tests, and implementation feedback.

## The engineering control system

Engineering disciplines keep free implementation space inside the intended context; they are what separates emergent design from vibe coding. Each earns its place through a causal role:

- **Vertical slices and short feedback loops** expose real behavior, integration constraints, and design information incrementally, so evidence replaces up-front guessing.
- **TDD through agreed testing seams** keeps observable behavior executable and stable while internal structure keeps emerging and being refactored.
- **Deep modules and narrow interfaces** contain complexity, minimize what callers must know, and preserve the freedom to replace internal design.
- **Ubiquitous language and `CONTEXT.md`** keep local implementation choices aligned with the shared domain model.
- **Selective ADRs** preserve only the lasting decision context that none of the long-lived carriers below can appropriately hold.

## Information-carrier responsibility

Locality and single authority govern where information ultimately lives: give each meaning one authoritative home in the closest durable carrier that can make it evident.

### Long-lived carriers — ground truth

Long-lived carriers maintain ground truth, each in its own territory:

- **Code** owns concrete implementation and every implementation intent expressible through structure, types, naming, and behavior. When the code makes information evident, no comment is needed.
- **Tests** own the observable behavior the user stories require — the durable record of it, in place of a duplicate long-lived user-story document.
- **Interfaces** own the caller contract: everything a caller must know to use a module correctly.
- **Local comments** own only local intent that code cannot make evident.
- **`CONTEXT.md`** owns the shared domain language.
- **ADR** enters consideration only for lasting decision context that none of the carriers above can appropriately carry — and such a candidate must still pass independent necessity review.

### One-shot carriers — goals in transit

- **The spec** records all ratified needs and design and forwards them to implementers. It is the required handoff layer from ratified conversation into implementation. A spec may instruct that specific long-lived carriers must eventually hold specific information; fulfilling that instruction completes the spec's one-shot handoff responsibility.
- **Tickets** split the spec's work into the current round's units.

Both describe goals and intended work only. Before, during, and after implementation — even when the code momentarily matches them — ground truth lives exclusively in the long-lived carriers.
