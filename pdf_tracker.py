from __future__ import annotations

import difflib
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

import requests
from pypdf import PdfReader

from tracker import Guide

SECTION_RE = re.compile(
    r"^(?:(?:[A-Z]|\d+(?:\.\d+)*)[.)]?\s+)?[A-Z][A-Z0-9 ,/&()'\-]{4,}$"
)


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")


def download_pdf(url: str, timeout: int = 60) -> bytes:
    response = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; NuclearRegUpdateTracker/0.3)"},
        timeout=timeout,
    )
    if response.status_code == 403:
        raise RuntimeError(f"PDF 다운로드가 NRC에서 차단되었습니다: {url}")
    response.raise_for_status()
    content = response.content
    if not content.startswith(b"%PDF"):
        raise ValueError(f"PDF가 아닌 응답을 받았습니다: {url}")
    return content


def extract_pdf_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append(f"\n--- PAGE {index} ---\n{text.strip()}")
    return "\n".join(pages).strip()


def text_diff(before: str, after: str, context: int = 3) -> str:
    return "\n".join(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile="previous",
            tofile="current",
            n=context,
            lineterm="",
        )
    )


def split_sections(text: str) -> list[dict]:
    sections = []
    current = {"title": "FRONT MATTER", "lines": []}
    for raw_line in text.splitlines():
        line = " ".join(raw_line.split())
        is_page_marker = line.startswith("--- PAGE ")
        is_heading = bool(SECTION_RE.fullmatch(line)) and len(line) <= 120
        if not is_page_marker and is_heading:
            if current["lines"]:
                body = "\n".join(current["lines"]).strip()
                sections.append({
                    "title": current["title"],
                    "text": body,
                    "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                })
            current = {"title": line, "lines": []}
        else:
            current["lines"].append(raw_line)
    if current["lines"]:
        body = "\n".join(current["lines"]).strip()
        sections.append({
            "title": current["title"],
            "text": body,
            "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        })
    return [section for section in sections if section["text"]]


def compare_sections(before: list[dict], after: list[dict]) -> list[dict]:
    old = {section["title"]: section for section in before}
    new = {section["title"]: section for section in after}
    changes = []
    for title in new.keys() - old.keys():
        changes.append({"type": "ADDED", "title": title})
    for title in old.keys() - new.keys():
        changes.append({"type": "REMOVED", "title": title})
    for title in old.keys() & new.keys():
        if old[title]["sha256"] != new[title]["sha256"]:
            changes.append({"type": "MODIFIED", "title": title})
    return sorted(changes, key=lambda item: (item["title"], item["type"]))


def load_manifest(path: Path) -> dict:
    if not path.exists():
        return {"documents": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def process_documents(guides: Dict[str, Guide], archive_dir: Path) -> list[dict]:
    archive_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = archive_dir / "manifest.json"
    manifest = load_manifest(manifest_path)
    old_documents = manifest.get("documents", {})
    new_documents = dict(old_documents)
    results = []

    for number, guide in sorted(guides.items()):
        if not guide.document_url.lower().endswith(".pdf"):
            results.append({"guide": number, "status": "SKIPPED", "reason": "PDF 링크 없음"})
            continue

        previous = old_documents.get(number)
        content = download_pdf(guide.document_url)
        digest = hashlib.sha256(content).hexdigest()
        if previous and previous.get("sha256") == digest:
            results.append({"guide": number, "status": "UNCHANGED", "sha256": digest})
            continue

        version = safe_name(f"{guide.revision or 'unknown'}_{guide.issue_date or digest[:8]}")
        document_dir = archive_dir / safe_name(number)
        document_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = document_dir / f"{version}_{digest[:12]}.pdf"
        text_path = pdf_path.with_suffix(".txt")
        pdf_path.write_bytes(content)
        text = extract_pdf_text(pdf_path)
        text_path.write_text(text, encoding="utf-8")
        sections = split_sections(text)
        sections_path = pdf_path.with_suffix(".sections.json")
        sections_path.write_text(
            json.dumps(sections, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        result = {
            "guide": number,
            "status": "NEW_BASELINE" if not previous else "PDF_CHANGED",
            "sha256": digest,
            "pdf_path": str(pdf_path),
            "text_path": str(text_path),
            "sections_path": str(sections_path),
            "characters": len(text),
            "sections": len(sections),
        }
        if previous and previous.get("text_path"):
            old_text_path = Path(previous["text_path"])
            if old_text_path.exists():
                diff = text_diff(old_text_path.read_text(encoding="utf-8"), text)
                diff_path = document_dir / f"diff_{digest[:12]}.patch"
                diff_path.write_text(diff, encoding="utf-8")
                result["diff_path"] = str(diff_path)
                result["diff_lines"] = len(diff.splitlines())
        if previous and previous.get("sections_path"):
            old_sections_path = Path(previous["sections_path"])
            if old_sections_path.exists():
                section_changes = compare_sections(
                    json.loads(old_sections_path.read_text(encoding="utf-8")), sections
                )
                section_diff_path = document_dir / f"section_diff_{digest[:12]}.json"
                section_diff_path.write_text(
                    json.dumps(section_changes, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                result["section_diff_path"] = str(section_diff_path)
                result["section_changes"] = len(section_changes)
                result["section_change_items"] = section_changes

        new_documents[number] = {
            "document_url": guide.document_url,
            "sha256": digest,
            "pdf_path": str(pdf_path),
            "text_path": str(text_path),
            "sections_path": str(sections_path),
            "checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
        results.append(result)

    manifest_path.write_text(
        json.dumps({"documents": new_documents}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return results


def make_pdf_report(results: list[dict]) -> str:
    lines = ["# NRC PDF 본문 수집·비교 보고서", ""]
    for item in results:
        lines += [f"## {item['guide']} — {item['status']}", ""]
        if item.get("reason"):
            lines += [f"- 사유: {item['reason']}"]
        if item.get("characters") is not None:
            lines += [f"- 추출된 글자 수: {item['characters']:,}"]
        if item.get("sections") is not None:
            lines += [f"- 인식된 장·절 수: {item['sections']}"]
        if item.get("sha256"):
            lines += [f"- PDF SHA-256: `{item['sha256']}`"]
        if item.get("diff_path"):
            lines += [f"- 본문 차이 파일: `{item['diff_path']}`", f"- diff 줄 수: {item['diff_lines']}"]
        if item.get("section_diff_path"):
            lines += [
                f"- 절별 비교 파일: `{item['section_diff_path']}`",
                f"- 변경된 장·절 수: {item['section_changes']}",
            ]
        lines.append("")
    return "\n".join(lines)
