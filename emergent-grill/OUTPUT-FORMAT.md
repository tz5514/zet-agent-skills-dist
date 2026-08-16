# Output Format — fixed templates for grill's recurring output blocks

Every fixed-process output block a grill round emits — opening binding, the ADR necessity self-check, documentation results, verification results, supersession scan reports, the pending-items map, closing blocks — uses a fixed template from this file. Nothing here is improvised at runtime. The templates serve two audiences at once: the user reading the conversation live (high-frequency blocks stay short and quiet; rare events are loud and structured), and any post-hoc reviewer of the transcript, which identifies each block mechanically by its label line.

Read this file during the opening load step (with CONTEXT.md and the ADRs) and keep it on hand for the whole round.

## General rules (apply to every block)

1. **The label line is the machine contract.** Each block starts with `### ` + emoji + label text; that whole line-start structure is the identification anchor a transcript reviewer locks onto. The block's content goes on the lines after the heading — never merged into the heading itself, even when the content is one short sentence.
2. **Label language** follows the language layering rules at the end of this file.
3. **Links.** In conversation output, every file and folder path is a markdown hyperlink (workspace-relative). When pointing at a specific decision, attach a `#L` line anchor — the line number at output time; these anchors are point-in-time and going stale later is accepted. This linking rule applies **only to conversation output**: ADR prose rules are governed by `/emergent-adr` operations and are not restated here.
4. **Designators.** Supersession-report rows are coded S1, S2, …; option lists are coded A1, A2, … — so the user can verbally pinpoint one row or option ("roll back S1").
5. **Batch boundary.** Whichever of 🧭 / ✅ / 🔍 / 📣 a cycle actually emits is emitted once per documentation-gate cycle: when one cycle writes several files or triggers several checks, the results merge into a single block of each kind. The interview-time documentation gate runs no supersession scan, so 🔍 / 📣 do not appear then (see the 🔍 block's own note); the batch rule governs whichever blocks a cycle does emit.
6. **User-visible wording** says 「決策」 (decision) when naming an atomic decision — never 「原子」 (atom) as a standalone noun ("atomic" is the adjective; "decision" is the noun).
7. **Block order within a gate cycle is fixed:** 🧭 → 📝 → ✅ → 🔍 → 📣 — at interview time only 🧭 → 📝 → ✅ appear, since the interview-time gate defers supersession scanning to the draft promotion flow.

## The eleven blocks — zh-TW literal set (source version)

These literals were visually tuned by the user word by word. At runtime, copy them exactly — do not rephrase, do not improvise. `{…}` placeholders are instantiated at output time.

### 1. 📍 本輪 grill 綁定 — once, at the opening

_Turn role: non-blocking notification block._

Emitted right after the opening three-state load sequence (the folder counts feed the last line).

```
### 📍 本輪 grill 綁定
- bounded context：{名稱}（[{資料夾路徑}]({連結})）
- CONTEXT.md：[{路徑}]({連結})
- ADR：[{docs/adr/ 路徑}]({連結})（active {N}＋archived {M}＋draft {K}）
```

There is no "not yet created" special case: binding creates the CONTEXT.md skeleton on the spot, so the printed path always points at a real, clickable file.

### 2. 🧭 ADR 必要性自檢 — after every ratified answer, first block of the gate cycle

_Turn role: the per-condition variant and the one-line not-initiating variant are **non-blocking notification blocks**; the authority-failure variant is a **user ruling point** (the gate stops and waits until the authority input is repaired, ending the turn)._

Per-condition variant — condition judgment ran:

```
### 🧭 ADR 必要性自檢
- 候選：{候選決策範圍，一句}
  - ✅ **{條件名稱}**：{候選特定短理由}
  - ❌ **{條件名稱}**：{候選特定短理由}
  - 結論：{發起是否應寫 ADR 檢查／不發起——未全數通過}
```

One-line variant — no candidate decision, or a prerequisite check blocked entry into condition judgment:

```
### 🧭 ADR 必要性自檢
不發起——{一句原因}
```

Authority-failure variant — the necessity-conditions authority could not be loaded or reloaded (stop and wait):

```
### 🧭 ADR 必要性自檢
權威載入失效——{一句原因}；本答的必要性判斷維持未評估，停下等權威修復後補跑
```

#### ADR necessity condition display names (zh-TW)

Human-facing condition titles only — copy the display name exactly; judgment semantics stay in the loaded necessity-conditions authority only. Match each authority condition by its English identity, in authority order:

- `Hard to reverse` → **難以反悔**
- `Surprising without context` → **脫離脈絡會令人意外**
- `real trade-off` → **真實取捨**

The condition lines are generated at output time from the conditions the loaded authority document currently defines — one line per condition, in the authority's order; the condition count is never hardcoded here. For each line, match the condition's English identity to its display name: a zh-TW environment copies from the zh-TW list above and an English environment copies from the English list below, without translating between these two hand-maintained sets; any third-language environment translates the matching English display name on the fly under Language layering below. Never paste the authority heading verbatim onto the human-facing block, glue bilingual authority titles onto the output, or use the zh-TW display name as a third-language translation source. Reading CONTEXT.md is not required to render these names (it may still record vocabulary cross-references for maintainers). The Chinese colon sits outside the bold (`**{條件名稱}**：`) so the bold close-marker parses. A condition that was never evaluated never gets a ❌ line — the two one-line variants exist for exactly that. In the per-condition variant, the candidate line is the parent list item; every ✅/❌ condition line and the conclusion line are nested two spaces beneath it — the same shape for one or many candidates. When one answer ratifies several candidates, repeat that nested group per candidate inside this single 🧭 block, using parent labels `候選 1`, `候選 2`, … (a space before the numeral). When exactly one candidate is judged, keep the unnumbered parent label `候選` as in the fence above — do not emit `候選 1`. The short reasons are transparency only: they carry no evidence weight and never authorize a write; when the independent review returns, its result is reported alongside this block's content, never replacing it.

### 3. 📝 Bounded context 文件歸檔 — after every ratified answer

_Turn role: non-blocking notification block._

```
### 📝 Bounded context 文件歸檔
- 新增 ADR：[ADR {id}]({連結})「{標題}」
- 修改本輪 ADR：[ADR {id}]({連結}) ＋{改動摘要}
- 新增 CONTEXT.md 詞條：「[{詞}]({CONTEXT.md 連結}#L{詞條行號})」
- 修改 CONTEXT.md 既有詞條：「[{詞}]({連結}#L{行號})」（{改動摘要}）
```

List only the situations that actually occurred in this cycle (the four lines above are the complete case set). When none of the four occurred, use the single-line variant instead:

```
### 📝 Bounded context 文件歸檔
不歸檔——{一句理由}，留在對話；要留請自行記錄
```

### 4. ✅ 交付檢查 — per gate cycle that wrote files, when foreground delivery checks pass

_Turn role: non-blocking notification block._

```
### ✅ 交付檢查
{交付結果清單，如「ADR {id}：CONTEXT.md 詞彙拍板預檢通過（未跑完整品質審查與推翻掃描）；CONTEXT.md：自足性驗證通過」}
```

Heading and content stay on separate lines — the pass sentence is never merged into the H3 heading, keeping the visual structure consistent with every other block. ADR entries report the CONTEXT.md glossary-approval preflight pass — full ADR quality review and supersession scan have not run, so this is never worded as a completed `produce` acceptance; CONTEXT.md-only entries keep this skill's local self-sufficiency wording. The pass line's language follows the layering rules below. Rejected term candidates, if any, may be appended as a parenthetical note at the end of this block — see SKILL.md's documentation gate for the candidate-handling flow.

### 5. 🔍 ADR 決策推翻掃描 — emitted only when a supersession scan actually ran and reported; the interview-time documentation gate defers scanning to the draft promotion flow and runs none, so it does not emit this block (template retained for non-interview or future use)

_Turn role: non-blocking notification block._

```
### 🔍 ADR 決策推翻掃描
[ADR {id}]({連結})、[ADR {id}]({連結}) vs active ADR ×{N} → 無推翻
```

When something was superseded, the line ends with `→ 推翻 {N} 筆決策（詳下表）` instead. Multiple trigger ADRs in one cycle are all listed on the same single line. `{N}` counts only `active/` candidate files. **When `active/` holds no ADR files, the scan is skipped and this block is not emitted at all** — there is no zero-candidate variant of this line to print.

### 6. 📣 ADR 決策推翻報告 — only when something was actually superseded, immediately after 🔍

_Turn role: non-blocking notification block — presenting it is the review moment; it does not end the turn._

```
### 📣 ADR 決策推翻報告
| 代號 | 舊決策 | 新決策 | 推翻情形簡述 | 範圍與處置 | 信心 |
|---|---|---|---|---|---|
| S1 | [ADR {id} 決策 {決策id}]({連結}#L{行號}) | [ADR {id} 決策 {決策id}]({連結}#L{行號}) | {≤30字自然語言} | 部分決策被推翻：ADR 文件續留於 [active]({連結}) | 高 |
| S2 | … | … | … | 全部決策皆被推翻：ADR 文件封存至 [archived]({連結}) | 低，優先審 |

不認同任一筆 → 說「撤回 S{n}」，兩側對稱復原。（未要求撤回即視為同意，之後不再提醒；撤回權不設時限。）
```

Low-confidence rows always write 「低，優先審」 in the confidence column — loud, for priority review. The heading carries no trigger names: the 🔍 line directly above already lists them, and row-level attribution lives in the 「新決策」 column. The footer sentence's wording may be slightly adjusted, but its meaning is locked: presenting the report is the review moment — no rollback requested means consent, the markings are not reminded about again, and the rollback right never expires.

### 7. 🚨 自足性驗證回報違規 — when the verifier reports a violation; the heading carries the re-review verdict

_Turn role: the false-positive variant is a **user ruling point** (it stops and waits for the user's ruling, ending the turn); the true-violation variant is a **non-blocking notification block** (auto-fixed, the block is just the visible trail)._

False-positive variant (stop and wait for the user's ruling):

```
### 🚨 自足性驗證回報違規——複核判定：誤報
- 決策：[ADR {id} 決策 {決策id}]({連結}#L{行號})
- 回報內容：{驗證者的違規描述}
- 複核理由：{為何判誤報，一句}
- **停下等你確認**：同意誤報就繼續，不同意我就修
```

True-violation variant (auto-fixed without stopping; this block is the visible trail):

```
### 🚨 自足性驗證回報違規——複核判定：真違規，已修正
- 決策：[ADR {id} 決策 {決策id}]({連結}#L{行號})
- 違規內容：{解析不了的指涉}
- 修正：{保意義改寫的內容}；已重跑驗證 → 通過
```

The true-violation variant's layout may be slightly adjusted; its meaning is locked: the violation, the meaning-preserving fix, and the re-verification result are all visible.

### 8. 🛑 自足性修正觸及決策內容 — hard rule: stop and ask

_Turn role: user ruling point — it stops and waits for the user's ruling, ending the turn._

```
### 🛑 自足性修正觸及決策內容，停下等你拍板
- 決策：[ADR {id} 決策 {決策id}]({連結}#L{行號})
- 卡點：{為何不是改寫指涉就能解決，一句}
- 你的選項：
  - **A1**：決策內容不變，照此改寫：「{建議改寫}」
  - **A2**：決策內容確實要改 → 走正常決策變更
```

### 9. 🗺️ 待拍板議題 — one line before each question

_Turn role: non-blocking notification block (it accompanies, but is not itself, the turn's single question)._

```
### 🗺️ 待拍板議題
{項目A}、{項目B}（卡 {前置}）｜下一問 → {主題}
```

### 10. 🎯 收尾前最後候選議題 — when you think you have no more questions

_Turn role: non-blocking notification block — it presents candidates and silence means "go ahead, ask them"; it does not itself halt for a required reply (the design questions it leads to are the ruling points)._

```
### 🎯 收尾前最後候選議題
1. {問題}
   建議：{答案}（依據：codebase／web／低信心）
   不可推導：{為何不能從其他候選的答案導出，一句}
2. …
（可改序、補項、或說「夠了，收尾」；沉默＝照問）
```

No "(N/cap)"-style counters — they carry no information the user can act on. The at-most-three-candidates rule itself lives in SKILL.md and is unchanged.

### 11. 🏁 收尾檢核 — at the end of each round

_Turn role: user ruling point — the session may not close until the user ratifies or explicitly defers every listed item._

```
### 🏁 收尾檢核
最後一答歸檔：{📝 內容或「無待歸檔」}
未拍板清單：
1. {項目} — 請拍板，或明說「擱置、之後決」
（全部處理完才可收尾）
```

## English literal set (canonical; the fallback when no language is specified)

Translated from the zh-TW source set. The emoji + H3 + field structure is invariant across languages — only the label text is translated. At runtime, copy these exactly; improvised translation is forbidden. For a third language, translate on the fly using this English set as the source; terminology consistency is not guaranteed there.

Each block's **turn role** (user ruling point vs non-blocking notification block) is annotated on its zh-TW source block above and is identical here — the turn role is a property of the block, not of the language.

### 1. 📍 This grill round's binding

```
### 📍 This grill round's binding
- bounded context: {name} ([{folder path}]({link}))
- CONTEXT.md: [{path}]({link})
- ADR: [{docs/adr/ path}]({link}) (active {N} + archived {M} + draft {K})
```

### 2. 🧭 ADR necessity self-check

Per-condition variant — condition judgment ran:

```
### 🧭 ADR necessity self-check
- Candidate: {candidate decision scope, one sentence}
  - ✅ **{condition name}**: {candidate-specific short reason}
  - ❌ **{condition name}**: {candidate-specific short reason}
  - Conclusion: {initiating check-should-write-adr / not initiating — not every condition passed}
```

One-line variant — no candidate decision, or a prerequisite check blocked entry into condition judgment:

```
### 🧭 ADR necessity self-check
Not initiating — {one-sentence reason}
```

Authority-failure variant — the necessity-conditions authority could not be loaded or reloaded (stop and wait):

```
### 🧭 ADR necessity self-check
Authority load failure — {one-sentence reason}; this answer's necessity judgment stays unevaluated; stopping until the authority is repaired, then re-running this self-check
```

#### ADR necessity condition display names (English)

Human-facing condition titles only — copy the display name exactly; judgment semantics stay in the loaded necessity-conditions authority only. Match each authority condition by its English identity, in authority order:

- `Hard to reverse` → **Hard to reverse**
- `Surprising without context` → **Surprising without context**
- `real trade-off` → **real trade-off**

Condition lines are generated at output time from the conditions the loaded authority document currently defines — one line per condition, in the authority's order; the condition count is never hardcoded here. For each line, match the condition's English identity to its display name: an English environment copies from the English list above and a zh-TW environment copies from the zh-TW list, without translating between these two hand-maintained sets; any third-language environment translates the matching English display name on the fly under Language layering below. Never paste the authority heading verbatim onto the human-facing block, glue bilingual authority titles onto the output, or use the zh-TW display name as a third-language translation source. Reading CONTEXT.md is not required to render these names (it may still record vocabulary cross-references for maintainers). A condition that was never evaluated never gets a ❌ line. In the per-condition variant, the candidate line is the parent list item; every ✅/❌ condition line and the conclusion line are nested two spaces beneath it — the same shape for one or many candidates. When one answer ratifies several candidates, repeat that nested group per candidate inside this single 🧭 block, using parent labels `Candidate 1`, `Candidate 2`, …. When exactly one candidate is judged, keep the unnumbered parent label `Candidate` as in the fence above — do not emit `Candidate 1`.

### 3. 📝 Bounded context documentation

```
### 📝 Bounded context documentation
- New ADR: [ADR {id}]({link}) "{title}"
- Modified this-round ADR: [ADR {id}]({link}) + {change summary}
- New CONTEXT.md term: "[{term}]({CONTEXT.md link}#L{term line})"
- Modified existing CONTEXT.md term: "[{term}]({link}#L{line})" ({change summary})
```

Single-line variant when nothing is filed:

```
### 📝 Bounded context documentation
Not filing — {one-sentence reason}; it stays in the conversation — record it yourself if you want it kept
```

### 4. ✅ Delivery checks

```
### ✅ Delivery checks
{delivery result list, e.g. "ADR {id}: CONTEXT.md glossary approval preflight passed (full quality review and supersession scan have not run); CONTEXT.md: self-sufficiency verification passed"}
```

### 5. 🔍 ADR supersession scan — not emitted at interview time (the gate defers scanning to the draft promotion flow); template retained for non-interview or future use

```
### 🔍 ADR supersession scan
[ADR {id}]({link}), [ADR {id}]({link}) vs active ADRs ×{N} → no supersession
```

### 6. 📣 ADR supersession report

```
### 📣 ADR supersession report
| Code | Old decision | New decision | What changed | Scope & handling | Confidence |
|---|---|---|---|---|---|
| S1 | [ADR {id} decision {decision id}]({link}#L{line}) | [ADR {id} decision {decision id}]({link}#L{line}) | {≤30 words, plain language} | Some decisions superseded: ADR file stays in [active]({link}) | high |
| S2 | … | … | … | All decisions superseded: ADR file archived to [archived]({link}) | low — review first |

Disagree with any row → say "roll back S{n}" and both sides are restored symmetrically. (No rollback requested means consent — no further reminders; the rollback right never expires.)
```

### 7. 🚨 Self-sufficiency violation reported

```
### 🚨 Self-sufficiency violation reported — re-review verdict: false positive
- Decision: [ADR {id} decision {decision id}]({link}#L{line})
- Reported: {the verifier's violation description}
- Re-review basis: {why it is a false positive, one sentence}
- **Stopping for your confirmation**: agree it's a false positive and we continue; disagree and I fix it
```

```
### 🚨 Self-sufficiency violation reported — re-review verdict: true violation, fixed
- Decision: [ADR {id} decision {decision id}]({link}#L{line})
- Violation: {the unresolvable reference}
- Fix: {the meaning-preserving rewrite}; re-verified → passed
```

### 8. 🛑 Self-sufficiency fix touches decision content

```
### 🛑 Self-sufficiency fix touches decision content — stopping for your ruling
- Decision: [ADR {id} decision {decision id}]({link}#L{line})
- The snag: {why rewriting the reference cannot solve it, one sentence}
- Your options:
  - **A1**: keep the decision unchanged, rewrite as: "{suggested rewrite}"
  - **A2**: the decision itself must change → go through the normal decision-change flow
```

### 9. 🗺️ Pending items

```
### 🗺️ Pending items
{item A}, {item B} (blocked by {prerequisite}) | next question → {topic}
```

### 10. 🎯 Final candidate questions before closing

```
### 🎯 Final candidate questions before closing
1. {question}
   Recommendation: {answer} (basis: codebase / web / low confidence)
   Not derivable: {why the other candidates' answers cannot derive this one, one sentence}
2. …
(Reorder, add items, or say "enough, move on"; silence = ask them as listed)
```

### 11. 🏁 Closing checklist

```
### 🏁 Closing checklist
Last answer filed: {📝 content, or "nothing to file"}
Unratified list:
1. {item} — ratify now, or say explicitly "leave it unresolved, I'll decide later"
(The session may close only after every item is handled)
```

## Language layering

- **Machine-facing text is always English**, regardless of the environment language: the sub-agent prompts (self-sufficiency verification and supersession scan), the verdict tokens they emit (`PASS`, `VIOLATIONS`, `SCAN …: none`), and the reviewer input the documentation gate freezes for `/emergent-adr check-should-write-adr`. Verdict tokens never switch with the environment language — they are machine-parse targets, not human interface.
- **Human-facing literals follow the language the user's environment specifies.** Only two literal sets are hand-maintained — the zh-TW source set and the English canonical set above; copy whichever applies, exactly. No language specified → use the English canonical set. A third (non-Chinese, non-English) language specified → not a fallback to English: translate on the fly with the English canonical set as the source. The cross-language invariant emoji + H3 structure stays the machine anchor either way.
- **🧭 condition display names** ship in this file's two hand-maintained literal sets (see each 🧭 block's display-name list). A matching zh-TW or English environment copies its set at runtime; a third-language environment translates the matching English display name at runtime. The names are not sourced from CONTEXT.md and do not restate necessity-condition judgment semantics.
- **No wording — literal sets or sub-agent prompts — may conflict with the term definitions in CONTEXT.md.** The glossary's Chinese-and-English term records are exactly the governance boundary of the two hand-maintained literal sets; third-language renderings sit outside that governance and get no terminology-consistency guarantee.
