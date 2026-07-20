# Git-Commit Skill 使用指南

> 給人類工程師的呼叫手冊 — 如何讓 AI agent 幫你自動拆分並 commit 變更。

---

## 一句話說明

這個 skill 會自動分析工作區中所有未 commit 的變更，依功能/目的拆成多個語意清晰的 conventional commit，不需要你手動 `git add` 或想 commit message。

---

## 怎麼呼叫

在對話中直接說出包含「commit」的指令即可。以下是常見用法：

### 基本用法

| 你說的話 | 效果 |
|---------|------|
| `commit` | 分析所有變更，自動拆分成多個 commit（互動模式：分組後會停下來讓使用者確認） |
| `git commit` | 同上 |
| `執行 xxx 任務，都做完後幫我 commit` | 完成前面的任務後，再執行 commit（**自動模式**，不中斷等分組確認） |
| `git commit & push` | commit 完成後自動 push 到 remote |

### 篩選特定檔案

| 你說的話 | 效果 |
|---------|------|
| `commit foo.ts 與 bar.ts` | **白名單** — 只 commit 這兩個檔案 |
| `commit 除了 package.json 以外的變更` | **黑名單** — 排除指定檔案，其餘全部 commit |

### 用描述篩選（模糊比對）

| 你說的話 | 效果 |
|---------|------|
| `commit 只跟這個對話內容相關的變更` | 根據對話 context 判斷哪些變更相關 |
| `commit 除了 i18n 相關的以外` | 排除符合描述的變更 |
| `commit 只處理 lint 設定的更新` | 只 commit 與 lint 設定有關的變更 |

> **模糊篩選會先列出分析結果，等你確認後才繼續。** 你可以在確認時看到每個檔案甚至每個 hunk 的篩選判定。

---

## 不會被觸發的情況

以下情況 **不會** 啟動此 skill，即使 agent 覺得「應該 commit 了」：

- Agent 完成了 todo 清單中的任務
- 測試跑過了
- 程式碼改好了、流程推進了
- Agent 自己判斷「差不多可以 commit 了」

**唯一觸發條件：你本人在訊息中明確說出 commit 指令。**

---

## 執行過程中你會看到什麼

### 1. 前置檢查
- 確認 repo 沒有在 merge / rebase / cherry-pick 狀態
- 若已有 staged 變更，會詢問你怎麼處理（納入拆分 / 先 commit 現有 staging / 終止）

### 2. 變更分析
- 讀取 `git status`、`git diff HEAD`、近 10 筆 commit log
- 讀取 untracked 的文字檔內容以了解用途

### 3. 篩選（若你有指定）
- **明確檔案名**：直接包含/排除，不詢問
- **模糊描述**：列出每個檔案（甚至每個 hunk）的篩選判定，等你確認

### 4. 分組計畫
- 輸出分組表格，說明每個 commit 包含哪些檔案
- 依呼叫方式分兩種模式：
  - **互動模式**（單獨說 `commit`）：展示分組表格後等你確認。若分組不滿意，可在第三個選項直接輸入調整需求（例如「把第 1 和第 2 組合併」），agent 會重新分組再問一次，直到你確認為止
  - **自動模式**（commit 是其他任務的收尾，如「執行 xxx 任務，都做完後幫我 commit」）：展示分組表格後直接執行，不中斷等確認，以便 agent 在完成任務後能無縫接續 commit 流程不會卡住

### 5. 逐組 Commit
- 每組：清空 staging → stage 檔案 → 驗證 → commit
- 需要拆分 hunk 時會自動用 patch 方式處理
- Commit message 遵循 Conventional Commits，繁體中文描述

### 6. 完成摘要
```
✅ 成功建立 3 個 commit

Commit:
- `a1b2c3d`（2 個檔案）- feat: 新增使用者頭像上傳功能
- `d4e5f6a`（1 個檔案）- fix: 修正登入頁面表單驗證錯誤
- `b7c8d9e`（1 個檔案）- chore: 更新 ESLint 設定
```

---

## Pre-commit Hook 失敗時

如果 commit 被 pre-commit hook（如 ESLint、commitlint）擋下：

1. Agent 會列出所有錯誤（含檔案路徑、行數、rule 名稱）
2. 詢問你如何處理，通常有以下選項：
   - **Linter 自動修復**（若該 rule 支援 `--fix`）
   - **由 Agent 修復**（會列出多種可行方案讓你選）
   - **不修復，由人工接手處理**
3. 修復後自動重試 commit，同一組最多重試 3 次

---

## 安全保證

| 項目 | 保證 |
|------|------|
| 工作區檔案 | 不會被修改或刪除（除非 hook 失敗且你授權修復） |
| 被篩選排除的變更 | 保留在工作區，不會遺失 |
| `--force` push | **絕對不會執行**，這是最高鐵則 |
| `git reset --hard` | 絕對不會執行 |
| 內容修改 | 只做 staging 和 commit，不主動改程式碼 |

---

## Commit Message 格式

遵循 [Conventional Commits](https://www.conventionalcommits.org/)：

```
type(scope): 繁體中文標題（≤72 字元）

選填 body — 說明「為什麼」做這個變更
```

- **type** 使用英文：`feat`、`fix`、`docs`、`refactor`、`chore`、`test`、`style`、`perf` 等
- **scope** 選填
- **description / body** 使用繁體中文，技術名詞維持英文
- 會參考你近 10 筆 commit 的風格

---

## 常見 Q&A

**Q: 我可以只說「commit」就好嗎？**
A: 可以。最簡單的用法就是直接說 `commit`，agent 會自動處理一切。

**Q: 分組結果不滿意怎麼辦？**
A: 在互動模式下，分組表格出現後會等你確認。選第三個（輸入框）選項，直接描述你想要的調整（例如「把 chore 和 fix 合成一組」「把 config 變更獨立出來」），agent 會重新分組並再次確認，不需要整個重跑。

若你用的是自動模式（commit 是任務收尾），分組會直接執行。結果不滿意的話，用 `git reset --soft HEAD~N`（N = commit 數量）回到 commit 前，直接說 `commit` 觸發互動模式再調整。

**Q: 想 push 但有些組被跳過了？**
A: Agent 會告知你有組被跳過，不會自動 push。你需要手動處理被跳過的變更後再自行 push。

**Q: 只想 commit 剛才對話中改過的檔案？**
A: 說 `commit 只跟這個對話內容相關的變更`，agent 會根據對話 context 判斷。

**Q: 可以在 agent 完成任務後自動 commit 嗎？**
A: 可以，在任務指令中加上 commit 即可，例如「幫我把 Button 元件重構成 TypeScript，完成後 commit」。
