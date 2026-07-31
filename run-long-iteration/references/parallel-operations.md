# Parallel Operations

## Prepare

先建立完整的 round execution packet，再 dispatch。它是 immutable manifest；每個 job 依 contract 的 `retry_limit` 預列初始 attempt 與所有可用 retry attempts。每個 attempt 至少保存：

- stable job ID 與 attempt ID
- executor/runtime
- model、effort 或其他 executor settings
- prompt/instruction 與 input identity
- run directory、timeout、chunk 與 repeat index
- 唯一 output 與 evaluator-result path
- 唯一 dispatch-receipt 與 completion-receipt path

這些 paths 在 round 進入 `planned` 前決定，但 receipts 尚不存在。`current_round.execution_packet` 固定引用整份 manifest，執行或 retry 時不得換成另一份 packet。用機械 generator 產生 entries，不要在 spawn 迴圈中逐份思考、摘要或改寫。

每個 worker 的 write scope 必須互不重疊。只有 coordinator 可以 commit navigation state。

## Preflight

整波 dispatch 前逐 job 驗證：

- executor 與必要 settings 完整
- prompt/instruction、input 與 run directory 存在
- output、evaluator 與 receipt paths 唯一且位於允許範圍
- chunk membership 與 source order 正確
- truth、EXPECTED、歷史答案與預期修法不在 input
- timeout、retry 與 model/effort 符合 execution packet
- receipt paths 尚不存在

任一 job 失敗時不要派出整波。修正 packet；若 frozen surface 改變，建立新 round。

這份 preflight 是 coordinator 的內容驗證責任。`navigation_state.py` 將 execution packet 視為 opaque artifact，只凍結 ref/hash；「script 接受 checkpoint」不代表 packet payload 已通過本節 gate。

## Append-Only Receipts

Receipt 是單次發布的 JSON object。使用 bundled helper exclusive publish；目標已存在時必須拒絕，不得覆寫：

```bash
python3 "$SKILL_DIR/scripts/navigation_state.py" publish-receipt \
  --source <staged-receipt.json> \
  --out <execution-packet指定的receipt-path>
```

Helper 只保證 source 是 JSON object、目標 exclusive publish 與回傳 artifact hash，不驗證 dispatch/completion 欄位或它與 execution packet 的綁定；coordinator 必須在 publish 前完成該內容檢查。

每個 job 使用兩份 receipt：

- **Dispatch receipt**：spawn 回傳後立即建立，保存 job ID、agent/process ID、dispatch time 與 output path。
- **Completion receipt**：output 驗證、evaluator 完成且 agent close 後建立，保存 job ID、output/evaluator hashes、disposition、completion time 與 close 結果。

不得修改 dispatch receipt，也不得用 completion receipt 覆蓋它。`result_packet` 或 `history_index` 引用需要保存的 receipts。

## Dispatch

Preflight 完成後：

1. 記錄 dispatch timestamp。
2. 以單一平行 tool call 送出整個 wave。
3. 依 spawn response 立即建立每個 job 的 dispatch receipt。
4. 以 CAS 將已知 active worker IDs 寫入 checkpoint。
5. 低頻等待，不做 busy polling。

Spawn 與本機 receipt publish 無法成為同一個原子操作。若中斷發生在兩者之間，resume 必須先查 runtime、預定 output path 與 receipt path；無法辨認原 execution 時等待到 timeout，將該 attempt 記為 invalid，再以新的 attempt identity 與 paths retry，不能盲目重派到相同 paths。

若 runtime 有 concurrency ceiling，拆成多個 wave。完成並釋放上一波 agents 後再開下一波。

Concurrency ceiling 是安全上限，不是目標值。逐步提高 wave 大小，觀察 memory pressure、CPU、process count、收件速度、server failure、slot latency、總 token 與 retry rate；吞吐下降或本機壓力明顯上升前停止擴張。

## Collect and Close

每次醒來：

1. 先檢查 dispatch receipt、completion receipt 與實體 output。
2. 收取已完成 job。
3. 驗證 output 結構並保存 evaluator result。
4. 立即 close 完成的 Codex sub-agent。
5. Exclusive publish completion receipt。
6. 以 CAS 從 checkpoint 移除 worker ID，並在需要時更新 result/history ref。
7. 只等待仍執行的 workers。

UI 顯示仍在思考或 websocket idle timeout，不代表沒有產物；先查 output file。Completed agent 仍可能佔 concurrency slot，因此結果已回傳後仍要明確 close。

## Failure Policy

| Failure class | 品質 evidence | 處置 |
|---|---|---|
| Semantic answer mismatch | 有 | 保留並交 evaluator 計分，不 retry |
| Transport、server、timeout 且無完整 output | 無 | 在 retry budget 內同 slot retry |
| Parser 或 output schema terminal failure | 無 | 原 packet 可恢復時 retry，否則 `invalid_run` |
| 錯誤 permission、path、model、effort 或 prompt | 無 | 停止該 wave；修復後依變因是否改變決定 retry 或新 round |
| Truth leakage 或 evaluator 無法判定 inventory | 無 | `invalid_run`；修復隔離後建立新 round |

同 slot retry 必須保持 candidate、condition、model、effort、prompt、input、timeout 與 chunk 不變，並啟用 fixed execution packet 中下一個預列的 attempt identity、output 與 receipt paths。若預列 attempts 已用盡，不得臨時擴寫 manifest；依 contract 將該 slot 記為 terminal disposition。

Retry limit 耗盡時停止並記錄 terminal disposition。整波錯派時立即關閉 workers、保存 failure reason；只有完全相同的實驗條件才可 retry。

## Resume

暫停前不再派新 job，收完無法安全中斷的 execution，關閉完成 agents，保存 receipts、outputs、evaluator results、in-flight IDs 與下一個動作，再 commit checkpoint。

恢復後：

1. 以 `navigation_state.py read` 讀唯一 committed state。
2. 從 fixed execution packet 枚舉所有 job／attempt 的預定 paths。
3. 逐 job 對照 dispatch receipt、completion receipt、output、evaluator result 與 active worker IDs。
4. 有 valid completion receipt：不得重派；必要時只補 checkpoint。
5. 有 valid output 但沒有 completion receipt：完成 evaluator、close，發布 completion receipt，再補 checkpoint。
6. 有 dispatch receipt 但沒有 output：確認 runtime 狀態，繼續等待或依 failure policy 結束 attempt。
7. 沒有 dispatch receipt：先做 spawn-gap reconciliation；不可直接假定「從未 dispatch」。

未被 committed state 引用的 staged state 不具控制權。它的 artifacts 可以作為調查材料，但必須由 coordinator 重新評估後，才能在新的合法 transaction 引用。

Session 中斷、電腦休眠或 fresh context 都不構成全量 retry 理由。
