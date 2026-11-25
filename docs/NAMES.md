# 名稱對照表

2026-11-22 起照第 1 節的原則命名。之前的名字是隨手取的,沒有規則;已經存在的資料夾、備份和記錄都不改名,舊名字的意思查第 3、4 節。

## 1. 命名原則

| 對象 | 原則 | 例子 |
|---|---|---|
| 階段 | 名字代表功能,固定不變。工單只改文字時不換名字,版本記在 `docs/GFLOW_EVOLUTION.md` 和執行記錄裡 | `UD` 一直叫 `UD` |
| 流程版本 | `f` + `GFLOW_EVOLUTION.md` 的版本號。版本 6 之後的第一個改動是 `f7` | `f7` |
| 回合 | 題目簡稱 + 流程版本 + 兩位序號 | `aes0005-f7-01`、`cla0005-f7-01` |
| dry run | `dry-` + 題目簡稱 + 階段 + 兩位序號 | `dry-aes0005-B2-01` |
| 同一回合裡的工單 | 階段小寫 + 第幾個範圍;接續工單加 `r`;同一張工單的第幾次重寫加 `b`、`c`;主機檢查後交回事實的續接加 `h`,事實仍在再加一次成 `hh`(最多兩次)(B,2026-11-23 起) | `b2`、`b2r`、`a2b`、`b2p1h` |
| 一個範圍拆成幾張 | 範圍名後加 `p` + 第幾張(2026-11-22 起);dry run 寫成大寫 `B2P1` | `b2p1`、`b2p2r`、`dry-aes0005-B2P1-01` |
| 讀工單的測試 | `read-` + 題目簡稱 + 階段與範圍(大寫)+ 兩位序號:Qwen 只讀那張工單並寫下理解、做法、不清楚之處,不執行(2026-11-25 起;`orch/read_order.py`) | `read-aes0005-B1-01` |

題目簡稱:`aes0005` = `cvdp_agentic_AES_encryption_decryption_0005`,`cla0005` = `cvdp_copilot_Carry_Lookahead_Adder_0005`。

## 2. 階段

現在用的名字在左欄。「舊名字」是同一個階段在程式或資料夾裡出現過的其他名字。

| 名字 | 做什麼 | 舊名字 | 出現的版本 |
|---|---|---|---|
| `M` | Qwen 依題目文字和文件寫參考模型,不看 RTL | | 1b 起 |
| `A`、`A2` | RTL 逐句翻成 Python 模型;`A2` 是模型和 RTL 不一致時的重做 | | 1 起 |
| `B` | 一塊一塊對規格查,找出塊內的錯並加開關 | | 1 起 |
| `C1`、`C2`、`C2A`、`C2B` | 控制的走法、運算序列(版本 1 和 1b;版本 2 起不用) | | 1、1b |
| `E` | 下層模組:每個控制狀態下一拍存什麼 | | 2 起 |
| `UA1`、`UA2`、`UB` | 下層模組:寫走法檢查器、逐一試候選開關、整個運算序列 | `UA`(未拆開前) | 2 起 |
| `T` | Qwen 依架構給的時序規格寫時序模型,不看 RTL | | 3 起 |
| `TN` | `T` 的變體:規格沒定的值,模型回傳 None | | f7 準備中(加法器) |
| `UT` | 設計模型對時序模型(版本 3;之後被 `UD`、`UC` 取代) | | 3 |
| `UD` | 頂層的資料路徑:`stepfacts` 第 1 部分,資料暫存器對參考的步驟記錄 | `UW`(加修改清單)、`UX`(加帳本的 RTL 修改) | 4 起 |
| `UC` | 頂層的控制與交握:`stepfacts` 第 2 部分和 `hsfacts`,對時序模型 | `UQ`(加修改清單)、`UY`(加帳本的 RTL 修改) | 4 起 |
| `UP` | 沒有步驟記錄的設計:每個輸出埠逐拍對時序模型(`portfacts`) | | f7 準備中(加法器) |
| `D`、`D2` | Qwen 把開關寫回 RTL(版本 1 到 5) | | 1~5 |
| `LB` | 補登帳本:先前的開關逐筆寫進帳本,每筆附 RTL 修改 | `DL`(修改清單) | 6 起 |
| `LF` | 主機比對有差異時,只修主機指出的那一筆 | `DL2` | 6 起 |

程式裡 `UX`、`UY` 於 2026-11-22 改回 `UD`、`UC`。這兩個階段的工單資料夾本來就叫 `-ud`、`-uc`,所以資料夾名字不變。

## 3. 回合:舊專案 `multi-ai/claude/cvdp_qwen_lora_traj`

版本號是 `docs/GFLOW_EVOLUTION.md` 的版本。題目沒寫的都是 `aes0005`。日期取自各回合請求記錄的檔名。

| 舊回合名 | 日期 | 版本 | 結果 |
|---|---|---|---|
| (沒有回合名,資料夾 `-a1`、`-b1`、`-c1`… `-d1`) | 11-13 | 1 | 通過(演進文件稱 `d1`,多次人工接續)。資料夾名稱是推測對應,沒有逐一核對 |
| `g1` | 11-13 | 1 | 其他題第一批:`barrel_shifter_0001`、`lfsr_0001`、`signal_correlator_0015`、`cache_lru_0022` 都通過;`lfsr_0005` 的 B 做到一半停掉 |
| `x1`、`x2`、`x3` | 11-14 | 1b | `x3` 通過,`x1`、`x2` 沒通過 |
| `f1` | 11-15 | 1b | 停在 A2(模型不等於 RTL) |
| `h1` | 11-15 | 1b | 演進文件沒有記錄 |
| `h2` | 11-15 | 1b | 走完,隱藏測試沒過 |
| `n1` | 11-16 | 1b | C2 三次被切斷 |
| `s1` | 11-16 | 1b | C2A 沒完成 |
| `q1`、`q2`、`q3` | 11-16~17 | 2 | `q2`+`q3` 通過(分層流程第一次) |
| `t1`、`v1`、`w0` | 11-17~18 | 2 | 停在頂層的 UA2 或 UB |
| `w1` | 11-18 | 2 | 走完,隱藏測試沒過 |
| `y1` | 11-18 | 3 | UT 三次被切斷 |
| `z1`、`z2`、`z3` | 11-19 | 4 | `z2`、`z3` 通過 |
| `z4`、`z5`、`z5b` | 11-19 | 5 | `z4`、`z5b` 通過;`z5` 演進文件沒有記錄 |
| `z6`、`z6b`、`z7` | 11-19 | 5 | `z6`、`z7` 通過(`z6` 有一次人工接續) |
| `z8`、`z9` | 11-20 | 5 | 通過 |
| `z10` | 11-20 | 6 | 通過 |
| `z11` | 11-20 | 6 | 主機擋下(Qwen 改了無開關的模型) |
| `z12`、`z13`、`z14` | 11-20 | 6 | 連續三輪通過 |

另外還有給 LoRA 和取樣實驗用的回合(`loop-*`、`pilot-*`、`s2-*`、`smoke-*`、`m4_*`、`map2_*`),不是 gflow 的回合,這裡不列。

## 4. 回合:新專案 `claude/cvdp_bug_fix`

| 舊回合名 | 日期 | 題目 | 內容 | 結果 |
|---|---|---|---|---|
| `dry1`、`dry2`、`dry3` | 11-20~21 | aes0005 | 重播 dry run:用先前回合的檔案代替 Qwen,只測驅動程式 | `dry1` 停在 A(沒有 DONE)、`dry2` 停在激勵檢查;修正後 `dry3` 走完 |
| `dc2`~`dc6` | 11-21 | cla0005 | Claude 扮 Qwen 的 dry run,M 到 UP | `dc6` 通過隱藏測試 |
| `r1` | 11-21 | aes0005 | Qwen 實跑,從 M 開始 | 停在 B2(無開關模型和 RTL 不同) |
| `r2` | 11-21 | aes0005 | Qwen 實跑,從 B 接續 | 使用者停掉(B2、B2r、E1 做完,UA1 進行中) |
| `r3` | 11-21 | aes0005 | Qwen 實跑,從 r1 的金鑰展開接續,只重做 B2 | B2、B2r 都超時,沒寫 DONE;找到 6 個錯中的 4 個 |
| `r4` | 11-21~22 | aes0005 | 同 `r3`,技能第 1 點加一句(輸入照實際排法、只跑一拍) | 使用者停掉(B2 第 73 分鐘);Qwen 改用轉置的內部排法 |

dry run 的資料夾(`runs/dry_aes0005/`、`runs/dry_cla0005/`):

| 資料夾 | 內容 |
|---|---|
| `dry_aes0005/b2_prev` | B2 的 dry run,技能還沒加那一句;找到 6 個錯 |
| `dry_aes0005/b2s` | 原本要做 B2,因為資料夾名字的數字判斷錯,做成了 B1(金鑰展開) |
| `dry_aes0005/b2` | B2 的 dry run,技能加了那一句;找到 6 個錯 |
| `dry_cla0005/m`、`a`、`b`、`t`、`lb`、`up`、`upx` | 加法器各階段的 dry run |
| `dry_aes0005/dry-aes0005-LF-01`、`dry-aes0005-A2-01` | f7-01 的 LF 第 (2) 種情況和接著的 A2(模型同 session) |
| `dry_aes0005/dry-aes0005-B2-01` | B2,加了頂層介面的資料定義和排法規則;用 session 的模型,做到一半停掉 |
| `dry_aes0005/dry-aes0005-B2-02` | 同上,改用 haiku(之後的 dry run 都用最低的模型) |
| `dry_aes0005/dry-aes0005-B2-03` | B2 不給 fips197(haiku);10 分鐘,6 個錯都找到,沒有假開關 |
| `dry_aes0005/dry-aes0005-B2P1-01`、`dry-aes0005-B2P2-01` | B2 拆成兩張、拿掉走記錄(haiku);p1 7 分鐘 4 個開關,p2 5 分鐘 2 個開關,都正確 |
| `dry_aes0005/dry-aes0005-B1-01` | f7-05 的改動(piececheck、技能拿掉第 8 點、45 分鐘)下的 B1(haiku);約 40 分鐘,`ke_chain_word`、`ke_done_bit` |
| `dry_aes0005/dry-aes0005-B2P1-02` | 同上的 B2 p1(haiku);5 分鐘 3 個開關,漏掉 MixColumns 先讀後寫(每塊的輸入都固定住) |
| `dry_aes0005/dry-aes0005-B2P1-03` | 技能第 5 點加「一個步驟整段跑」後重跑(haiku);9 分鐘 5 個開關,含 `mc_after_xtimes` |
| `dry_aes0005/dry-aes0005-B2P2-02` | 接 B2P1-03 的 p2(haiku);約 35 分鐘,`load_index`、`ark_index`,沒有假開關 |
| `dry_aes0005/dry-aes0005-B2P1-04` | f7-05 後:技能「整段跑」加上「整段不同而各塊單獨都對,就是一塊不同的地方,不是跑法的錯」(haiku),從 r1-b1r 起 約 5 分鐘 4 個開關,含 `mixcol_after_loop`(整段跑看到 x,判為先讀後寫並用開關證明);主機驗證:不開它時 MixColumns 第 0–2 行為 x |
| `dry_aes0005/dry-aes0005-B2P1-05` | f7-06 後:order_b 兩句範圍限縮為跨週期(「how the steps of the whole operation follow one another over the cycles」),haiku,從 r1-b1r 起 | 5 個開關:xtimes_msb、mc_index、**mc_position**(整段跑看到 x、呼叫兩次得舊值,判為先讀後寫並用開關證明)、isr_row1、isr_row3(同一錯拆成兩個);沒把它推到後面的工單 |
| `dry_aes0005/dry-aes0005-B2P1-06` | f7-07 後:技能第 5 點「整段跑」改為參考模型步驟紀錄的每一步都跑(不由 Qwen 判斷哪步是幾塊一起算),第 8 點與 order_b 報告加「整段跑的步驟表」,haiku,從 r1-b1r 起 | 4 個開關:xt_chain_msb、mc_term_row、**mc_after_loop**、sr_dir;步驟表 3 列(ARK→IMC、ARK→ISR、IMC→ISR,無開關不同,全開 0 差)。曾試寫 /tmp(失敗,無檔) |
| `dry_aes0005/dry-aes0005-B1-02`、`dry_aes0005/dry-aes0005-B2P1-07` | f7-08 後(使用者同意「一起改」):B 的參考只用 M——order_b 刪第 2 步、比對步驟改為以 M 的函式用 piececheck.against;技能第 4、5 點改寫;「not verified」換成主機跑 M 的 ref_check.py 的結果;haiku,B1 從 r1-a2、B2P1 從 r1-b1r | B2P1-07:4 開關含 mixcol_after_xtimes,參考全用 M(XTIMES、gf_mul、InvMixColumns、InvShiftRows),against 40 次;B1-02:找到 103–106(拆成 4 個開關),參考用 M 的函式組合並對 KeyExpansion 驗過,against 約 190 次,看到 o_done 不會設但判為時序 |
| `dry_aes0005/dry-aes0005-B2P1-08` | 使用者同意:技能第 3 點改成「對應 M 的函式」(不再寫 must compute)、刪第 5 點「組合邏輯呼叫兩次」;order_b 兩處 must compute 同步;haiku,從 r1-b1r | 5 開關含 mixcol_after_loop,參考全用 M 的函式(無自寫公式),沒有呼叫兩次;但 against 0 次:只能固定一個訊號,讀多個訊號的塊改寫 run 迴圈 → against 的 hold 改為可給多個訊號(各由 M 的函式算出),技能第 5 點同步 |
| `dry_aes0005/dry-aes0005-B2P1-09` | 使用者同意:B 改給一頁使用說明 /code/lib/usage.md(tool/gflow/usage_b.md,70 行,通用名稱)取代讀函式庫原始碼(約 68 KB);工單檔案清單只列 svvec/sigdump/piececheck/basecheck 並指向它;against 可固定多個訊號;haiku,從 r1-b1r | 5 開關含 mc_after_loop,參考全用 M,against 108 次(9 塊 + 3 步,多訊號固定有用),讀函式庫約 14 KB(原 68 KB)。之後使用者同意:against 每次比對寫入 /code/work/against_log.jsonl;主機 B 交差後讀它,全開仍不一致、或不一致但從未全開重比的比對,當事實續接(後綴 h)。用 f7-08 b2p1r 模型與本試跑的腳本驗證兩種情況 |
| `dry_aes0005/dry-aes0005-B2P1-10` | 使用者同意(f7-09 後):工單範圍以 step() 劃界(同一 step() 內各塊合起來屬本工單,跨多個 step() 才交後面);主機事實對「全開仍不一致」加註「同一 step() 內的不一致,屬本工單範圍,比對全開一致才算完成」,續接最多 h、hh;haiku,從 f7-09 b2p1h(Qwen 寫成 loop-ordering artifact 的狀態)接續 | 撤回 artifact 結論,加 mixcols_outside_loop(145-148 移到迴圈後),InvMixColumns 整段全開 29/29 一致,basecheck 無差異。發現主機事實雜訊:同一比對換名字重跑、或固定的訊號 step() 根本沒讀(模型用區域變數)也被列為事實 → 主機改以(固定, 讀取)當一筆比對;piececheck 記下 step() 沒讀到的固定訊號(held_not_read,text_against 會說明),主機略過這些列 |
| `dry_aes0005/dry-aes0005-B2P2-03` | f7-11 的改法;haiku,從 f7-10 b2p1r(沒有 arrangement.json)起做 B2P2 | 依 MixColumns/ShiftRows 寫 arrangement.json(列在前,載入與 ARK 不用來決定);7 開關全對(加 ld_byte_index、ark_key_index,並為整步一致補 mc_after_loop);埠到埠三筆與每輪整步全開一致,basecheck 無差異。發現:排列套到金鑰(1408 位元)會出錯,haiku 改傳自己的函式 → 主機誤判排列不同 → 改為排列只套到形狀相符的值、函式在這些值上等於檔案排列時記為檔案排列;state 可為函式。haiku 指出設計在 round 1..10 都做 InvMixColumns(10 次,標準 9 次),屬跨週期,留給 UD |
| `dry_aes0005/dry-aes0005-B2P1-11` | 使用者同意(f7-11 後):arrangement.json 已有的沿用不改、本範圍沒給的陣列補上;值必須是排列名稱;主機檢查值、改動、缺排列;haiku,從 f7-11 b1h(檔內只有金鑰、signals 為文字)接 B2P1 | 在 signals 補 AddRoundKey、xtimes*、MixColumns、ShiftRows = rows as written(依 145-148 與 159-174),原項目未改;4 開關全對(xtimes_own_msb、mixcol_term_index、mixcol_after_loop、shiftrows_direction),全開 11 列一致;主機檢查只剩 B1 留下的文字值。試跑資料夾沒有 base_record.json,basecheck 不能跑(試跑工具的缺,非流程) |
| `dry_aes0005/dry-aes0005-B2P1-12` | 使用者同意(f7-12 後):B 工單續接後未完成即停;逾時的續接附主機事實(缺排列、全開仍不一致);刪「切成一個訊號一個方法」;haiku,從 f7-12 b2p1(逾時、無開關)續接 | 先在 signals 補 AddRoundKey、xtimes*、MixColumns、ShiftRows = rows as written;4 開關全對(xtimes04_08_msb、mixcol_index、mixcol_after_loop、shiftrows_direction),全開各段與四步合跑一致,basecheck 無差異。它另外比了範圍外的 AddRoundKey(全開不一致,是真錯)→ 主機會交回並續接:可接受(排列已定,提早找到不會錯)。haiku 曾在主機端直接改腳本文字(試跑紀律,非流程) |
| `dry_aes0005/dry-aes0005-B2P1-13` | 使用者同意(2026-11-25,read-aes0005-B1-01 之後):order_b 換成精簡版(5,231→2,393 字元;刪多週期單元、規格=task.md、整段跑改只留在技能;埠到埠那句只給頂層最後一張);技能第 2、3、5、6 點四處;haiku,從 f7-14 b1 起 | 排列 rows as written 加進 B1 的檔案、B1 條目未改;範圍內 4 錯全對(MixColumns 列索引拆成 3 個開關),有做整段跑並找到 mc_order;另外做了範圍外的 load(找到第 87 行)和 out(相符,無誤判);basecheck 無差異 |
| `dry_aes0005/dry-aes0005-B2P1-14` | f7-15 之後(我決定,2026-11-25):order_b 第 3 步加回「then each step of the reference model that the scope computes, run as one (skill, point 5)」;主機 arrangement 檢查:有 signals 條目時不比頂層 "place";haiku,從 f7-15 b1h 起 | 排列加進檔案、頂層 place 與 B1 條目未改;範圍內全對(xtimes 拆 2 個開關、MixColumns 列索引、fix_mc_pos 先讀後寫、ShiftRows);有整段跑(held AddRoundKey read MixColumns);basecheck 無差異 |
| `dry_aes0005/dry-aes0005-B1-15` | f7-16 之後(我決定,2026-11-25):order_b 第 4 步改成「`RtlModel.SWITCHES` is the dict … of every switch, also of a submodule」;piececheck.against 紀錄 state_from_input(state= 為函式時設的暫存器),主機整步檢查接受它;主機比對鍵去掉訊號的階層前綴;haiku,從 r1-a2 起 | 找到 103–106 字索引(拆成 4 個開關),RtlModel.SWITCHES = KeyExpansion.SWITCHES;每片都用 piececheck.against(state= 設暫存器、沒用 hold);basecheck 無差異 |

另有離線實驗,沒有呼叫 Qwen:`runs/tool_compare_aes0005/`(三個工具的比較)、`runs/hostlist_trial/`(主機的方塊清單,用 r3、r4、dry run 的狀態)。

## 5. 回合:flow f7

| 回合 | 日期 | 題目 | 內容 | 結果 |
|---|---|---|---|---|
| `aes0005-f7-01` | 11-22 | aes0005 | 從 B 接續(r1 的 B1、M),T 重跑;B2、B2r 超時;UD 第 1 張主機檢查不過,`udb` 補上 `init_nomixcol`;UC 後 LF `ucf` 超時,驅動加上第 (2) 種情況的路徑後從 `ucr` 接續:LF `ucfb` → A2 `ucfbm`(模型讀了金鑰展開計數器這一拍之後的值)→ UC `ucb` | **通過隱藏測試** |

| `aes0005-f7-02` | 11-22 | aes0005 | 同 f7-01 的起點(從 B 接續,T 重跑);B 加了頂層介面的資料定義和排法規則(A1、A1b、A2、A3)。看 B2 是否還有排法繞圈、假開關、超時 | 使用者停掉(B2 第 28 分鐘,20 個請求);排法第一次照規則判對,之後又回到載入推出的排法;輸出被讀成錯(`4j+i` 對 `i+4j`);工作檔存於 `-b2/stopped/work` |

| `aes0005-f7-03` | 11-22 | aes0005 | 同 f7-01 的起點;B 不給 fips197(依參考模型和頂層介面判斷) | B2 超時(75 分、64 個請求,快取沒有失效),只加了 xtimes、MixColumns 係數、ShiftRows 方向 3 個開關;排法繞圈;依決定在 B2 後停掉,改用拆開的 B2(f7-04) |

| `aes0005-f7-04` | 11-22 | aes0005 | 同 f7-01 的起點;B2 拆成 `b2p1`(xtimes、MixColumns、ShiftRows,定排法)和 `b2p2`(載入、輸出、AddRoundKey、SubBytes);B 不走步驟記錄 | **通過隱藏測試**(674 分)。b2p1、b2p2 都超時後接續完成,B2 找到 5 個錯,沒有假開關;UD `udr` 補上 MixColumns 先讀後寫,並以 `nextdata_r1`+`round_order` 重排每拍的運算(另一種正確切法);UC 超時後 `ucr` 完成,LF `ucf` → A2 `ucfm` → UC `ucb` |

| `aes0005-f7-05` | 11-23 | aes0005 | 同 f7-04 的起點;B 用 `piececheck`、技能拿掉第 8 點並加「一個步驟整段跑」、B 上限 45 分鐘 | **停止**(447 分):B2 135 分(f7-04 231)、找到 5 個錯但漏掉 MixColumns 先讀後寫(b2p1r 整段跑看到 x、推出原因,又照「固定讀的訊號」改回而報無);UD 143 分寫出大開關 `chain_order`(另寫整條鏈,內含沒寫進記錄的 xtimes/MixColumns 迴圈拆分);LF udf/udfb/udfc/udfcr 都修不好,主機比對停在 chain_order |
| `aes0005-f7-06` | 11-23 | aes0005 | 同 f7-05 的起點與改動;技能「整段跑」加上整段不同時的判讀(B2P1-04);`--to b` 前停(B 階段穩定優先) | **B2 找到 5/6**:T 17 分、b2p1 逾時 45 分、b2p1r 28 分(xtimes_msb_gate, mixcols_rows, shiftrows_dir)、b2p2 21 分(load_byte_index, addroundkey_byte_index)。漏 MixColumns 先讀後寫:b2p1r #38 整段跑看到 x 並認出原因,但以工單「does not judge ... how the whole operation is sequenced」和「從未初始化狀態的假象」排除。LB1 前由守衛停下 |
| `aes0005-f7-07` | 11-23 | aes0005 | 只跑 B(`--to b`),從 r1-a2 起 B1+B2;T 沿用 f7-06-t;order_b 範圍兩句限縮為跨週期(B2P1-05) | **B 停(116 分)**:b1 45 分逾時但完成,找到 keyexp_windex(開關寫在子模組 KeyExpansion.SWITCHES,RtlModel.SWITCHES 沒有,blockfacts 看不到);b2p1 34 分 3 個、b2p2 37 分 2 個。又漏先讀後寫:MixColumns 只在 xtimes 被固定時單獨比,InvMixColumns 從 AddRoundKey 到 MixColumns 從未整段跑;整體解密錯被當成跨週期的事。全對 0/3 |
| `aes0005-f7-08` | 11-23 | aes0005 | 同 f7-07 起點(只跑 B);技能第 5、8 點與 order_b 加整段跑步驟表(B2P1-06) | **B 停(230 分),改前基準**:B2 5/6(漏先讀後寫),b2p2r 也逾時(b_unfinished),開關 6 個在 RtlModel.SWITCHES、無假開關。b1 45+11 分,b2p1 45+39 分(漏先讀後寫:整段跑看到 X、說對原因,仍判為「跨迴圈/週期,交後面」),b2p2 45 分逾時:17:38 起單一請求重複迴圈 28 分(思考 13 萬字,結尾不斷寫 0)——sigdump 的錯誤訊息整串印出 1408 位元的值 → 工具改:錯誤訊息與 piececheck 的值超過 16 位數只印頭尾和位數 |
| `aes0005-f7-09` | 11-23 | aes0005 | 同 f7-08 起點(只跑 B);B 參考只用 M(order_b 刪第 2 步、技能 3/4/5 改寫、刪呼叫兩次)、ref_check 主機事實、usage.md 取代讀原始碼、against(多訊號、比對紀錄)、主機檢查續接 h、錯誤訊息長值縮短 | 244 分;B1 45+30+21h 對;B2P1 45+36+18h、B2P2 44+5h;B2 5/6,先讀後寫又漏(定位正確但寫成 loop-ordering artifact,引範圍句交給後面工單);無假開關;主機續接 3 次 |
| `aes0005-f7-10` | 11-23 | aes0005 | 同 f7-09 起點(只跑 B);工單範圍以 step() 劃界、主機事實加註並續接最多 h/hh、比對以(固定, 讀取)為準、held_not_read | 302 分;B1 45+16+9h+39hh 對(hh 起因:against 不能逐輸入驅動埠,Qwen 正確判為測試問題);B2P1 45+29 自行結束(Qwen 把每次都有的日期提醒當成新訊息,無工具呼叫就停),3 開關;B2P2 45+29+45h(逾時),h 事實後找到 mc_compute_order(先讀後寫,首次);但 B2P2 自行改判資料排列(以待測的 AddRoundKey 決定為轉置),假開關 od_byte_index(49),漏 load(87)、ARK(119);B2 4/6 + 1 假 |
| `aes0005-f7-11` | 11-24 | aes0005 | 同 f7-10 起點(只跑 B);使用者同意(通用改法):排列寫一次於 arrangement.json(技能 3),against 預設用它、記 place;最後一張頂層 B 工單比對埠到埠(載入、一整個 step()、輸出,技能 5),主機檢查;against 的 inputs_ports 可為函式、start=、可讀輸出埠;續接結束了沒 DONE 的續接再續一次 rr | 215 分;B1 40+9h 對(stepkey_word_index;h 起因正確:全開沒重比);B2P1 45+45 兩次逾時、0 開關:思考裡已找到 xtimes MSB、ShiftRows 方向、MixColumns 組合,但每次思考 4–7 萬字(5–9 分),又以範圍外且有錯的載入去定排列(B1 先寫的 arrangement.json 只有金鑰,place=as written),沒寫到開關;B2P2 28+36h+12hh:以 AddRoundKey 定為轉置,改寫 arrangement.json 成轉置(主機的排列不同事實因此消失),假開關 odata_byte_index(49);整步比對全開 20/20 不一致仍結束。主機缺陷:Qwen 重寫 against_log 後,依行數略過舊行使主機看不到任何比對 → hh 事實錯(說沒有比對),真正的整步不一致沒交回;已改為依內容判斷沿用行(carried_lines)。B2 0/6 + 1 假 |
| `aes0005-f7-12` | 11-24 | aes0005 | 同 f7-11 起點(只跑 B);arrangement.json 沿用不改、補本範圍陣列,值為排列名稱;主機檢查排列檔(值、改動)與比對缺排列;against_log 沿用行依內容判斷 | 約 280 分,b2p2hh 開始 2 分後由我停止(使用者指出工具有錯不應續跑);B1 45+21r+31h+8hh 對(stepkey_read_offset),arrangement.json 值為名稱;h/hh 起因是主機雜訊(測試修好後同開關已一致仍要求全開重比,30 筆逐行列出);B2P1 45+50 兩次逾時:比對用正確的 rows as written,3 開關(xtimes、ShiftRows 對;mixcolumns_index_order 寫錯,先讀後寫已看出未寫完),始終沒把 4×4 陣列寫進 arrangement.json;思考 58 萬字:第一張約 10 分在 i,j↔r,c(以有錯的 AddRoundKey、載入對照,結論翻轉 6 次以上),另有「切成一個訊號一個方法」規則與先讀後寫;B2P2 37+38h:檔案沒有 4×4 → 自行定為轉置並寫入,假開關 odata_index;埠到埠整步全開 25/25 不一致。工具缺陷:模型把 fix="all" 存成 ["all"],piececheck 記成非全開 → b2p2h/hh 的主機事實多數錯。已修:piececheck 與主機認得 ["all"];同開關後來一致即不再報;只差索引的事實合併。B2 2/6 + 1 假 |
| `aes0005-f7-13` | 11-24 | aes0005 | 同 f7-12 起點(只跑 B);B 工單續接後未完成即停;逾時續接附主機事實;刪切方法句;工具:認得 ["all"]、同開關後來一致不再報、同類事實合併 | 129 分後由我停止(B1 完成於 b1hh、B2P1 剛開始):B1 1/1 正確(開關 stepkey_four_earlier)、無誤判;b1h 與 b1hh 共 48 分是主機事實造成的多餘續接——工具把「把值打包成向量的自訂排列函式」判成與 arrangement.json 不同,且 signals 的陣列名不適用於帶索引的元素名。(模型 qwen3.8-nopen-exp-dflash2 於 11-24 重建:FROM qwen3.8-nopen-exp + DRAFT hf/Qwen3.8-27B-DFlash2,清單 ID 5aa1bb5105bb 與遺失的原檔雜湊相同) |
| `aes0005-f7-14` | 11-24 | aes0005 | 同 f7-13;工具:自訂排列函式回傳打包值時不判定與檔案是否相同、signals 的陣列條目也適用其元素(name[i]) | B1 一張工單 45 分完成,1/1 正確(開關 ke_src_word)、無誤判,但只有 SubWord 用 piececheck.against;B2P1 第一張逾時,續接結束時由我停止(使用者要求先做讀工單測試 read-aes0005-B1-01) |
| `read-aes0005-B1-01` | 11-25 | aes0005 | 讀工單測試:Qwen 讀 f7-14 的 B1 工單,寫理解、做法、不清楚之處(全文 docs/read/read-aes0005-B1-01.md) | 9 分完成;理解大致正確;指出多週期單元與跨 step() 兩句衝突、規格是 task.md 還是參考模型、埠到埠是否適用、arrangement.json 由誰建 |
| `aes0005-f7-15` | 11-25 | aes0005 | 同 f7-14 起點(只跑 B);精簡版 order_b 與技能四處修改(見 dry B2P1-13) | B 全程 178 分、8 張工單;6/7 正確(keyexp、xtimes、MixColumns 列索引、ShiftRows、load、ARK)、無誤判(o_data 相符);漏 MixColumns 先讀後寫:比對紀錄沒有整段跑(只各片單獨比),即精簡版拿掉的那句;B1 第一張逾時(50 分)、續接 35 分;主機事實 3 種:開關不在 RtlModel.SWITCHES(修好)、"place" 由 as written 改成 rows as written(兩次續接都沒改,signals 條目其實沒動,屬主機檢查過嚴)、ARK 未用全部開關比(修好) |
| `aes0005-f7-16` | 11-25 | aes0005 | 同 f7-15(只跑 B);order_b 第 3 步加回整段跑半句、主機排列檢查放寬(見 dry B2P1-14) | B 全程 233 分、8 張工單;7/7 正確(含 MixColumns 先讀後寫 mixcolumns_loop_position)、無誤判、排列正確、頂層 place 未改 → 第一輪全對(穩定 1/3);B2P1 第一張逾時;主機事實:B1 沒用 piececheck.against、開關不在 RtlModel.SWITCHES(正確,b1h 修好);b1hh 殘留的 step_key 一條是同一比對用子模組自己的名字與頂層路徑各做一次(主機當成兩個);B2P2 兩次續接的「沒有整步比對」是主機看不到 state= 設的暫存器(Qwen 其實做了且相符),共白花約 55 分 |
| `aes0005-f7-17` | 11-25 | aes0005 | 同 f7-16(只跑 B,穩定第 2 輪);order_b 第 4 步 RtlModel.SWITCHES、state_from_input、主機比對鍵去階層前綴(見 dry B1-15) | B1:第一張逾時 53 分、b1r 37 分完成、b1h 28 分(主機事實:沒驅動 reset 的埠到埠比對在全開關下仍不同;Qwen 之後用多一個埠的同一比對已相符,屬測試本身的差);B1 結果 1/1 正確(step_key_four_earlier)、開關在 RtlModel.SWITCHES。09:59 我在 b1h 剛結束時停了 driver(剛開始幾秒的 b2p1 改名為 `…-b2p1.stopped`,第一段輸出為 `runs/aes0005-f7-17.b1.out`);主機修正:同一比對驅動較多埠且相符時,較少埠的那次不再報;10:05 用 `--carry aes0005-f7-17-b1h --skip-b 1` 從 B2P1 接續。B2P1 45 分完成 + b2p1h 11 分(補全開關比對);B2P2 第一張逾時 45 分、b2p2r 36 分完成、b2p2h 11 分(補 load 與整步比對)。到 b2p2h 為止 7/7 正確、無誤判、排列正確。b2p2hh:主機事實是「整步比對最後一次在全開關下不同(設計全 0)」,那是 Qwen 自己第二次測試沒設好輪計數器;事實句尾的結論(「這是範圍內一步之內的差異」)讓 Qwen 以為主機找到了設計的錯,去查控制與金鑰擴展,第 43、45 次請求的思考與指令完全相同(迴圈);13:03 我停止(33 分,模型未被改動,工作資料夾存在 `…-b2p2hh/work_at_stop/`)。全程約 4.6 小時。不計入穩定輪(由迴圈停止) |

同一階段的主機比對之後的工單:`<階段名>f`、`fb`、`fc` 是 LF;LF 判定第 (2) 種情況時,接著的 A2 叫 `<LF 名>m`(例如 `ucfbm`);模型改過後重給的那張工單加 `b`(例如 `ucb`)。
