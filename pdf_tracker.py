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
        if previous and previous.get("document_url") == guide.document_url:
            results.append({"guide": number, "status": "UNCHANGED", "sha256": previous.get("sha256")})
            continue

        content = download_pdf(guide.document_url)
        digest = hashlib.sha256(content).hexdigest()
        version = safe_name(f"{guide.revision or 'unknown'}_{guide.issue_date or digest[:8]}")
        document_dir = archive_dir / safe_name(number)
        document_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = document_dir / f"{version}_{digest[:12]}.pdf"
        text_path = pdf_path.with_suffix(".txt")
        pdf_path.write_bytes(content)
        text = extract_pdf_text(pdf_path)
        text_path.write_text(text, encoding="utf-8")

        result = {
            "guide": number,
            "status": "NEW_BASELINE" if not previous else "PDF_CHANGED",
            "sha256": digest,
            "pdf_path": str(pdf_path),
            "text_path": str(text_path),
            "characters": len(text),
        }
        if previous and previous.get("text_path"):
            old_text_path = Path(previous["text_path"])
            if old_text_path.exists():
                diff = text_diff(old_text_path.read_text(encoding="utf-8"), text)
                diff_path = document_dir / f"diff_{digest[:12]}.patch"
                diff_path.write_text(diff, encoding="utf-8")
                result["diff_path"] = str(diff_path)
                result["diff_lines"] = len(diff.splitlines())

        new_documents[number] = {
            "document_url": guide.document_url,
            "sha256": digest,
            "pdf_path": str(pdf_path),
            "text_path": str(text_path),
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
        if item.get("sha256"):
            lines += [f"- PDF SHA-256: `{item['sha256']}`"]
        if item.get("diff_path"):
            lines += [f"- 본문 차이 파일: `{item['diff_path']}`", f"- diff 줄 수: {item['diff_lines']}"]
        lines.append("")
    return "\n".join(lines)
