import unittest

from summary_report import make_change_summary


class SummaryReportTests(unittest.TestCase):
    def test_unchanged_documents_are_explained_simply(self):
        report = make_change_summary([
            {"guide": "1.261", "status": "UNCHANGED"},
            {"guide": "1.262", "status": "UNCHANGED"},
        ])
        self.assertIn("변경된 PDF 문서: 0개", report)
        self.assertIn("이전 기준과 동일합니다", report)

    def test_changed_sections_are_written_in_korean(self):
        report = make_change_summary([
            {
                "guide": "1.261",
                "status": "PDF_CHANGED",
                "diff_path": "pdf_archive/1.261/diff.patch",
                "section_change_items": [
                    {"type": "MODIFIED", "title": "A. INTRODUCTION"},
                    {"type": "ADDED", "title": "C. CONCLUSION"},
                ],
            }
        ])
        self.assertIn("### 1.261", report)
        self.assertIn("수정: A. INTRODUCTION", report)
        self.assertIn("추가: C. CONCLUSION", report)


if __name__ == "__main__":
    unittest.main()
