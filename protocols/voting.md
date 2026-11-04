# 投票與評分

`schemas/review_result.schema.json` 定義結構；以下是同樣必須檢查的跨欄位語意。
維護用 `evals/council_checks.py` 提供相同規則的純函式，沒有派發或模型執行功能。

## 單方案

`recommendation.kind = SINGLE`，`option_id` 必須等於 packet 的 primary_option_id。
vote 為 SUPPORT、CONDITIONAL_SUPPORT、OPPOSE 或 INSUFFICIENT_INFORMATION。
有條件支持至少列一個可驗證條件；資訊不足至少列一項 information_gaps。
反對不等於沒有優點，支持也不等於沒有風險。

## 多方案

`recommendation.kind = COMPARISON`，使用 rankings（由優到劣的排名組）、
preferred_option_ids、comparability、conditions、information_gaps。
同一排名組的 option_ids 可並列；組的 rank 必須由 1 開始連續遞增（dense rank）。
可比較或部分可比較時，全部 packet 方案恰好出現一次，首組等於推薦方案集合。
PARTIAL 要列出資訊缺口，並對每個排名給理由。
完全無法比較時使用 INSUFFICIENT_INFORMATION，rankings 與 preferred_option_ids
均為空陣列並列出缺口，不強迫排出假名次。不得用單一支持／反對票代替比較。

## 分數、信心與證據

Value、Feasibility、Cost Efficiency、Risk Safety、Reversibility、Evidence Quality
六項均出現；每個方案分別評分。整數 1–5 或字串 N/A，每項都有理由。
分數越高表示該準則越有利；Risk Safety 5 代表較安全，不是風險更大。
N/A 不當成零，不加入平均。不適用經濟數據明示 N/A，不編造投資報酬或金額。
信心只用 LOW / MEDIUM / HIGH 加理由，代表判斷穩定度，不是真實成功機率。

證據 `kind` 區分 USER_PROVIDED、SOURCE、INFERENCE、ASSUMPTION。
SOURCE 必須有實際來源、locator、觀察日期及 VERIFIED / UNVERIFIED 狀態；
未開啟的連結不能標為 VERIFIED。ASSUMPTION 永遠是 UNVERIFIED。
「已查閱來源」仍不保證來源內容正確；重要主張在第二輪獨立查驗。
critical_risks 的 evidence_ids 必須指向同一回覆的 evidence；嚴重度與
evidence grounding 分開記錄，不把任何猜測都當成有根據重大風險。

## 統計與最終判斷

只計有效、已鎖定的 A01–A08，每個角色最多一票；缺席與格式失敗不算資訊不足票。
單方案列四種票數及有效分母。多方案列每位排名、共同首選的次數、並列次數及
無法比較數，不使用混淆的支持率。並列方案各獲一次「列入首選」計數，故總和
可能超過有效人數；須標示此口徑。V01/V02 永不加入分母。

票數只是輔助。不得以簡單多數決或平均分數直接決定建議，不能把票數／信心
稱為成功機率。所有 credible HIGH / CRITICAL 風險都需審查，保留重要少數意見。
缺關鍵專業、核心證據未解或零票時，須降低結論確定性，必要時
INSUFFICIENT_EVIDENCE。不要掩蓋不確定性以湊出明確答案。
