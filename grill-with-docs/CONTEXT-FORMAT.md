# CONTEXT.md Format

## Structure

```md
# {Bounded Context Name}

{One or two sentence description of what this bounded context is and why it exists.}

## Language

**Order**:
{A one or two sentence description of the term}
_Avoid_: Purchase, transaction

**Invoice**:
A request for payment sent to a customer after delivery.
_Avoid_: Bill, payment request

**Customer**:
A person or organization that places orders.
_Avoid_: Client, buyer, account
```

## Rules

- **Be opinionated.** When multiple words exist for the same concept, pick the best one and list the others as aliases to avoid.
- **Retire a term by removing it whole — never leave a deprecated remnant.** When a term is renamed or retired, delete its entry outright; do not keep the old entry, and do not mark it `deprecated` / `已棄用`. CONTEXT.md reflects the **current state**, not history — a retired term left in the file (even flagged deprecated) is read by the next agent as still-current vocabulary and pollutes its context. The evolution trail belongs to the ADR supersession chain (the dedicated record for decisions), not to the glossary. If the old word still appears in the body of an immutable `active`/`archived` ADR that cannot be edited, carry it as an `_Avoid_` alias on the **current** term's entry — so a reader resolves the old word back to the current one — rather than keeping a standalone old entry for it.
- **Flag conflicts explicitly.** If a term is used ambiguously, call it out in "Flagged ambiguities" with a clear resolution.
- **Keep definitions tight.** One or two sentences max. Define what it IS, not what it does.
- **Show relationships.** Use bold term names and express cardinality where obvious.
- **Only include terms specific to this project's bounded context.** General programming concepts (timeouts, error types, utility patterns) don't belong even if the project uses them extensively. Before adding a term, ask: is this a concept unique to this bounded context, or a general programming concept? Only the former belongs.
- **Group terms under subheadings** when natural clusters emerge. If all terms belong to a single cohesive area, a flat list is fine.
- **Write an example dialogue.** A conversation between a dev and a domain expert that demonstrates how the terms interact naturally and clarifies boundaries between related concepts.

## Single vs multi-bounded-context repos

**Single bounded context (most repos):** One `CONTEXT.md` at the repo root.

**Multiple bounded contexts:** A `CONTEXT-MAP.md` at the repo root lists the bounded contexts, where they live, and how they relate to each other:

```md
# Context Map

## Bounded Contexts

- [Ordering](./src/ordering/CONTEXT.md) — receives and tracks customer orders
- [Billing](./src/billing/CONTEXT.md) — generates invoices and processes payments
- [Fulfillment](./src/fulfillment/CONTEXT.md) — manages warehouse picking and shipping

## Relationships

- **Ordering → Fulfillment**: Ordering emits `OrderPlaced` events; Fulfillment consumes them to start picking
- **Fulfillment → Billing**: Fulfillment emits `ShipmentDispatched` events; Billing consumes them to generate invoices
- **Ordering ↔ Billing**: Shared types for `CustomerId` and `Money`
```

The skill infers which structure applies:

- If `CONTEXT-MAP.md` exists, read it to find bounded contexts
- If only a root `CONTEXT.md` exists, single bounded context
- If neither exists, create a root `CONTEXT.md` skeleton at the moment the bounded context is bound at the opening — title, a one-sentence description, and an empty Language section with zero terms — so any printed path always points at a real file. Terms are added only later, as the user ratifies them.

When multiple bounded contexts exist, infer which one the current topic relates to. If unclear, ask.
