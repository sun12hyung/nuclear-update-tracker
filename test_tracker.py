import tempfile
import unittest
from pathlib import Path

import tracker

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

if __name__ == "__main__":
    unittest.main()
