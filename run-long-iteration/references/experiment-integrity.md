# Experiment Integrity

## Freeze

每輪只改一個主變因。比較 model 時固定 prompt；比較 prompt 時固定 model；比較 orchestration 時固定 semantic prompt 與 evaluator。

`condition_packet` 至少凍結：

- input corpus、source order 與 corpus hash
- truth 與 evaluator identity
- output schema
- prompt 或 instruction identity
- model、effort、timeout 與 retry policy
- search budget unit 與本輪 consumption 記錄位置
- packet shape、chunk policy 與 dispatch channel
- runtime permissions

執行前比較 baseline 與 candidate。出現未聲明變因時，建立新 round 或將本輪判為 `invalid_run`。

## Truth Isolation

被測 agent 只能取得完成任務所需的原始 input。以下內容只交給外部 evaluator：

- EXPECTED 或 truth ledger
- 歷史模型答案
- 既有錯題清單
- benchmark report
- 預期修法與主 agent 結論

以不同目錄、permission boundary 或明確 packet boundary 隔離 truth。Evaluator 只在 output 固定後讀取它。

多模型答案聯集只能研究互補性，不能當作 production 正確率，因為 production 不知道哪個答案正確。

## Fixture Quality

先驗證 fixture，再測被測系統：

1. 依 production 寫作或輸入規則建立 material。
2. 執行正式 quality gate。
3. 修復 blocking finding 後 fresh re-review。
4. 由不知道既有 EXPECTED 的獨立 reviewer 建立或審核 truth。
5. 只把 reviewer 分歧交給窄範圍仲裁。
6. 反向檢查 inventory、mapping 與 omitted candidates。

Corpus 應覆蓋不同主題、語言、表達方式、量級與狀態。舊 corpus 負責 regression；全新 blind corpus 的第一次結果負責檢驗通用性。

## Test Funnel

依成本由低到高：

1. **Structural checks**：schema、parser、packet 與必要 inventory。
2. **Sentinel**：快速檢查主要狀態與最危險 regression。
3. **Difficult slice**：代表一般推理邊界的少量案例。
4. **Full regression**：完整既有 corpus。
5. **Fresh blind corpus**：首次泛化品質。
6. **Cross-model/runtime**：shared semantics 是否只適配單一環境。

每層有明確晉級條件。低層失敗時停止昂貴層；低層通過不代表高層自動通過。

## Timing

先完成 prompt、input 與 execution packet，再開始計時：

1. 真正 dispatch 前立即記錄開始時間。
2. 同一 wave 以同一平行呼叫送出。
3. 必要 output 到達時記錄完成時間。
4. 以兩者差值計算模型執行 wall time。

分開保存：

- 每個 slot wall time
- wave critical path
- median、min、max
- timeout、retry、malformed 與 server failure 次數
- prompt 組裝與 evaluator 時間

平行流程的端到端時間由 critical path 主導，不是 slot 時間相加。不要把 dispatch 前的主 agent 思考算進模型執行時間。

## Valid Evidence

有效測試必須符合：

- 正確 input 已送達。
- model、effort、prompt 與 orchestration 符合 execution packet。
- output 結構有效。
- evaluator 可完整計分。
- agent 未接觸 forbidden truth。

答案錯誤仍是有效測試。只有執行或實驗設計失效才可 retry，且必須保持原條件。

若修復會改變實驗變因或 frozen surface，建立新 round，不得包裝成 retry。

## Variance

依 contract 的有效 replication 條件收集資料：

- 比較分布與 median，不挑最快或最高分的一次。
- 保存 server、connection、parser 與 timeout failures。
- 檢查錯誤是否集中於同一推理類型。
- 檢查 input 大小與 orchestration 是否意外漂移。
- 跨模型比較時區分 shared regression 與單一模型 variance。

資料不足時，不得以主觀印象 promotion；依 contract 預先寫定的處置 repeat、reject 或 exhausted。

## Quality Gate

先淘汰未達品質 hard gate 的候選，再比較：

1. 速度
2. token 或金錢成本
3. 操作複雜度

更高 effort 不保證品質單調增加。只接受跨有效 replication 可重現的收益。

加速非 critical stage 可能不縮短端到端時間，卻增加 disagreement 與 reviewer 成本；評估完整 critical path。

## Generalization

改善必須是判斷框架，不是案例清單。Semantic rule 不得依賴：

- fixture ID、檔名或測資路徑
- 特定自然語言關鍵字
- domain vocabulary list
- EXPECTED pattern
- 歷史模型答案

Mechanical script 只能處理結構、格式、hash 與 invariant。若更換自然語言就失效，通常代表混入 semantic heuristic。

最強的通用性證據是全新主題、全新寫法的 blind material 第一次結果。

## Audit

Contract 必須定義 audit trigger。常見的通用 trigger 類型是：

- 固定數量的 completed rounds
- baseline promotion
- 出現異常完美結果、truth leakage 或其他污染跡象

每次 audit 建立 stable event key 與 immutable findings report。相同 event 不重複消耗 reviewer；先查 history index 是否已有 closed report。

Auditor 只讀當前 candidate、方法、硬規則與原始 material，不得取得 EXPECTED、歷史答案、預期修法或 coordinator 結論。

Auditor 檢查：

- 改善是否仍是通用框架
- script 是否跨越結構／語意邊界
- evaluator 或 truth 是否污染被測 agent
- 報告是否選擇性忽略失敗
- promotion evidence 是否足以支撐結論
- 繼續迭代是否仍有合理收益

成立的 finding 必須修正或淘汰 candidate。未關閉 finding 時不得 promotion。

## Prompt Slimming

先建立可信 baseline，再做區塊 isolation：

1. 移除或合併一個概念區塊。
2. 測量它防止的錯誤是否回來。
3. 比較品質、速度與 token。
4. 品質失敗時回退。

逐句刪字只適合最後收斂。早期用較大的 isolation test 找高成本、低貢獻區。品質未過 gate 時，不以速度或 prompt 長度作為晉級理由。
