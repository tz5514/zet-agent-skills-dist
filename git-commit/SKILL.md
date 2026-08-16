---
description: 自動將 git 中所有未 commit 的變更，依照邏輯分組拆分成多個 commit。觸發條件：使用者本人的訊息明確包含 commit 指令（如「commit」「git commit」「做完後幫我 commit」），或使用者已授權執行的其他 skill 其 SKILL.md 明文將 commit／呼叫本 skill 列為流程步驟。禁止觸發：agent 自行判斷應該 commit（如 todo 清單、任務完成、測試通過、流程推進）不構成觸發條件。獨佔規則：所有 git commit 操作一律透過此 skill 執行，禁止手動跑 git commit 命令。
---

# 自動拆分 Commit

## 呼叫範例

- `git commit` — 自動拆分並 commit 所有變更
- `git commit & push` — 自動拆分並 commit 所有變更，完成後 push 至 remote
- `git commit 除了 package.json 以外的變更` — 忽略明確指定的檔案
- `git commit 除了 i18n 相關的以外` — 忽略符合模糊描述的檔案（需經使用者確認忽略清單）
- `git commit foo.ts 與 bar.ts` — 僅包含明確指定的檔案
- `git commit 只跟這個對話內容相關的變更` — 根據對話 context 判斷並確認符合描述的檔案，僅包含這些檔案的變更

## 流程

### 守衛條件：驗證觸發條件

**在進入任何步驟前，必須確認存在有效授權**。以下任一成立即可進入流程；否則直接拒絕執行並回應：
```
「此 Skill 需要明確的 commit 指示。請在指令中明確說『commit』或『git commit』；或透過已授權 skill 的明文 commit 步驟呼叫。」
```

有效授權（擇一即可）：
1. **使用者／委派指令含觸發詞**：ARGUMENTS 或使用者原始指令包含下列任一詞彙
觸發詞彙清單：
- `commit`
- `git commit`
- `幫我 commit`
- `做完後 commit`
- `完成後 commit`
- `然後 commit`
- `之後幫我 commit`

2. **其他 skill 的明文步驟**：使用者已授權執行的其他 skill，其 `SKILL.md` 流程中若字面寫明某步驟須做 git commit、或須呼叫本 skill，則到達該步驟時視為有效觸發——授權延伸自使用者對該 skill 的呼叫，不必再等使用者另發一則含 commit 的訊息。判準是「commit／呼叫本 skill」在該 skill 的流程文字中字面存在；agent 自行把「做完後順便 commit」加進流程、或 skill 未寫 commit 卻自行決定要 commit，都不構成觸發。

**Sub-agent 情境的觸發詞來源**：sub-agent 的「使用者訊息」即為派發給它的委派任務指令。以下任一成立即視為有效觸發——授權延伸自發起該流程的使用者：（1）委派指令中含字面 commit 觸發詞；（2）委派指令要求執行的 skill，其流程以 commit／呼叫本 skill 為明文步驟（如 implement 的收尾 commit）。判準是「觸發詞或 skill 明文步驟在收到的指令／該 skill 文字中字面存在」，與主 agent 情境同一標準；sub-agent 僅憑自身判斷（委派指令無觸發詞、且所執行 skill 亦無明文 commit 步驟）而 commit，同樣不構成觸發。



---

### Step 0：前置檢查
1. **模型資訊**：輸出當前運行的 model 名稱與版本號給使用者看。如果沒有可取得的 model 資訊則填寫為「無法得知」
2. **Repo 狀態**：執行 `git status` 確認 repo 不在 merge、rebase、cherry-pick 或 bisect 狀態。若處於異常狀態，告知使用者並結束
3. **已有 staged 變更**：執行 `git diff --cached --stat` 檢查。若已有 staged 變更，使用 AskUserQuestion 詢問使用者：
   - **納入拆分**：將已 staged 的變更一併分析，可能被重新分組到不同 commit
   - **先 commit 當前 staging**：以現有 staging 內容直接建立一個 commit（依 Commit Message 規範撰寫），再對剩餘的 unstaged 與 untracked 變更執行拆分流程。若此 commit 觸發 pre-commit hook 失敗，依注意事項中的 hook 失敗協議處理
   - **終止並維持原狀**：結束整個流程，維持現有狀態不變
4. **執行模式判斷**（必須執行，不得猜測）：分析使用者的原始 commit 指令，判斷 commit 是否明確為其他任務的收尾。符合以下任一模式即判定為「**自動模式**」，否則一律判定為「**互動模式**」。結果記錄供 Step 3 使用。
   - 時序詞接在其他任務描述之後：「做完後 commit」「完成後 commit」「然後 commit」「之後幫我 commit」
   - 並列收尾：「[做某事] 並 commit」「[做某事]，順便 commit」「[做某事] + commit」
   - 若 commit 是指令中**唯一的任務**（例如單純的「commit」「git commit」「幫我 commit」「git commit & push」），一律為互動模式，無論對話中是否有前置作業
   - 若在 sub-agent 中執行本 skill，則一律強制為自動模式，沒有例外（因為不會有人類互動回覆，停下來就等於導致任務意外中斷失敗）

### Step 1：蒐集變更資訊

同時執行以下命令：

1. `git status`（不使用 `-uall`）
2. `git diff HEAD`（所有已追蹤檔案的 staged + unstaged 變更）
3. `git log --oneline -10`（了解近期 commit 風格）

對於 `git status` 中出現的 untracked files，根據副檔名判斷：文字檔使用 Read 工具讀取內容以了解用途，二進位檔（圖片、字型等）僅依檔名與路徑推斷用途。

另外，如果此對話前面有其他 context 可參考（例如前面使用者與 agent 討論過要改什麼功能，並留下了 agent 的改動紀錄），也將這些 context 納入分析。

若沒有任何未 commit 的變更，回覆「沒有需要 commit 的變更。」並結束。

### Step 2：變更篩選（白名單/黑名單）

**指令解析（必做）**：回頭檢查使用者的**原始指令全文**（含引號、括號內的文字），判斷是否包含篩選要求。

> **「原始指令」的定義**：使用者直接發送的 commit 訊息文字，**不包含** Skill 工具的 ARGUMENTS 參數。ARGUMENTS 是外層 agent 傳入的補充 context（例如描述「這個對話做了什麼」），只能用來輔助理解篩選範圍的語意（幫助判斷哪些變更屬於「這個對話」），**不可用來決定篩選模式**（明確 vs 模糊）。即使 ARGUMENTS 中列出了具體檔案路徑，只要使用者的原始指令是模糊描述，就必須走模糊描述流程。

以下任一情況視為「有指定篩選」：

- 包含限制詞彙：「只」「僅」「只有」「只處理」「除了」「不包含」「不要」「跳過」「排除」等
- 明確提及特定檔案名稱、路徑、或功能範圍（如「只處理 git-commit skill 的更新」「除了 i18n 以外」）
- 以引號、括號等方式框出篩選條件（如「『只處理 X』」）

若判定「無篩選要求」，跳過此步驟。否則繼續以下流程。

- 包含 = 白名單：僅包含符合條件的變更，其餘全部排除
- 排除 = 黑名單：排除符合條件的變更，其餘全部包含

根據使用者的指定方式，分兩種處理：

- **明確檔案名稱**（如 `package.json`、`src/config.ts`）：以**檔案**為單位，直接從變更清單中包含/排除整個檔案，不進行 hunk 分析，不需確認
  - 若指定的檔案不在變更清單中：
    - 白名單：告知使用者這些檔案不在變更範圍內，直接報錯並結束
    - 黑名單：告知使用者這些檔案不在變更範圍內，不報錯，繼續流程（不在變更清單中的檔案本來就不會被處理）
  - 若有匹配到檔案，以下列格式輸出匹配到的檔案列表，然後自動繼續後續流程：
    ```
    包含的檔案：（白名單時）
    忽略的檔案：（黑名單時）
    - [path/to/file1](path/to/file1)
    - [path/to/file2](path/to/file2)
    ```
- **模糊描述**（如「i18n 相關的」、「做 linting 設定的變更」、「只跟這個對話內容相關的變更」）：以 **hunk** 為最小分析單位
  1.  根據 Step 1 蒐集的變更資訊，對每個變更檔案逐一分析：
  - **已追蹤檔案**（有 diff hunk）：逐 hunk 判斷是否符合描述
  - **Untracked 檔案**（新檔案）：根據檔案內容整體判斷，視為不可拆分的單一單位
    每個檔案的分析結果分為三類：
  - **全檔符合**：所有 hunk 都符合描述（或 untracked 整檔符合）
  - **部分符合**：僅部分 hunk 符合（僅已追蹤的多 hunk 檔案可能出現）
  - **全檔不符合**：沒有任何 hunk 符合描述（或 untracked 整檔不符合）
    若為白名單且無任何 hunk 符合，告知使用者後直接報錯並結束。若為黑名單且無任何 hunk 符合，告知使用者後繼續流程（等同於不排除任何變更，所有變更照常處理）
  2.  以下列格式輸出分析結果給使用者。「部分符合」的檔案必須列出**該檔案的所有 hunk**（含符合與不符合的），讓使用者能完整審核篩選是否正確：
  ```
  篩選結果：
  - [path/to/file1](path/to/file1) — 全部 commit
  - [path/to/file2](path/to/file2) — 部分 hunk：
    ✓ hunk 1（L12-25）：修改 login() 驗證邏輯
    ✗ hunk 2（L58-70）：修改 formatDate() 格式
    ✓ hunk 3（L102-115）：新增 auth middleware 呼叫
  - [path/to/file3](path/to/file3) — 全部不 commit
  ✓ = 會 commit　✗ = 不 commit（留在工作區）
  ```
  其中 `（L12-25）` 為 diff 中該 hunk 對應的大致行號範圍，摘要為該 hunk 變更內容的一句話描述。白名單中符合描述的 hunk 標 ✓，不符合的標 ✗；黑名單中符合描述的 hunk 標 ✗（排除），不符合的標 ✓（保留）3. 使用 AskUserQuestion 向使用者確認。question 文字須包含篩選摘要（注意：AskUserQuestion UI 不支援 markdown 渲染與換行，僅支援單行純文字）。格式範例：`篩選確認 — 全檔 commit 2 個, 部分 hunk 1 個（file2: 3 hunks 中 commit 2 個）, 全檔不 commit 1 個。是否正確？`。選項：- **確認繼續**：以此篩選結果繼續流程 - **終止並維持原狀**：結束整個流程，維持現有狀態不變 4. 若使用者選擇終止，結束流程

**判斷「明確」vs「模糊」的標準**：僅檢查使用者的**原始指令文字**（非 ARGUMENTS）。若使用者輸入的字串能在變更清單中精確匹配到檔案名稱或路徑（完整路徑或檔名部分匹配皆可），視為明確檔案名稱；否則一律視為模糊描述，進入確認流程。ARGUMENTS 中出現的檔案路徑不影響此判斷

**篩選粒度**：

- **明確檔案名稱**：一律以**檔案**為單位。指定的檔案整個包含或整個排除
- **模糊描述**：白名單與黑名單皆以 **hunk** 為最小單位。同一檔案中，符合描述的 hunk 與不符合的 hunk 可被分別處理。Untracked 檔案（新檔案）因無 diff hunk，視為不可拆分的單一單位

**安全保證**：整個流程只操作 staging area（`git add`、`git apply --cached`、`git reset`、`git commit`），絕不修改或刪除工作區檔案內容。被篩選排除的變更（無論是整個檔案或個別 hunk）會保留在工作區中作為未 commit 的變更，不會遺失

**篩選結果傳遞**：Step 2 的篩選結果（哪些檔案/hunk 會被 commit）直接作為 Step 3 的輸入範圍。Step 3 僅對通過篩選的變更進行分組，被排除的變更不參與分組。若篩選產生了「部分 hunk」的檔案，Step 3 分組與 Step 4 staging 都必須使用 patch 方式精確處理這些 hunk

若套用篩選後沒有剩餘的變更，回覆「套用篩選後，沒有需要 commit 的變更。」並結束。

### Step 3：分析與分組

根據 Step 2 篩選後的變更內容（含整檔與個別 hunk），將其分成邏輯上獨立的 commit 群組。分組原則：

- **參考對話 context**：根據對話內容輔助判斷哪些變更屬於同一功能或修正。如果此對話中沒有先前的 context 可參考，則僅根據變更內容本身判斷
- **按內容的功能/目的分組**：同一個功能或修正的相關變更放在一起
- **按類型分組**：`feat`、`fix`、`docs`、`refactor`、`chore` 等不同類型分開
- **設定/工具鏈變更獨立**：CI、lint 設定、hook 等基礎設施變更獨立一組
- **同一檔案可拆分**：若單一檔案包含屬於不同群組的 hunk，使用 patch 方式精確 staging（見 Step 4）
- **Commit 順序**：基礎設施/config 變更先 commit，功能/文件變更後 commit（後者可能依賴前者）
- **永遠使用完整檔案路徑**（從 repo root 起算）進行 `git add`，不使用目錄名稱或 glob pattern
- **檔案路徑使用 markdown link**：分組表格中的檔案路徑必須使用 `[path](path)` 格式，使其在 VS Code 中可點擊

向使用者展示分組表格後，依 Step 0 的模式判斷結果決定後續：

- **自動模式**：直接開始執行 Step 4，不等待確認
- **互動模式**：使用 AskUserQuestion 詢問使用者是否確認分組計畫。開啟 allowFreeformInput（UI 上會出現無標籤的文字輸入框作為第三個選項）。question 文字需包含兩部分（純文字單行）：① 群組數量與各群組的 type/標題摘要，② 明確提示使用者可用第三個選項輸入調整需求。格式範例：`共 3 組：1) chore: 更新 ESLint 設定 2) fix: 修正登入驗證 3) docs: 更新 README。確認請選「開始 commit」；若想調整分組，可在第三個選項輸入需求（例如：把第 1 和第 2 組合併）。`。固定選項：
  - **確認，開始 commit**：以此分組繼續執行 Step 4
  - **終止**：結束整個流程，維持現有狀態不變

  若使用者輸入了自由文字（調整需求），根據其描述重新分組，再次展示分組表格並以相同方式詢問確認，重複此循環直到使用者按下「確認，開始 commit」或「終止」。

#### 分組範例

假設 `git status` 與 `git diff HEAD` 顯示以下變更：

```
修改：  .eslintrc.js                          （新增一條 rule）
修改：  src/components/Button.jsx             （hunk A: 修正 onClick 事件 bug, hunk B: 新增 disabled prop）
新檔案: src/components/__tests__/Button.test.jsx （新增 disabled prop 的測試）
修改：  README.md                              （更新元件文件）
```

分組結果：

| 順序 | 類型    | 檔案                                                                                                                                                   | 需 hunk 拆分                   |
| ---- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------ |
| 1    | `chore` | [.eslintrc.js](.eslintrc.js)                                                                                                                           | 否                             |
| 2    | `fix`   | [src/components/Button.jsx](src/components/Button.jsx)（hunk A）                                                                                       | **是**                         |
| 3    | `feat`  | [src/components/Button.jsx](src/components/Button.jsx)（hunk B）、[src/components/**tests**/Button.test.jsx](src/components/__tests__/Button.test.jsx) | **是**（Button.jsx 的 hunk B） |
| 4    | `docs`  | [README.md](README.md)                                                                                                                                 | 否                             |

### Step 4：逐組 Commit

對每一組依序執行：

1. **Unstage all**：先 `git reset` 確保 staging area 乾淨（若沒有任何 staged 變更則跳過）
2. **Stage 檔案**：
   - 一般檔案（含 untracked）：`git add <file1> <file2> ...`
   - 需拆分 hunk — 使用 patch 方式精確 staging：
     1. `git diff -- <file>` 取得完整 diff
     2. 從 diff 中擷取需要的 hunk（保留 diff header 及目標 `@@` 區段）
     3. 將擷取的 patch 寫入暫存檔（例如 `/tmp/partial.patch`）
     4. `git apply --cached /tmp/partial.patch` 套用至 staging area
     5. 刪除暫存 patch 檔
     6. 若 `git apply --cached` 失敗（patch 格式錯誤等）：
        - **Step 3 分組拆分**（同檔案不同 hunk 分屬不同 commit 群組）：放棄拆分，將整個檔案歸入該檔案變更量較大的那一組
        - **Step 2 篩選拆分**（同檔案部分 hunk 被篩選排除）：白名單時將整個檔案包含（可能多 commit 不符合描述的 hunk），黑名單時將整個檔案排除（可能少 commit 部分 hunk），並告知使用者
3. **驗證 staging**：
   - `git diff --cached --stat` 確認檔案清單正確
   - 若該組使用了 patch 方式拆分 hunk，額外執行 `git diff --cached -- <file>` 確認 staged 的是預期的 hunk（而非僅看 stat）。若 staged 內容不正確，執行 `git reset HEAD -- <file>` 後將整個檔案歸入該檔案變更量較大的那一組，不再嘗試拆分
4. **Commit**：使用 HEREDOC 格式撰寫 commit message

### Commit Message 規範

- 必須遵循 [Conventional Commits](https://www.conventionalcommits.org/) 格式（commitlint commit-msg hook 會驗證），type 使用英文（`feat`、`fix`、`docs`、`refactor`、`chore` 等），scope 選填
- 使用繁體中文（台灣）撰寫 description 與 body，技術名詞維持英文原文
- 標題簡潔（不超過 72 字元）
- 必要時加 body 說明「為什麼」
- 使用 HEREDOC 確保格式正確：

  ```bash
  git commit -m "$(cat <<'EOF'
  type: 標題

  Body（選填）
  EOF
  )"
  ```

### Step 5：驗證結果

完成所有 commit 後：

1. `git status` 確認工作區狀態
2. `git log --oneline -N`（N = 新 commit 數量 + 2）展示結果
3. **Push（若使用者要求）**：若使用者明確要求 push 且所有群組均成功 commit（無跳過），執行 `git push`（若當前分支尚未設定 upstream，使用 `git push -u origin <branch>`）。若有群組被跳過，告知使用者 push 已略過，需手動處理。Push 失敗處理見注意事項「Push 策略」
4. 向使用者輸出以下格式的完成摘要：

```
## 完成摘要

✅ 成功建立 N 個 commit[ 並 push 至 remote]

**Commit:**
- `hash1`（X 個檔案）- commit message 1
- `hash2`（Y 個檔案）- commit message 2

[**Push 結果:**
- 已推送至 `origin/<branch>`]

[**未處理的變更（依使用者指定篩選）:**
- 以 markdown link 格式列出未處理的檔案及 hunk]

[**未 commit 的變更（hook 錯誤跳過）:**
- 列出被跳過的檔案]
```

- `[ ]` 內的區塊僅在對應情境時顯示（有 push 時顯示 Push 結果，有篩選排除的變更時顯示未處理清單，有跳過時顯示未 commit 變更）

## 注意事項

- **Push 策略**：預設不 push。若使用者明確要求 push，在所有群組都成功 commit 後執行 `git push`（若當前分支尚未設定 upstream，使用 `git push -u origin <branch>`）。若有群組被跳過，告知使用者並不自動 push。**嚴禁使用 `--force` 或 `--force-with-lease`，此為最高鐵則。** Push 失敗時：
  - **網路錯誤**（連線逾時、DNS 解析失敗等）：自動重試，最多 3 次。仍失敗則將錯誤訊息完整呈現給使用者
  - **Non-fast-forward（remote 有新 commit）**：將錯誤訊息呈現給使用者，請其自行處理（pull / rebase），不自動操作
  - **其他錯誤**（權限不足、remote 不存在等）：將錯誤訊息完整呈現給使用者
- **不主動修改內容**：正常流程只做 staging 和 commit，不改動任何檔案內容。唯一例外是 pre-commit hook 失敗時，經使用者明確授權的修復操作
- **安全第一**：如果 patch 方式的 hunk 拆分不確定，寧可把整個檔案歸入較大的群組，也不要漏掉變更
- **pre-commit hook 失敗**：若 commit 被 hook 拒絕，**嚴禁未經授權的自動修復**。必須按以下流程處理：
  1. **解析錯誤**：從 hook 輸出中提取每一個錯誤，整理成清單，每條包含：錯誤訊息、完整檔案路徑（從 repo root 起算）、行數
  2. **報告錯誤**：將錯誤清單完整呈現給使用者。檔案路徑必須使用 **markdown link 格式**，使其在 VS Code 中可點擊：`[path/to/file.ts:42](path/to/file.ts#L42)`
  3. **詢問處理方式**：使用 AskUserQuestion 詢問使用者。同類錯誤（同一 rule/同一修復方式）合併為一組詢問，不需逐條問。**question 文字必須包含 rule 名稱、錯誤訊息、完整檔案路徑與行數**（注意：AskUserQuestion UI 不支援 markdown 渲染與換行，僅支援單行純文字）。格式：`如何處理 <rule-name>：<錯誤訊息>（<檔案路徑>:<行數>）錯誤？`。若同組有多個檔案，括號內用 `, ` 串接各路徑。選項建構規則：
     - **Linter auto-fix**：檢查該 rule 是否支援 `--fix`。若支援，提供「使用 linter 自動修復（具體指令：`eslint --fix` / `stylelint --fix` / `yarn lint:docs:fix`）」選項。若該 rule 不支援 auto-fix，**省略此選項並在 question 文字末尾附上說明**（固定用語：「此 rule 不支援由 linter 等工具 auto-fix。」）。
     - **Agent 修復**：提方案前必須查閱 CLAUDE.md、lint 規則等專案規範。**若修復方式不只一種，每種方式列為獨立選項**，各自附上具體方案說明。選項文字固定以「由 Agent 修復：」開頭，後接具體方案。例如 `no-unused-vars` 應提供：「由 Agent 修復：加 `export` 導出」、「由 Agent 修復：加 `_` 前綴標記為刻意未使用」、「由 Agent 修復：刪除該變數」等。
     - **不修復**：固定提供「不修復，由人工接手處理」選項。
  4. **執行使用者選擇的方案**：僅執行使用者核准的修復操作
  5. **重新 staging 並建立新 commit**（不使用 `--amend`，因為前次 commit 未成功）。若 pre-commit hook 再次失敗，從步驟 1 重新開始處理新的錯誤。**同一組最多重試 3 次**，超過則跳過該組並告知使用者。若 commitlint（commit-msg hook）拒絕 message 格式，直接修正 message 重試，不需詢問使用者，此類重試不計入 3 次上限
  6. **若使用者對所有錯誤都選擇不修復**：跳過此組 commit，告知使用者這些變更維持未 commit 狀態，繼續處理下一組
- **跳過組後的 re-staging**：若某組被跳過，且該組與後續組共享同一檔案（透過 hunk 拆分），後續組 staging 該檔案時**必須**再次使用 patch 方式精確 staging，不可用 `git add <file>`（否則會把被跳過組的 hunk 一併 stage 進來）
