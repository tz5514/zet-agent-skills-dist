---
name: forge-agent
description: "forge 的 sub-agent 快捷入口。自動 spawn fresh-context sub-agent 以 forge 框架執行任務，避免主 context 錨定效應。觸發：/forge-agent、用 sub-agent 跑 forge、隔離分析、fresh context 分析、盲測、blind analysis。Do NOT use for 主 agent 直接跑 forge（直接用 /forge）。"
---

# forge Sub-agent 快捷入口

收到任務後，自動 spawn 一個 general-purpose sub-agent，讓它以 forge skill 框架執行任務。主 agent 不介入執行過程。

## 流程

### Step 1：解析任務

從使用者的 prompt 中提取四件事：

1. **任務目標**：sub-agent 要做什麼（一句話）
2. **任務標籤**（主 agent 預判）：根據任務目標，預判 forge 的任務標籤（Build/Debug/Review/Creative）。這個判斷由主 agent 做——主 agent 有完整對話 context，比 sub-agent 更適合判斷。
3. **目標檔案**（自動推斷為主）：
   - **預設**：從對話 context 自動推斷——最近討論/引用過的檔案中，跟任務目標相關的
   - **使用者覆蓋**：使用者可用「帶上 X」「只看 Y」「不要帶 Z」明確指定或排除
   - **推斷不出**（如新 session 第一句話就觸發、或任務跟之前的對話無關）：列出推斷困難的原因，問使用者「你要 sub-agent 讀哪些檔案？」。使用者回覆後，帶著答案重新從 Step 2 繼續。此處不受 forge 的提問鎖約束——forge-agent 是外層 skill，提問鎖只在 sub-agent 內部的 forge 流程中生效
4. **隔離程度**：
   - 使用者提到「blind」「盲測」「fresh context」→ **完全隔離**：只給檔案路徑和任務，不帶任何對話脈絡
   - 否則 → **有限 context**：帶上使用者指定的檔案 + 從對話中摘錄的必要背景（限 3 句以內）

### Step 2：前置檢查（Hard Gate）

1. 確定 output 目錄：取得作業系統的暫存資料夾路徑（macOS/Linux: `$TMPDIR` 或 `/tmp`；Windows: `%TEMP%`），在其下建立 `forge-agent` 子目錄。確認目錄存在（不存在就建——**這步必須由主 agent 做**，因為 sub-agent 無法回應權限確認會卡死）
2. 確認所有目標檔案存在（用 Glob 驗證路徑即可——**不要 Read 內容**，特別是 blind 模式下，主 agent 讀了內容可能在轉述時洩漏脈絡）
3. 如果使用者指定了額外約束或參考資料，確認路徑有效

任一檢查未完成 → 告知使用者哪個檔案不存在或路徑無效，等使用者修正後再繼續。不准跳過直接進 Step 3。

### Step 3：Spawn Sub-agent

使用 Agent tool，參數：
- `subagent_type`: **general-purpose**（必須——Explore 沒有 TodoWrite，而 TodoWrite 是 forge 的核心驅動機制）
- `prompt`: 按以下模板組裝。組裝時主 agent 須：
  - 將 `{output_dir}` 替換為 Step 2 取得的 output 目錄絕對路徑
  - 將 `{output_filename}` 替換為主 agent 預先生成的完整檔名（格式：`YYYYMMDD-HHmmss-{4位hex}-{任務關鍵字}.md`，如 `20260407-143022-a7f3-blacksmith-review.md`）——不要讓 sub-agent 自己命名
  - 將 `{任務標籤列表}` 替換為 Step 1 預判的標籤（如 `Build + Review`），並展開對應的條件提示
  - 將 `{forge_skill_absolute_path}` 替換為 forge SKILL.md 的絕對路徑（即 `~/.claude/skills/forge/SKILL.md` 展開後的完整路徑）

#### Prompt 模板

```
你是一個獨立的{角色}。你沒有任何對話歷史——以下是你的全部 context。

**重要：你跑在 sub-agent 環境中。你不能向使用者提問——沒有人會回覆你。
如果遇到無法自行解決的問題，在回傳中說明即可。**

## 任務
{任務目標}

## 任務類型
這是一個 {任務標籤列表} 類型的任務。
{如果含 Build：你需要在開工分析中產出 [完成狀態] 和 [需求拆解]。}
{如果含 Debug：你需要在開工分析中產出 [複現]。}
{如果含 Creative：每個步驟需要做一致性核對，交付時需要 [Creative 自檢]。}
{如果含 Build 或 Review：交付時需要 [零知識審視]。}

## 要讀的檔案
{檔案路徑列表，每個一行}

## 執行框架
依據你的環境，選擇合適的方式觸發 forge skill：
- Claude code: 使用 Skill tool 呼叫 /forge skill
- Codex: 使用 $forge 呼叫 forge skill

如果都無法觸發，改用 Read-inline：Read `{forge_skill_absolute_path}` 並嚴格按照其內容執行。
無論哪種方式，都不可跳過任何步驟，特別是條件區塊中對應任務標籤的額外欄位。

## 產出落地
完成 forge 交付閉環後，用 Write tool 將完整產出寫入：
`{output_dir}/{output_filename}`
（目錄已由主 agent 預先建好，檔名已由主 agent 預先決定。直接寫入即可，**不要跑 mkdir、不要改檔名**。）
寫完檔案後，在回傳中同時附上完整內容和檔案路徑。
這是為了防止回傳截斷導致產出遺失——檔案是保底，回傳是主要通道。

{如果是有限 context 模式，加入以下區塊：}
## 背景（來自主 agent 的摘要）
{3 句以內的必要背景}

{如果使用者指定了額外約束：}
## 約束
- {使用者指定的約束}
```

#### 角色選擇

根據任務類型填入 `{角色}`：
- 使用者在 prompt 中指定了角色 → 使用指定的
- 分析/研究 → 「分析者」
- review/審查 → 「品質審查員」
- 其他 → 「執行者」

### Step 4：回報

Sub-agent 的回傳只有主 agent 能看到（Agent tool 機制）。主 agent 須：

1. **正常完成**：按以下優先順序轉述 sub-agent 的產出：
   - **必轉**（使用者需要立即知道的）：[任務結果]、[任務目標對照]、改善點/發現的問題清單
   - **按需轉**（有實質內容才轉）：[產出影響]（有連鎖影響時）、[額外處理]（有 bonus discoveries 時）、[零知識審視]（有誤解風險時）、[Creative 自檢]（有 ⚠️ 項目時）
   - **不轉**（agent 自用）：[核心四問回顧]、[過程回顧]（除非包含持久化建議）
   - 如果 sub-agent 產出含具體修改文字（修改前/後），必須完整轉述，不可只轉摘要
   - 最後附上備份檔案的可點擊連結
2. **回傳被截斷**（內容不完整、沒有交付閉環）：告知使用者回傳被截斷，附上檔案的可點擊連結讓使用者直接開啟閱讀
3. **sub-agent 回報卡住**（forge 六步排查跑完仍未解決）：告知使用者並詢問是否要在主 context 中接手

按以上三級分類轉述——「必轉」項不可省略，「不轉」項不必轉述。sub-agent 的發現和具體修改文字不可被改寫或摘要化。
