---
name: run-long-iteration
description: 執行可恢復的長期迭代 campaign，以凍結契約、單一變因、evidence gate、原子 checkpoint 與受控 sub-agent wave 維持研究可信度。適用於需要跨多輪或跨 session 的 prompt、模型、效能、正確率、成本或流程研究。
disable-model-invocation: true
---

# Run Long Iteration

把長任務視為一場 **campaign**。每輪只回答一個可驗證問題，品質 gate 先於速度與成本，所有 promotion 都必須能回到前一個可信 baseline。

先將本檔所在目錄的絕對路徑記為 `SKILL_DIR`。

## 契約邊界

本 skill 有兩層責任：

- **機械層**：`scripts/navigation_state.py` 驗證目前 checkpoint 的 schema、artifact ref/hash、contract freeze、round lifecycle、promotion linkage、progress counter 與 CAS commit。Referenced artifact 的 payload 對 script 是 opaque；script 不替 coordinator 驗證 execution manifest、receipt 或 evaluator payload 的領域 schema。
- **判斷層**：coordinator 在 commit 前 preflight referenced artifact 的內容，並依 frozen evaluator、regression 與 blind audit 判斷實驗是否有效、候選是否正確、是否應 promotion 或停止。

Script 不解讀任意研究領域的語意，也不從 metric 文字自行推導 verdict。不要把它宣稱成通用 workflow engine、完整歷史資料庫或形式化正確性證明。

一個 campaign 只能有一個 coordinator 寫 navigation state。Sub-agent 只能寫互不重疊的 immutable artifacts；不得直接修改 state 或 locator。

## 1. 決定入口

有明確 locator path 時先讀 committed checkpoint：

```bash
python3 "$SKILL_DIR/scripts/navigation_state.py" read \
  --locator <absolute-locator-path> \
  --json
```

- `running`：從 `next_action` 繼續。
- `paused` 或 `blocked`：確認 `resume_condition` 已成立後才恢復。
- `converged`、`cancelled`、`exhausted`：campaign 已結束；新研究建立新 campaign。

沒有 locator 且任務明確是新研究時，從 [navigation-state.template.json](assets/navigation-state.template.json) 建立新 state。先把 template 的 `campaign_id` placeholder 換成穩定且唯一的 ID；placeholder 不可 commit。

任務要求「繼續」但沒有 locator，或有多個互相衝突的 locator 時，不得搜尋猜測或悄悄建立新 campaign。回報 blocked 並要求取得唯一 locator；沒有 locator 時不建立假 state。

Campaign directory 放在使用者或 runtime 管理的持久 scratch 位置，不要污染 production source tree，也不要使用重開機後可能消失的 OS 暫存目錄。

## 2. 凍結 campaign contract

第一次實驗前，完整填寫 `contract`：

- objective 與 final deliverable
- metric priority 與 hard gate
- 本階段唯一 allowed variable
- frozen surfaces
- valid-run、promotion 與 rollback criteria
- blind audit trigger 與 findings closure policy
- retry limit 與可計數的 search budget
- stop conditions
- `serial` 或 `wave` execution mode

`contract.complete` 設為 `true` 後，以工具計算 hash：

```bash
python3 "$SKILL_DIR/scripts/navigation_state.py" contract-hash \
  --state <staged-state.json>
```

把輸出寫入 `contract_sha256`。Committed complete contract 不可漂移；需要改契約時建立新 campaign。

Contract 中的 criteria 必須具體到 coordinator 與 fresh-context reviewer 能對同一份 evidence 得出可辯護結論。Script 只凍結文字與 hash，不代替這項判斷。

## 3. 封存 baseline

實驗前建立可信 baseline，保存：

- `artifact`：候選來源的固定快照。
- `evidence`：已通過的 regression 或品質報告。
- `rollback`：永遠是 artifact ref；初始 baseline 可引用寫有可執行回退步驟的檔案，promotion 後必須引用前一 baseline artifact。

每個 reference 都是：

```json
{"path": "/absolute/path", "sha256": "64-hex"}
```

使用 helper 產生，不要手算：

```bash
python3 "$SKILL_DIR/scripts/navigation_state.py" artifact-ref \
  --path <artifact-path>
```

初始 baseline 只能在 contract complete 且沒有 active round 時封存。

涉及 prompt、model、fixture、正確率、效能或 A/B 比較時，在第一輪前完整讀取 [experiment-integrity.md](references/experiment-integrity.md)。

## 4. 執行單一變因 round

每輪先寫：

```text
只改變 X，預期 Y 改善，且 Z 不得退步。
```

Round lifecycle 固定為：

```text
none/closed -> planned -> running -> evaluated -> closed
```

`planned` 前建立 immutable artifacts：

- `candidate_artifact`：本輪實際被評估的候選。
- `condition_packet`：假設、唯一變因、baseline/candidate hashes、frozen surfaces、input/truth/evaluator identity。
- `execution_packet`：本 round 的 immutable execution manifest，保存 executor、model/effort、input、timeout、chunk、repeat index 與 dispatch 設定，並依 `retry_limit` 預列每個 job 所有可用 attempt 的 identity、output、evaluator 與 receipt paths。
- `repeat_of`：只有 `repeat_same_conditions` 的下一輪使用，綁定來源 round、execution hash 與 result hash；一般 round 為 `null`。

Execution packet 必須在 `planned` 前一次列完初始 attempt 與有限 retries。執行期間不可替換這份 manifest；retry 只能啟用下一個預列 attempt。Fresh-context coordinator 因此能從同一個 committed ref 找到所有可能產物，不必猜測路徑或依賴 history archive。

這是 coordinator 的 preflight gate；navigation script 只驗證該 artifact ref 的存在、hash 與後續不可漂移，不解析 manifest payload。空白、不完整或 paths 重複的 packet 不得進入 `planned`，即使 checkpoint schema 本身可被 script 接受。

執行後建立 `result_packet`，至少保存：

- output 與 evaluator identity
- 每個 required slot 的 disposition
- 品質、速度與成本結果
- valid-run 判定及理由
- 可重算 verdict 所需的 evidence
- 本 attempt 的 retry 次數與 search budget consumption

Evaluator 根據 frozen criteria 產生唯一 verdict：

- `promote`
- `reject`
- `repeat_same_conditions`
- `invalid_run`

結構完整但答案錯誤是有效 evidence，不得因分數不好而 retry。Transport、錯誤 input、錯誤 model/effort、truth leakage、malformed output 或 evaluator 無法計分才是 invalid run。

`repeat_same_conditions` replication 必須沿用同一 hypothesis、condition 與 candidate，並以 `repeat_of` 證明來源。新的 execution/result 必須有不同內容 hash；若改到 frozen surface，建立一般新 round。

## 5. 管理 sub-agent wave

使用 sub-agent、平行 process 或長時間 wait 前，完整讀取 [parallel-operations.md](references/parallel-operations.md)。

硬性規則：

- Dispatch 前先機械產生並 preflight 全部 execution packets。
- 平行 worker 不得寫同一檔案。
- Prompt、input、output path 不在 spawn 之間臨時組裝。
- Spawn 後立即建立每個 job 的 immutable dispatch receipt；收件、驗證並 close 後建立另一份 completion receipt。
- 每個完成的 Codex sub-agent 必須立即 close。
- 恢復時依 execution packet 掃描 receipts 與實體 output，再決定是否重派；已有有效產物不得 retry。

Navigation state 只保存 active worker IDs 與 packet refs。Dispatch/completion receipts 與完整結果使用 execution packet 預定的 append-only paths；coordinator 透過 checkpoint CAS 使兩者一致。

## 6. 評估、審計與 promotion

品質未通過 hard gate 時，不比較速度、token 或成本。

Promotion 前必須：

1. 對 candidate 跑 contract 要求的 regression。
2. 依 [experiment-integrity.md](references/experiment-integrity.md#audit) 判斷是否需要 fresh-context blind audit。
3. 關閉成立的 audit findings，或淘汰 candidate。
4. 在 `promotion_evidence` 保存 candidate hash、前一 baseline hash、regression ref、audit event key、findings report 與 closure 狀態。
5. 將 round 依序 commit 為 `evaluated`、`closed`；evaluated 後的 result、verdict 與 promotion evidence 不得改寫。
6. 在 close transition 同一 checkpoint 將 baseline 更新為 candidate；baseline evidence 必須是該 regression，rollback 必須指向前一 baseline artifact。

`reject` 保持 baseline 不變並保存失敗類型。`invalid_run` 不提供品質結論。`repeat_same_conditions` 不得偷偷修改條件。

Audit 是 evaluator／promotion／history evidence 的一部分，不是 navigation `next_action`。沒有 immutable audit report 時，不得把它當成已完成的 transition。

改善必須是可跨主題與語言成立的判斷框架。禁止以 fixture ID、檔名、EXPECTED、歷史答案、特定自然語言關鍵字或 domain vocabulary 修補結果。

## 7. 原子 checkpoint

每次狀態變更都先取得 transaction 與 CAS expectation：

```bash
python3 "$SKILL_DIR/scripts/navigation_state.py" begin \
  --locator <locator.json>
```

從目前 committed state 複製 staged state，只修改本次合法 transition 的欄位。新 campaign 使用 template。準備好所有 referenced artifacts 後 commit：

```bash
python3 "$SKILL_DIR/scripts/navigation_state.py" commit \
  --staged <staged-state.json> \
  --locator <locator.json> \
  --revisions-dir <campaign-dir>/revisions \
  --transaction-id <transaction-id> \
  --expected-revision <expected-revision> \
  --expected-state-sha256 <expected-state-sha256-or-none>
```

既有 campaign 的 staged state 必須保留目前 head 的 `campaign_id`、`revision`、`transaction_id` 與 predecessor metadata，讓 commit 能辨認它確實從該 head 衍生。`begin` 對新 campaign 輸出的 JSON 值是 `null`；傳給 CLI 時使用字串 `none`。

Committed `next_action` 是下一個 state transition 的 intent。正常 running flow 必須由對應 action 推進，例如 `execute_round` 才能 `planned -> running`；沒有 transition 時不得任意改 action。進入 `paused`／`blocked` 時把原 action 保存為 `checkpoint.suspended_next_action`；恢復時必須原樣還原，且不得同時改 round、baseline、progress、workers、history 或 evidence refs。

Commit 會：

- 取得 locator lock。
- 拒絕 stale revision/hash。
- 拒絕不是從目前 head 衍生的 staged state。
- 驗證目前 state、直接 predecessor、artifact hashes 與 transition。
- 以 exclusive publish 建立 append-only revision；CLI 不覆蓋既有路徑，後續外部修改會被 locator hash 偵測並拒絕。
- atomic replace locator。

它不遞迴審計整段歷史。需要完整研究軌跡時，以 `checkpoint.history_index` 引用 coordinator 維護的 immutable index；該 index 至少記錄 round outcomes、retry 與 search budget consumption。它是 evidence archive，不是恢復控制面。

Checkpoint 至少在以下時點更新：

- round lifecycle 改變
- wave 收件完成
- baseline 改變
- 暫停、blocked 或等待外部資源
- 發現污染或 invalid run
- 準備停止

若 CAS 拒絕，重新讀 locator，保留未提交 artifacts，從新 head 重新判斷；不得覆蓋新狀態。

## 8. 暫停、恢復與停止

`paused` 與 `blocked` 必須有具體 `resume_condition`，且 next action 分別是 `resume` 或 `recover`。暫停前停止派新工作，收完無法安全中斷的結果，關閉完成 agents，再 commit。`suspended_next_action` 在等待期間不可漂移；恢復 checkpoint 只切回 running、原樣還原 action 並清空 suspended 欄位。

宣告 `converged` 或 `exhausted` 前：

1. 關閉目前 round。
2. 清空 active worker IDs。
3. 建立 immutable `completion_evidence`，逐項對照 hard gate、stop conditions、剩餘風險與 rollback。
4. 先 commit 一個 `running` checkpoint，將 next action 設為 `evaluate_stop`。
5. 下一個 commit 才進入 terminal status，next action 設為 `none`。

若穩定 checkpoint 已是 `plan_round` 或 `repeat_round`，可用窄範圍 stop-preparation transition 改成 `evaluate_stop`：contract、baseline、round、progress 與 history 不變、沒有 active workers、原本沒有 completion evidence，且本次只新增 completion evidence 與更新摘要／風險。其他 action swap 一律拒絕。

只有以下證據同時成立才可 convergence：

- hard gate 在 contract 要求的 regression 與有效 replication 中穩定通過
- fresh blind material 達到可接受品質
- 沒有未解釋的失效、選擇性重跑或污染
- 更昂貴方案沒有穩定且值得成本的收益
- 剩餘風險已被接受或有明確上層防線
- 新方向的預期收益低於成本與 regression 風險

Search budget 用盡但仍不符合 convergence 時使用 `exhausted`。使用者終止時可從 in-flight round 直接進入 `cancelled`，但必須先關閉 workers、保持 contract/baseline/round/progress 原樣，並在 `completion_evidence` 保存 immutable cancellation receipt。Terminal campaign 不可重新開啟。

## 完成定義

這個 skill 的成功不是「跑很多輪」，而是：

- locator 可讓 fresh-context coordinator 從唯一 checkpoint 恢復
- contract、baseline、round 與 evidence 彼此可追溯
- 每次 promotion 有 regression、audit disposition 與 rollback
- 無效執行沒有污染品質結論
- 平行 agent 全部有 terminal disposition，完成者已 close
- 終止結論與 scope 內的機械保證一致，沒有誇大 script 能力

交付或修改本 skill 前執行：

```bash
python3 -m unittest discover \
  -s "$SKILL_DIR/scripts" \
  -p 'test_*.py'
```
