# cvdp_qwen_gflow

用本機的 Qwen 模型解 CVDP 的 RTL 除錯題。目前只有一題:`cvdp_agentic_AES_encryption_decryption_0005`。通過標準是 CVDP 官方的隱藏測試(cocotb)。

這是從專案 `cvdp_qwen_lora_traj`(倉庫 `multu-ai-claude-v2`,標籤 `gflow-v6-2026-11-20`)取出的最精簡版本,只留現行流程用得到的檔案。流程的演進與量測結果見那個倉庫的 `docs/GFLOW_EVOLUTION.md`。

## 流程

每一張工單都在新的容器裡由 Qwen 執行;工單之間由主機上的固定程式銜接,主機不使用模型。

| 階段 | 工單 | 內容 |
|---|---|---|
| m | M | 只依題目與文件寫參考模型(不看 RTL) |
| a | A(A2) | 把 RTL 逐句翻成 Python 模型;主機用模擬器比對模型與 RTL,不同時發 A2 |
| b | B | 每個模組一張:各區塊對文件檢查,找到的錯做成模型裡的開關 |
| k | E、UA1、UA2、UB | 下層模組(金鑰展開)當成一個單元檢查 |
| t | T | 依時序規格寫頂層的時序模型(不看 RTL) |
| top | LB、UD、UC(LF) | 頂層:開關逐筆登進帳本並附 RTL 修改;資料路徑對參考的步驟記錄;控制與交握對時序模型 |
| | 官方隱藏測試 | 對帳本產生的 RTL 評分 |

頂層每一階段之後,主機把帳本的修改全部套到 RTL、模擬、和模型逐拍比對;不同時找出第一筆不同的,發一張只修那一筆的工單(LF,最多三次)。

## 需要先有的東西(不在 git 裡)

| 項目 | 說明 |
|---|---|
| CVDP 資料集 | `cvdp_v1.1.0_agentic_code_generation_no_commercial.jsonl` 與 nonagentic 那一份,放在 `datasets/`(可用連結),或以環境變數 `CVDP_DATASETS` 指定資料夾。題目檔與隱藏測試都從這裡讀。 |
| Docker 映像 `lora-s3xcell:v4-20261111` | Qwen 的容器;建置檔在 `tool/docker/stage3x_cell/`,它以映像 `lora-rtl` 為底,那個映像的建置檔不在這個倉庫。 |
| Docker 映像 `lora-rtl:dev` | 模擬器與官方測試用。 |
| 模型後端 | Ollama 在 `127.0.0.1:11435`,模型 `qwen3.8-nopen-exp-dflash2`。 |
| Docker、Python 3 | 主機程式只用標準函式庫。 |

## 執行

```bash
python3 -m orch.run_aes0005 --check
```

```bash
python3 -m orch.run_aes0005 r1 > runs/r1.log 2>&1
```

- 第一行檢查上表各項是否齊全,不呼叫模型。
- 第二行從 M 跑到官方測試。`r1` 是這一輪的名字,每輪用新的名字;同一時間只能跑一輪。
- 每張工單印一行 JSON;最後一行的 `passed` 是官方測試結果,`stopped` 是流程自己停下的原因。
- 工單的資料在 `runs/gf_tic_AES_encryption_decryption_0005-r1-<工單>/`。`runs/` 不在 git 裡,要保存用 `./backup_run.sh runs/<資料夾>`。
- 從中間接續:`python3 -m orch.run_aes0005 r2 --from top --carry r1-u1c --ref r1-m --timed r1-t`(階段名見上表)。

## 不用模型的試跑

環境變數 `GFLOW_REPLAY` 指向一個 JSON 檔(工單名對應到先前某一輪的工單資料夾)時,容器、檔案、主機檢查照常進行,Qwen 的輸出由那一輪留下的檔案代替。用來確認流程接得起來,不驗證模型。

## 檔案

| 位置 | 內容 |
|---|---|
| `orch/run_aes0005.py` | 進入點;這一題的模組名與報告檔名寫在這裡 |
| `orch/gflow.py`、`gflow_auto.py` | 工單、容器、接續、主機檢查 |
| `orch/cell.py`、`map_cell.py`、`map_s3x_cell.py`、`run_order.py`、`support.py` | 容器與代理的啟動、工單的執行與收回 |
| `orch/grade.py`、`dataset.py` | 官方測試與資料集 |
| `proxy/record_proxy.py` | 模型後端前面的記錄代理(重複偵測、舊思考的取捨) |
| `tool/gflow/` | 容器內給 Qwen 的函式庫,與主機的模擬比對工具 |
| `tool/skills/` | 技能 |
| `data/stages/gflow/` | 工單文字、給 Qwen 的時序規格 |

## 已知的限制

- 只在這一題、一台 64 GB 的 Mac 上跑過。時序規格(`data/stages/gflow/spec_aes0005/`)是另外給的,不是 Qwen 從題目推出來的。
- 從 M 一路自動跑到底的驅動程式是新寫的;先前通過的回合是從已完成的前半段開始的。
- 提示超過約 12 萬 token 時後端可能整段重讀(每次 4 到 5 分鐘)。
- 隱藏測試的內容不可給 Qwen,也不可寫進工單或技能。
