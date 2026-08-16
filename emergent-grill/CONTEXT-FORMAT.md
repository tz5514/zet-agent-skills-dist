# CONTEXT.md Format

## Structure

```md
# {Context Name}

{One or two sentence description of what this context is and why it exists.}

## Language

**Invoice**:
A request for payment sent to a customer after delivery.
_Avoid_: Bill, payment request

**Backorder**:
An order accepted while the item is out of stock, to be fulfilled once stock returns.
```

Both example entries are normative shapes: `Invoice` has real alternative names, so it lists them under `_Avoid_:`; `Backorder` has none, so its entry ends at the definition — no `_Avoid_:` line at all.

## Rules

- **A definition is the minimal semantic boundary that tells this concept apart from its neighbours.** Every clause must be needed to recognize the concept or to distinguish it from another; nothing enters a definition because extra background looks helpful. One or two sentences is the natural result of this bar, not a quota to fill.
- **Behavior, state, or relationship belongs in a definition exactly when the concept cannot be recognized or distinguished without it.** `Backorder` above is unrecognizable without its out-of-stock state; a distinguishing behavior is part of what the concept is, so there is no "describe what it is, never what it does" rule.
- **Content that does not disambiguate lives in its own carrier.** Operating procedures, implementation arrangements, variable and code identifiers, concrete values, temporary strategies, and decision rationale belong to code, tests, interfaces, local comments, ADRs, or a one-shot spec — never to a definition, however helpful they would look next to it.
- **Be opinionated.** When multiple words exist for the same concept, pick the best one as the headword and list the others under `_Avoid_`.
- **`_Avoid_:` is a fixed field marker — the same exact literal in every document language.** A glossary written in Chinese, English, or any other language marks the field as `_Avoid_:`, so readers and tools identify it mechanically across languages.
- **Every `_Avoid_` value is an alternative name: a word or short naming phrase someone might use to refer to the same concept the entry defines.** Values carry no behavioral prohibitions, no misunderstandings to correct, no reasons, no caveats — no prose of any kind. A note that needs a sentence is not an alternative name.
- **When the concept has no real alternative name, omit the whole `_Avoid_:` line.** Never an empty value, a placeholder, or an alias invented to keep the field present.
- **Retire a term by removing its entry whole — never leave a `deprecated` remnant.** The glossary reflects the current language, not its history; the evolution trail belongs to the ADR supersession chain. When the old name still appears in the body of an immutable `active`/`archived` ADR, carry that old name as an `_Avoid_` value on the current term's entry — an old name is exactly an alternative name a reader must resolve to the current one.
- **Only include terms specific to this project's context.** General programming concepts (timeouts, error types, utility patterns) don't belong even if the project uses them extensively. Before adding a term, ask: is this a concept unique to this context, or a general programming concept? Only the former belongs.
- **Group terms under subheadings** when natural clusters emerge. If all terms belong to a single cohesive area, a flat list is fine.

## Single vs multi-context repos

**Single context (most repos):** One `CONTEXT.md` at the repo root.

**Multiple contexts:** A `CONTEXT-MAP.md` at the repo root lists the contexts, where they live, and how they relate to each other:

```md
# Context Map

## Contexts

- [Ordering](./src/ordering/CONTEXT.md) — receives and tracks customer orders
- [Billing](./src/billing/CONTEXT.md) — generates invoices and processes payments
- [Fulfillment](./src/fulfillment/CONTEXT.md) — manages warehouse picking and shipping

## Relationships

- **Ordering → Fulfillment**: Ordering emits `OrderPlaced` events; Fulfillment consumes them to start picking
- **Fulfillment → Billing**: Fulfillment emits `ShipmentDispatched` events; Billing consumes them to generate invoices
- **Ordering ↔ Billing**: Shared types for `CustomerId` and `Money`
```

The skill infers which structure applies:

- If `CONTEXT-MAP.md` exists, read it to find contexts
- If only a root `CONTEXT.md` exists, single context
- If neither exists, create a root `CONTEXT.md` skeleton **at binding time** (title + one-sentence description + empty Language section, zero terms) — never lazy-create on first term ratification; the binding block must always print a path that already points at a real file

When multiple contexts exist, infer which one the current topic relates to. If unclear, ask.
