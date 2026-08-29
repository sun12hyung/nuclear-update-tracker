import tempfile
import unittest
import hashlib
import json
from pathlib import Path
from unittest.mock import Mock, patch

import tracker
import pdf_tracker

ROOT = Path(__file__).parent
URL = "https://www.nrc.gov/example"

class TrackerTests(unittest.TestCase):
    def test_parse(self):
        html = (ROOT / "sample_v1.html").read_text()
        guides = tracker.parse_guides(html, URL)
        self.assertEqual(set(guides), {"1.261", "1.262"})
        self.assertEqual(guides["1.261"].revision, "0")
        self.assertTrue(guides["1.261"].document_url.endswith("ML26100A001.pdf"))

    def test_change_detection(self):
        v1 = tracker.parse_guides((ROOT / "sample_v1.html").read_text(), URL)
        v2 = tracker.parse_guides((ROOT / "sample_v2.html").read_text(), URL)
        with tempfile.TemporaryDirectory() as d:
            state = Path(d) / "state.json"
            tracker.save_state(state, v1, "2026-08-18T00:00:00+00:00")
            old = tracker.load_state(state)
            changes = tracker.compare(old, v2)
            by_guide = {x["guide"]: x for x in changes}
            self.assertEqual(by_guide["1.261"]["type"], "MODIFIED")
            self.assertIn("revision", by_guide["1.261"]["fields"])
            self.assertEqual(by_guide["1.263"]["type"], "NEW")

    @patch("tracker.requests.Session.get")
    def test_fetch_explains_nrc_403(self, mock_get):
        response = Mock(status_code=403)
        mock_get.return_value = response

        with self.assertRaisesRegex(RuntimeError, "HTTP 403/Akamai"):
            tracker.fetch(URL)

    def test_pdf_text_diff(self):
        diff = pdf_tracker.text_diff("A\nold requirement", "A\nnew requirement")
        self.assertIn("-old requirement", diff)
        self.assertIn("+new requirement", diff)

    def test_safe_pdf_filename(self):
        self.assertEqual(pdf_tracker.safe_name("DG / 08/2026"), "DG_08_2026")

    def test_split_and_compare_sections(self):
        before = pdf_tracker.split_sections("A. INTRODUCTION\nOld text\nB. DISCUSSION\nSame")
        after = pdf_tracker.split_sections("A. INTRODUCTION\nNew text\nB. DISCUSSION\nSame\nC. CONCLUSION\nAdded")
        changes = pdf_tracker.compare_sections(before, after)
        self.assertIn({"type": "MODIFIED", "title": "A. INTRODUCTION"}, changes)
        self.assertIn({"type": "ADDED", "title": "C. CONCLUSION"}, changes)

    @patch("pdf_tracker.extract_pdf_text", return_value="A. INTRODUCTION\nNew text")
    @patch("pdf_tracker.download_pdf", return_value=b"%PDF-new-content")
    def test_same_url_pdf_replacement_is_detected(self, _mock_download, _mock_extract):
        guide = tracker.Guide(
            guide_number="1.261",
            title="Example",
            revision="0",
            issue_date="08/2026",
            additional_info="",
            document_url="https://www.nrc.gov/example.pdf",
            source_url=URL,
        )
        with tempfile.TemporaryDirectory() as d:
            archive = Path(d)
            (archive / "manifest.json").write_text(json.dumps({
                "documents": {
                    "1.261": {
                        "document_url": guide.document_url,
                        "sha256": hashlib.sha256(b"%PDF-old-content").hexdigest(),
                    }
                }
            }))
            results = pdf_tracker.process_documents({"1.261": guide}, archive)
        self.assertEqual(results[0]["status"], "PDF_CHANGED")

if __name__ == "__main__":
    unittest.main()
