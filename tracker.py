#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

GUIDE_RE = re.compile(r"^1\.\d{1,3}$")
DEFAULT_URL = "https://www.nrc.gov/reading-rm/doc-collections/reg-guides/power-reactors/rg/division-1/division-1-261"


@dataclass
class Guide:
    guide_number: str
    title: str
    revision: str
    issue_date: str
    additional_info: str
    document_url: str
    source_url: str

    def fingerprint(self) -> str:
        stable = "\n".join([
            self.title.strip(), self.revision.strip(), self.issue_date.strip(),
            self.additional_info.strip(), self.document_url.strip()
        ])
        return hashlib.sha256(stable.encode("utf-8")).hexdigest()


def clean_text(node) -> str:
    if node is None:
        return ""
    return " ".join(node.get_text(" ", strip=True).split())


def parse_guides(html: str, source_url: str) -> Dict[str, Guide]:
    soup = BeautifulSoup(html, "html.parser")
    guides: Dict[str, Guide] = {}

    # NRC pages currently expose RG entries as ordinary HTML table rows.
    # This parser intentionally ignores exact CSS classes so minor redesigns are tolerated.
    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 4:
            continue
        number = clean_text(cells[0])
        if not GUIDE_RE.fullmatch(number):
            continue

        title = clean_text(cells[1]) if len(cells) > 1 else ""
        revision = clean_text(cells[2]) if len(cells) > 2 else ""
        issue_date = clean_text(cells[3]) if len(cells) > 3 else ""
        additional = clean_text(cells[4]) if len(cells) > 4 else ""

        # Prefer the Issue Date/Revision link because it usually targets the actual RG/DG document.
        candidate_links = []
        for idx in (3, 2, 1, 4):
            if idx < len(cells):
                for a in cells[idx].find_all("a", href=True):
                    candidate_links.append(urljoin(source_url, a["href"]))
        document_url = candidate_links[0] if candidate_links else ""

        guides[number] = Guide(
            guide_number=number,
            title=title,
            revision=revision,
            issue_date=issue_date,
            additional_info=additional,
            document_url=document_url,
            source_url=source_url,
        )

    if not guides:
        raise ValueError("NRC 표에서 Regulatory Guide 항목을 찾지 못했습니다. 사이트 구조가 바뀌었을 수 있습니다.")
    return guides


def fetch(url: str, timeout: int = 30) -> str:
    headers = {"User-Agent": "NuclearRegUpdateTracker/0.1 (+personal research project)"}
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.text


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"checked_at": None, "guides": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, guides: Dict[str, Guide], checked_at: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "checked_at": checked_at,
        "guides": {
            key: {**asdict(value), "fingerprint": value.fingerprint()}
            for key, value in sorted(guides.items())
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def compare(old: dict, current: Dict[str, Guide]) -> List[dict]:
    old_guides = old.get("guides", {})
    changes: List[dict] = []

    for number, guide in sorted(current.items()):
        new = {**asdict(guide), "fingerprint": guide.fingerprint()}
        if number not in old_guides:
            changes.append({"type": "NEW", "guide": number, "before": None, "after": new, "fields": ["all"]})
            continue

        before = old_guides[number]
        changed_fields = []
        for field in ["title", "revision", "issue_date", "additional_info", "document_url"]:
            if (before.get(field) or "").strip() != (new.get(field) or "").strip():
                changed_fields.append(field)
        if changed_fields:
            changes.append({"type": "MODIFIED", "guide": number, "before": before, "after": new, "fields": changed_fields})

    for number, before in sorted(old_guides.items()):
        if number not in current:
            changes.append({"type": "REMOVED", "guide": number, "before": before, "after": None, "fields": ["all"]})

    return changes


def field_diff(before: str, after: str) -> str:
    if before == after:
        return ""
    lines = list(difflib.ndiff([before or "(없음)"], [after or "(없음)"]))
    return "\n".join(f"    {line}" for line in lines)


def classify_importance(change: dict) -> str:
    if change["type"] in {"NEW", "REMOVED"}:
        return "HIGH"
    fields = set(change.get("fields", []))
    if "revision" in fields or "document_url" in fields:
        return "HIGH"
    if "issue_date" in fields or "title" in fields:
        return "MEDIUM"
    return "LOW"


def make_report(changes: List[dict], old_checked_at: Optional[str], checked_at: str, source_url: str) -> str:
    out = [
        "# NRC Regulatory Guide 업데이트 감지 보고서",
        "",
        f"- 확인 시각(UTC): {checked_at}",
        f"- 이전 확인: {old_checked_at or '최초 실행'}",
        f"- 감시 소스: {source_url}",
        f"- 감지된 변경: {len(changes)}건",
        "",
    ]
    if not changes:
        out += ["## 결과", "", "변경 사항이 감지되지 않았습니다.", ""]
        return "\n".join(out)

    for c in changes:
        out += [f"## {c['guide']} — {c['type']} / 중요도 {classify_importance(c)}", ""]
        if c["type"] == "NEW":
            a = c["after"]
            out += [
                f"- 제목: {a.get('title','')}", f"- Revision: {a.get('revision','')}",
                f"- Issue Date: {a.get('issue_date','')}", f"- 문서: {a.get('document_url','') or '(링크 없음)'}", ""
            ]
        elif c["type"] == "REMOVED":
            b = c["before"]
            out += [f"- 기존 제목: {b.get('title','')}", "- 기존 목록에서 사라졌습니다. 폐기/이동/페이지 구조 변경 여부를 확인해야 합니다.", ""]
        else:
            b, a = c["before"], c["after"]
            out += [f"- 변경 필드: {', '.join(c['fields'])}", ""]
            for field in c["fields"]:
                out += [f"### {field}", "", "```diff", field_diff(b.get(field, ""), a.get(field, "")), "```", ""]
            out += [
                "### 1차 해석",
                "",
                "- Revision 또는 문서 링크 변경이면 실제 규제 가이드 본문 변경 가능성이 높으므로 원문 비교를 우선 수행합니다.",
                "- 제목/발행일/추가정보만 바뀐 경우 메타데이터 정정일 수도 있으므로 원문 변경 여부를 별도 확인합니다.",
                "",
            ]
    return "\n".join(out)


def run(url: str, state_path: Path, reports_dir: Path, html_file: Optional[Path] = None, bootstrap: bool = False) -> int:
    html = html_file.read_text(encoding="utf-8") if html_file else fetch(url)
    current = parse_guides(html, url)
    old = load_state(state_path)
    checked_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    # First run establishes a clean baseline unless explicitly asked to report all current entries.
    first_run = not old.get("guides")
    changes = [] if (first_run and bootstrap) else compare(old, current)

    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = reports_dir / f"nrc_update_{timestamp}.md"
    report_path.write_text(make_report(changes, old.get("checked_at"), checked_at, url), encoding="utf-8")
    save_state(state_path, current, checked_at)

    print(f"수집: {len(current)}개")
    print(f"변경: {len(changes)}건")
    print(f"상태: {state_path}")
    print(f"보고서: {report_path}")
    return 2 if changes else 0


def main() -> int:
    p = argparse.ArgumentParser(description="NRC Regulatory Guide update tracker")
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument("--state", default="data/state.json")
    p.add_argument("--reports", default="reports")
    p.add_argument("--html-file", help="테스트/오프라인용 HTML 파일")
    p.add_argument("--bootstrap", action="store_true", help="최초 실행 시 현재 상태를 기준선으로만 저장")
    args = p.parse_args()

    try:
        return run(args.url, Path(args.state), Path(args.reports), Path(args.html_file) if args.html_file else None, args.bootstrap)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
