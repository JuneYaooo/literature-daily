"""render_digest.py 的单元测试（全部离线夹具，不联网）：python3 -m unittest discover tests"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch_pubmed as fp
import render_digest as rd

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "evals" / "fixtures"
OFFLINE = FIX / "offline_v1"
RUN_DATE = "2026-09-19"


def make_candidates(tmp: Path) -> Path:
    """离线跑一次 fetch，得到 5 篇候选（无 seen → 全新）。"""
    out = tmp / "candidates.json"
    code = fp.main([str(FIX / "config_offline_v1.json"), "-o", str(out),
                    "--offline", str(OFFLINE), "--date", RUN_DATE])
    assert code == 0
    return out


class GateTests(unittest.TestCase):
    """防抄袭红线：照抄摘要 ≥25 词 → 退出码 4，且不落盘日报。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.candidates = make_candidates(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_plagiarism_verdict_rejected(self):
        out = self.tmp / "digest.md"
        code = rd.main([str(self.candidates), str(FIX / "verdicts_plagiarism_v1.json"),
                        "-o", str(out)])
        self.assertEqual(code, 4)
        self.assertFalse(out.exists())

    def test_boundary_24_vs_25_words(self):
        data = json.loads(self.candidates.read_text(encoding="utf-8"))
        abstract = next(c["abstract"] for c in data["candidates"]
                        if c["pmid"] == "99010001")
        words = rd.WORD_RE.findall(abstract.lower())
        self.assertIsNone(rd.find_plagiarism(" ".join(words[:24]), abstract))   # 24 词放行
        self.assertIsNotNone(rd.find_plagiarism(" ".join(words[:25]), abstract))  # 25 词拒绝

    def test_chinese_paraphrase_accepted(self):
        text = "该研究用梯度提升树预测重症患者院内死亡，验证了外部有效性。"
        data = json.loads(self.candidates.read_text(encoding="utf-8"))
        abstract = next(c["abstract"] for c in data["candidates"]
                        if c["pmid"] == "99010001")
        self.assertIsNone(rd.find_plagiarism(text, abstract))


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.candidates = make_candidates(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_good_verdicts_render(self):
        out = self.tmp / "digest.md"
        self.assertEqual(rd.main([str(self.candidates), str(FIX / "verdicts_good_v1.json"),
                                  "-o", str(out)]), 0)
        text = out.read_text(encoding="utf-8")
        self.assertIn("# 医学文献日报 · 2026-09-19", text)
        for heading in ("🔴 必读", "🟡 值得扫一眼", "⚪ 可跳过", "## 统计"):
            self.assertIn(heading, text)
        self.assertIn("已看过跳过 0 篇", text)
        # skip 档只列标题 + 命中词，不写导读（按分节标题切分，避开头部统计行）
        self.assertIn("99010003", text)
        self.assertNotIn("**导读**：", text.split("## ⚪ 可跳过")[1])
        # 版权声明行存在
        self.assertIn("不含摘要原文", text)

    def test_render_deterministic(self):
        out_a, out_b = self.tmp / "a.md", self.tmp / "b.md"
        for out in (out_a, out_b):
            rd.main([str(self.candidates), str(FIX / "verdicts_good_v1.json"), "-o", str(out)])
        self.assertEqual(out_a.read_bytes(), out_b.read_bytes())

    def test_missing_one_liner_for_must_read(self):
        verdicts = {"verdicts": [{"pmid": "99010001", "bucket": "must_read",
                                  "one_liner": "", "reason": "r"}]}
        path = self.tmp / "v.json"
        path.write_text(json.dumps(verdicts, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(rd.main([str(self.candidates), str(path)]), 3)

    def test_missing_reason_for_must_read(self):
        verdicts = {"verdicts": [{"pmid": "99010001", "bucket": "must_read",
                                  "one_liner": "一句话"}]}
        path = self.tmp / "v.json"
        path.write_text(json.dumps(verdicts, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(rd.main([str(self.candidates), str(path)]), 3)

    def test_bad_bucket(self):
        verdicts = {"verdicts": [{"pmid": "99010001", "bucket": "super",
                                  "one_liner": "一句话", "reason": "r"}]}
        path = self.tmp / "v.json"
        path.write_text(json.dumps(verdicts, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(rd.main([str(self.candidates), str(path)]), 3)

    def test_unknown_pmid(self):
        verdicts = {"verdicts": [{"pmid": "88888888", "bucket": "skip"}]}
        path = self.tmp / "v.json"
        path.write_text(json.dumps(verdicts, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(rd.main([str(self.candidates), str(path)]), 3)

    def test_incomplete_coverage(self):
        verdicts = {"verdicts": [{"pmid": "99010001", "bucket": "must_read",
                                  "one_liner": "一句话", "reason": "r"}]}
        path = self.tmp / "v.json"
        path.write_text(json.dumps(verdicts, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(rd.main([str(self.candidates), str(path)]), 3)

    def test_missing_input_exit_2(self):
        path = self.tmp / "v.json"
        path.write_text("{}", encoding="utf-8")
        with self.assertRaises(SystemExit) as cm:
            rd.main([str(self.tmp / "nope.json"), str(path)])
        self.assertEqual(cm.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
