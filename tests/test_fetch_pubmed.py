"""fetch_pubmed.py 的单元测试（全部离线夹具，不联网）：python3 -m unittest discover tests"""

import json
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
from hashlib import sha256
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch_pubmed as fp

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "evals" / "fixtures"
OFFLINE = FIX / "offline_v1"
RUN_DATE = "2026-09-19"


def parse_fixture() -> dict[str, dict]:
    root = ET.fromstring((OFFLINE / "efetch_v1.xml").read_bytes())
    articles: dict[str, dict] = {}
    for kind, parser in (("PubmedArticle", fp.parse_article),
                         ("PubmedBookArticle", fp.parse_book_article)):
        for node in root.findall(kind):
            pmid_node = node.find("MedlineCitation/PMID")
            if pmid_node is None:
                pmid_node = node.find("BookDocument/PMID")
            pmid = (pmid_node.text or "").strip()
            articles[pmid] = parser(node, pmid)
    return articles


class ParseXmlTests(unittest.TestCase):
    """efetch XML 解析：作者后缀、集体作者、无 DOI、无摘要、MedlineDate、标题标记。"""

    @classmethod
    def setUpClass(cls):
        cls.articles = parse_fixture()

    def test_author_suffix_jr(self):
        self.assertIn("John Smith, Jr", self.articles["99010001"]["authors"])

    def test_title_markup_stripped(self):
        title = self.articles["99010002"]["title"]
        self.assertNotIn("<i>", title)
        self.assertIn("procalcitonin", title)

    def test_no_doi(self):
        self.assertIsNone(self.articles["99010002"]["doi"])

    def test_no_abstract(self):
        self.assertIsNone(self.articles["99010003"]["abstract"])
        self.assertEqual(self.articles["99010003"]["pubdate"], "2026 Sep-Oct")

    def test_collective_author(self):
        self.assertEqual(self.articles["99010004"]["authors"],
                         ["Pediatric Sepsis Consortium"])

    def test_structured_abstract_labels(self):
        abstract = self.articles["99010004"]["abstract"]
        for label in ("BACKGROUND:", "METHODS:", "RESULTS:", "CONCLUSIONS:"):
            self.assertIn(label, abstract)

    def test_year_only_pubdate_and_url(self):
        self.assertEqual(self.articles["99010004"]["pubdate"], "2026")
        self.assertEqual(self.articles["99010001"]["pubmed_url"],
                         "https://pubmed.ncbi.nlm.nih.gov/99010001/")

    def test_book_article(self):
        """回归自真实运行：StatPearls 类图书章节以 PubmedBookArticle 返回。"""
        article = self.articles["99010006"]
        self.assertEqual(article["pubtypes"], ["Book"])
        self.assertEqual(article["journal"], "Synthetic Clinical References")
        self.assertIn("Laboratory Evaluation of Sepsis", article["title"])
        self.assertIn("textbook chapter", article["abstract"])


class OfflineRunTests(unittest.TestCase):
    """--offline 全流程：去重、matched_keywords、seen 原子写回。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.seen = self.tmp / "seen.json"
        shutil.copy(FIX / "seen_partial_v1.json", self.seen)
        self.out = self.tmp / "candidates.json"

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_offline(self):
        return fp.main([str(FIX / "config_offline_v1.json"), "--seen", str(self.seen),
                        "-o", str(self.out), "--offline", str(OFFLINE),
                        "--date", RUN_DATE])

    def test_partial_dedup_and_atomic_seen(self):
        self.assertEqual(self.run_offline(), 0)
        data = json.loads(self.out.read_text(encoding="utf-8"))
        self.assertTrue(data["offline"])
        self.assertEqual([c["pmid"] for c in data["candidates"]],
                         ["99010001", "99010003", "99010006", "99010004", "99010005"])
        self.assertEqual(data["stats"], {"esearch_hits": 158, "union": 6,
                                         "already_seen": 1, "new": 5, "requests": 4})
        cross = {c["pmid"]: c["matched_keywords"] for c in data["candidates"]}
        self.assertEqual(cross["99010004"], ["machine learning sepsis", "early warning score"])
        seen = json.loads(self.seen.read_text(encoding="utf-8"))
        self.assertEqual(seen["pmids"], ["99010001", "99010002", "99010003",
                                         "99010004", "99010005", "99010006"])
        self.assertFalse(Path(str(self.seen) + ".tmp").exists())  # 原子写回无残留

    def test_second_run_fully_deduped(self):
        self.run_offline()
        before = self.seen.read_text(encoding="utf-8")
        out2 = self.tmp / "candidates2.json"
        code = fp.main([str(FIX / "config_offline_v1.json"), "--seen", str(self.seen),
                        "-o", str(out2), "--offline", str(OFFLINE), "--date", RUN_DATE])
        self.assertEqual(code, 0)
        data = json.loads(out2.read_text(encoding="utf-8"))
        self.assertEqual(data["candidates"], [])
        self.assertEqual(data["stats"]["new"], 0)
        self.assertEqual(data["stats"]["requests"], 3)  # 全部已见 → 不再调 efetch
        self.assertEqual(self.seen.read_text(encoding="utf-8"), before)

    def test_determinism_sha256(self):
        seen_a, seen_b = self.tmp / "a.json", self.tmp / "b.json"
        for source in (seen_a, seen_b):
            shutil.copy(FIX / "seen_partial_v1.json", source)
        out_a, out_b = self.tmp / "ca.json", self.tmp / "cb.json"
        for seen, out in ((seen_a, out_a), (seen_b, out_b)):
            fp.main([str(FIX / "config_offline_v1.json"), "--seen", str(seen),
                     "-o", str(out), "--offline", str(OFFLINE), "--date", RUN_DATE])
        digest = lambda p: sha256(p.read_bytes()).hexdigest()
        self.assertEqual(digest(out_a), digest(out_b))
        self.assertEqual(digest(seen_a), digest(seen_b))


class ConfigErrorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_missing_config_exit_2(self):
        with self.assertRaises(SystemExit) as cm:
            fp.main([str(self.tmp / "nope.json")])
        self.assertEqual(cm.exception.code, 2)

    def test_bad_json_exit_3(self):
        path = self.tmp / "config.json"
        path.write_text("{not json", encoding="utf-8")
        self.assertEqual(fp.main([str(path)]), 3)

    def test_missing_keywords_exit_3(self):
        path = self.tmp / "config.json"
        path.write_text(json.dumps({"retmax": 5}), encoding="utf-8")
        self.assertEqual(fp.main([str(path)]), 3)

    def test_bad_seen_exit_3(self):
        seen = self.tmp / "seen.json"
        seen.write_text("nope", encoding="utf-8")
        self.assertEqual(fp.main([str(FIX / "config_offline_v1.json"),
                                  "--seen", str(seen), "--offline", str(OFFLINE),
                                  "--date", RUN_DATE]), 3)

    def test_missing_offline_fixture_exit_3(self):
        self.assertEqual(fp.main([str(FIX / "config_offline_v1.json"),
                                  "--offline", str(self.tmp / "empty"),
                                  "--date", RUN_DATE]), 3)


if __name__ == "__main__":
    unittest.main()
