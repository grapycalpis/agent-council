# 最終報告範本

使用繁體中文。開頭先用兩三句給結論與成立條件，再按以下九節提供證據。
不要只貼八份 JSON，不使用「多數支持所以值得」作結論。

## 01 — Executive Verdict

狀態：RECOMMEND / CONDITIONALLY_RECOMMEND / NOT_RECOMMEND /
INSUFFICIENT_EVIDENCE。明列建議對象（多方案可並列或暫無）、必要條件、
主要理由及會推翻建議的證據。區分已知事實、假設與未解問題。

## 02 — Council Voting

預定 8 位／有效 N 位。表列 Agent ID、角色（A08 明示領域）、立場或排名、
信心與關鍵條件。單方案列四種票數；比較列每位排名、首選次數、並列及
無法比較數。缺席另列，驗證角色不入投票。票數不是成功機率。

## 03 — Strongest Supporting Arguments

列最強支持理由及來源／假設／適用條件，必要時顯示各方案六項評分及理由。

## 04 — Strongest Opposing Arguments

列最強反對與重要少數意見，指出是否已驗證或仍待解，不淹沒在總票數中。

## 05 — Critical Risks

按嚴重度、可逆性、後果、grounding、緩解與殘留風險呈現。
不可用高平均分數抵銷可信的災難性失敗模式。

## 06 — Evidence Verification

表列 Claim ID、主張、驗證角色、CONFIRMED / REFUTED /
PARTIALLY_SUPPORTED / UNRESOLVED、實際來源與限制。跳過時清楚說明無觸發，
不寫成「所有事實已查證」。無工具則寫未解；未啟動與啟動失敗分開列出。

## 07 — Alternatives

公平比較原方案、替代、折衷及維持現狀；不適用的基準說明原因。

## 08 — Recommended Next Steps

提出有交付物、時間／成本假設、成功／停止準則的小型可逆實驗。
僅提供建議，不直接實施。不得要求使用者手動協調代理或繼續工作流程。

## 09 — Audit Summary

- 預定／實際啟動／有效評審數、八位角色對應的原生代理 ID 與嘗試次數。
- 第一輪是否完整、何時鎖定、是否有機械式 hash、缺席／失敗與重試原因。
- 原生介面、自訂角色載入或通用工具適配、實際並行限制、分批次數。
- context history 是否停用、模型／推理強度是否可觀察；不可宣稱不可見設定。
- 第二輪是否觸發、理由、預定／完成驗證數、結果與未解主張。
- 工作區共用、權限繼承、證據工具／網路限制與相關模型偏誤。
- 本次結論重要限制及對確定性的影響。

如完全沒有真正 Subagent 能力，明列「Council 未執行」、0 票與
INSUFFICIENT_EVIDENCE，提供設定限制；不可用虛構評審填滿範本。
