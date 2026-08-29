from __future__ import annotations


SECTION_TYPE_KO = {
    "ADDED": "추가",
    "REMOVED": "삭제",
    "MODIFIED": "수정",
}


def make_change_summary(results: list[dict]) -> str:
    changed = [item for item in results if item.get("status") == "PDF_CHANGED"]
    baselines = [item for item in results if item.get("status") == "NEW_BASELINE"]
    lines = [
        "# NRC 변경 핵심 요약",
        "",
        f"- 확인한 PDF 문서: {len(results)}개",
        f"- 변경된 PDF 문서: {len(changed)}개",
        f"- 새 기준으로 등록된 문서: {len(baselines)}개",
        "",
    ]

    if not changed:
        lines += [
            "## 결과",
            "",
            "변경된 NRC PDF가 없습니다. 이전 기준과 동일합니다.",
            "",
        ]
        return "\n".join(lines)

    lines += ["## 검토가 필요한 문서", ""]
    for item in changed:
        section_changes = item.get("section_change_items", [])
        lines += [
            f"### {item['guide']}",
            "",
            f"- 변경된 장·절: {len(section_changes)}개",
        ]
        if section_changes:
            for change in section_changes:
                label = SECTION_TYPE_KO.get(change.get("type"), change.get("type", "변경"))
                lines.append(f"- {label}: {change.get('title', '(제목 없음)')}")
        else:
            lines.append("- PDF 본문은 바뀌었지만 장·절 제목 변화는 감지되지 않았습니다.")
        if item.get("diff_path"):
            lines.append(f"- 상세 본문 비교: `{item['diff_path']}`")
        lines.append("")
    return "\n".join(lines)
