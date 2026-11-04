"""不新增事實與票數的繁體中文報告，所有建議均保留角色來源。"""

import html

from .domain import PHASE_LABELS, VOTE_LABELS, Json


def md(value: object) -> str:
    return html.escape(str(value), quote=False).replace("|", "\\|").replace("\n", "<br>")


def render_report(idea: Json, state: Json, snapshot: Json, summary: Json) -> str:
    mock = snapshot["backend"]["execution_kind"] == "mock"
    label = "確定性模擬｜沒有執行真實陪審代理" if mock else "原生互動收件｜執行來源由操作者聲明"
    lines = [
        f"# Agent Council 決策報告：{md(idea['title'])}",
        "",
        f"> **{label}**",
        "",
        "## 1. 提案概覽",
        "",
        md(idea["description"]),
        "",
        f"背景：{md(idea['context']) or '未提供，列為不確定性'}",
        "",
        "目標：" + "；".join(map(md, idea["goals"])),
        "",
        "限制：" + "；".join(map(md, idea["constraints"])),
        "",
        "使用者提供證據："
        + (
            "；".join(md(e["claim"]) for e in idea.get("evidence", []))
            or "未提供，所有外部效果主張均需驗證。"
        ),
        "",
        "## 2. 執行摘要",
        "",
    ]
    final = summary["final"]
    majority = final["majority"]
    if not summary["complete"]:
        recommendation = "資料不完整，暫緩形成整體建議，先補足失敗評估或辯論。"
    elif majority:
        recommendation = f"有效終評的嚴格多數為「{VOTE_LABELS[majority]}」。"
    else:
        recommendation = "未形成嚴格多數，保留分歧，先進行可逆實驗與補證。"
    if mock:
        recommendation = "【模擬流程示範，不適用於實際決策】" + recommendation
    lines += [
        recommendation,
        "",
        f"有效初評 {summary['initial']['valid_count']}/12；有效終評 {final['valid_count']}/12。",
        "",
        "票數是角色輸出的計數，不是成功或正確機率；共識不構成證明。",
        "",
    ]
    records = state["records"]

    def output(key: str) -> Json | None:
        record = records.get(key, {})
        return record["response"]["output"] if record.get("status") == "ok" else None

    for number, side, title in ((3, "pro", "最強正方論點"), (4, "con", "最強反方論點")):
        lines += [f"## {number}. {title}", ""]
        for phase in ("opening", "rebuttal"):
            record = output(f"{phase}.{side}")
            lines += [f"### {PHASE_LABELS[phase]}", ""]
            if not record:
                lines += ["此階段失敗或缺件，沒有補造論點。", ""]
                continue
            lines += [f"- {md(a)}" for a in record["arguments"]]
            for e in record["evidence"]:
                lines += [
                    f"- 證據狀態 `{e['status']}`：{md(e['claim'])}；"
                    f"來源：{md(e['source'] or '無')}；{md(e['verification_note'])}"
                ]
            lines += [
                "- 假設：" + "；".join(map(md, record["assumptions"])),
                "- 未知：" + "；".join(map(md, record["uncertainties"])),
                "",
            ]
    lines += [
        "## 5. 十二位陪審員評估表",
        "",
        "| 角色／ID | 初評 | 終評 | 變動 | 初評→終評信心 | 終評理由 |",
        "|---|---|---|---|---|---|",
    ]
    for role in snapshot["roles"]["jurors"]:
        rid = role["id"]
        initial, ending = output(f"initial.{rid}"), output(f"final.{rid}")
        changed = (
            "無法比較"
            if not initial or not ending
            else ("是" if initial["vote"] != ending["vote"] else "否")
        )
        lines += [
            f"| {md(role['name'])} / `{rid}` | "
            f"{VOTE_LABELS[initial['vote']] if initial else '失敗／缺件'} | "
            f"{VOTE_LABELS[ending['vote']] if ending else '失敗／缺件'} | {changed} | "
            f"{initial['confidence'] if initial else '—'} → "
            f"{ending['confidence'] if ending else '—'} | "
            f"{md(ending['reasoning']) if ending else '沒有有效回覆'} |"
        ]
    lines += ["", "## 6. 初評與終評票數", "", "| 票種 | 初評 | 終評 |", "|---|---:|---:|"]
    for vote, name in VOTE_LABELS.items():
        lines += [
            f"| {name} `{vote}` | {summary['initial']['counts'][vote]} | {final['counts'][vote]} |"
        ]
    lines += ["", "棄權是有效輸出；代理失敗與缺件不列入任何票種。", "", "## 7. 立場變動與理由", ""]
    for change in summary["changes"]:
        before = VOTE_LABELS.get(change["initial_vote"], "無有效初評")
        lines += [
            f"- `{change['agent_id']}`：{before} → {VOTE_LABELS[change['final_vote']]}；"
            f"{md(change['reason'])}"
        ]
    lines += ["", "## 8. 多數、少數與分歧檢視", "", recommendation, ""]
    for role in snapshot["roles"]["jurors"]:
        ending = output(f"final.{role['id']}")
        if ending:
            group = (
                "多數立場"
                if ending["vote"] == majority
                else ("少數／棄權立場" if majority else "分歧觀點（無嚴格多數）")
            )
            lines += [f"- {group} `{role['id']}`：{md(ending['reasoning'])}"]
    lines += ["", "### 多數未採納的疑慮與少數可能正確的情況", ""]
    for rid in summary["minority_ids"]:
        ending = output(f"final.{rid}")
        if ending:
            lines += [
                f"- `{rid}` 的風險：{md(r['description'])}；"
                f"影響 {r['impact']}/5，可能性 `{r['likelihood']}`。"
                for r in ending["critical_risks"]
            ]
            lines += [
                f"- 若 {md(condition)}，`{rid}` 的異議可能成立。"
                for condition in ending["reversal_conditions"]
            ]
    if not summary["minority_ids"]:
        lines += ["未出現不同票種；仍應主動尋找反例，不能以一致投票證明提案正確。"]
    lines += ["", "### 共同假設與潛在相關偏誤", ""]
    for assumption, ids in summary["shared_assumptions"].items():
        lines += [f"- 多於六位共享：{md(assumption)}（{', '.join(ids)}）；尚未因此成為事實。"]
    lines += [
        "- 相同模型、提示、原提案與辯論材料可能產生相關偏誤；獨立上下文並不保證統計獨立。",
        "- 不同票種的假設應逐條比較；系統只列出分歧來源，不推測未明說的語意矛盾。",
        "",
    ]
    for entry in summary["assumption_perspectives"]:
        lines += [
            f"- `{entry['agent_id']}`（{VOTE_LABELS[entry['vote']]}）："
            + "；".join(map(md, entry["assumptions"]))
        ]
    lines += ["", "### 明確爭議的假設與代理指出的矛盾", ""]
    for entry in summary["disputed_assumptions"]:
        lines += [
            f"- `{entry['agent_id']}` 質疑 `{entry['source']}`："
            f"{md(entry['assumption'])}；{md(entry['reason'])}"
        ]
    for entry in summary["contradictions"]:
        lines += [
            f"- `{entry['agent_id']}` 指出（{', '.join(entry['sources'])}）："
            f"{md(entry['description'])}；此為代理判斷，尚未獨立查證。"
        ]
    if not summary["contradictions"]:
        lines += ["沒有代理明確指出直接矛盾；這不代表所有主張相容或正確。"]
    lines += ["", "## 9. 未解不確定性與證據缺口", ""]
    for gap, ids in summary["evidence_gaps"].items():
        lines += [f"- {md(gap)}（{', '.join(ids)}）"]
    for role in snapshot["roles"]["jurors"]:
        ending = output(f"final.{role['id']}")
        if ending:
            lines += [f"- `{role['id']}`：{md(u)}" for u in ending["remaining_uncertainties"]]
            for evidence in ending["important_evidence"]:
                lines += [
                    f"- `{role['id']}` 的關鍵依據（`{evidence['status']}`）："
                    f"{md(evidence['claim'])}；來源：{md(evidence['source'] or '無')}；"
                    f"{md(evidence['verification_note'])}"
                ]
    for number, heading, field in (
        (10, "關鍵風險", "critical_risks"),
        (11, "建議實驗", "experiments"),
        (12, "推翻結論的條件", "reversal_conditions"),
    ):
        lines += ["", f"## {number}. {heading}", ""]
        for role in snapshot["roles"]["jurors"]:
            ending = output(f"final.{role['id']}")
            if ending:
                for item in ending[field]:
                    detail = (
                        (
                            f"{item['description']}（影響 {item['impact']}/5、"
                            f"可能性 {item['likelihood']}）"
                        )
                        if isinstance(item, dict)
                        else item
                    )
                    lines += [f"- `{role['id']}`：{md(detail)}"]
    lines += [
        "",
        "低可能性且高影響的風險應保留；unknown 代表未知，不能當成低風險。",
        "",
        "## 13. 整體建議",
        "",
        recommendation,
        "",
        "上述建議依個別終評與明列的多數規則產生；執行條件及可撤回實驗見第 11、12 節。",
        "",
        "## 14. 執行資訊、品質檢查與限制",
        "",
        f"- 評估 ID：`{state['evaluation_id']}`",
        f"- 建立時間（UTC）：{state['created_at']}",
        f"- 後端：`{snapshot['backend']['name']}`；模式：{label}",
        f"- 設定：並行 {snapshot['settings']['max_concurrency']}；"
        f"每任務最多重試 {snapshot['settings']['max_retries']} 次",
        f"- 階段封存：{', '.join(PHASE_LABELS[p] for p in state['phase_log'])}",
        f"- 完整性：{'完整' if summary['complete'] else '不完整'}",
        f"- 缺少初評：{', '.join(summary['initial']['missing']) or '無'}",
        f"- 缺少終評：{', '.join(final['missing']) or '無'}",
        f"- 缺少辯論：{', '.join(summary['debate_missing']) or '無'}",
        "",
    ]
    for limitation in snapshot["limitations"]:
        lines += [f"- {md(limitation)}"]
    lines += [
        "",
        "### 個別執行識別與評分",
        "",
        "可行性／預期價值／風險／證據品質各為獨立 1–5 序位；風險越高越不利，不計總分。",
        "",
        "| 任務 | 狀態 | 上下文 | 來源／續接 | 模型 | 用量 | 四維評分 |",
        "|---|---|---|---|---|---|---|",
    ]
    for task_id, record in records.items():
        resp = record.get("response", {})
        dimensions = resp.get("output", {}).get("assessment", {})
        scores = (
            "/".join(
                str(dimensions[k])
                for k in ("feasibility", "expected_value", "risk", "evidence_quality")
            )
            if dimensions
            else "—"
        )
        lines += [
            f"| `{task_id}` | {'有效' if record['status'] == 'ok' else '失敗'} | "
            f"{md(resp.get('context_id', '無'))} | "
            f"{md(resp.get('provenance', '無'))} / {md(resp.get('context_mode', '無'))} | "
            f"{md(resp.get('model') or '無法取得')} | "
            f"{resp.get('token_usage') if resp.get('token_usage') is not None else '無法取得'} | "
            f"{scores} |"
        ]
    lines += ["", "### 失敗與重試", ""]
    errors = [(key, e) for key, r in records.items() for e in r["errors"]]
    lines += [f"- `{key}` 第 {e['attempt']} 次：{md(e['error'])}" for key, e in errors]
    if not errors:
        lines += ["沒有記錄到失敗或重試。"]
    lines += ["", "完整原始輸出、任務、角色、設定快照與階段檢查點均保存在同一評估目錄。", ""]
    return "\n".join(lines)
