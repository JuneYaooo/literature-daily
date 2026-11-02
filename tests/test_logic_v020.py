"""v0.2.0 逻辑改进的回归测试（全部离线）：python3 -m unittest discover tests

覆盖：先去重再截取（seen 饿死缺陷）、顺延不写 seen、自动补窗、检索式告警、
撤稿/勘误/预印本标记、429/网络瞬断重试、两阶段 seen 提交、渲染徽标与提示。
"""

import io
import json
import shutil
import tempfile
import unittest
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch_pubmed as fp
import render_digest as rd

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "evals" / "fixtures"
OFFLINE = FIX / "offline_v1"
RUN_DATE = "2026-09-19"


def kw(keyword, pmids, count=None):
    return {"keyword": keyword, "count": count or len(pmids), "pmids": pmids,
            "translation": "", "warnings": []}


class SelectNewTests(unittest.TestCase):
    def test_seen_no_longer_starves_quota(self):
        """v0.1.x：retmax=3 截断在去重之前，前 3 篇已读 → 永远 0 新增。现在跳过已读继续取。"""
        results = [kw("a", ["10", "9", "8", "7", "6", "5"])]
        taken, deferred, per_kw = fp.select_new(results, {"10", "9", "8"}, 3)
        self.assertEqual(taken, ["7", "6", "5"])
        self.assertEqual(deferred, [])
        self.assertEqual(per_kw["a"], {"new": 3, "taken": 3})

    def test_overflow_deferred_not_dropped(self):
        results = [kw("a", ["6", "5", "4", "3", "2"])]
        taken, deferred, _ = fp.select_new(results, set(), 2)
        self.assertEqual(taken, ["6", "5"])
        self.assertEqual(deferred, ["4", "3", "2"])

    def test_cross_keyword_overlap_not_double_counted(self):
        results = [kw("a", ["5", "4"]), kw("b", ["5", "3", "2"])]
        taken, deferred, per_kw = fp.select_new(results, set(), 2)
        self.assertEqual(taken, ["5", "4", "3", "2"])  # b 跳过已被 a 收录的 5
        self.assertEqual(deferred, [])
        self.assertEqual(per_kw["b"], {"new": 3, "taken": 2})

    def test_deferred_from_one_keyword_rescued_by_another(self):
        results = [kw("a", ["5", "4", "3"]), kw("b", ["3"])]
        taken, deferred, _ = fp.select_new(results, set(), 2)
        self.assertEqual(taken, ["5", "4", "3"])
        self.assertEqual(deferred, [])


class WindowTests(unittest.TestCase):
    def test_no_history_uses_reldate(self):
        self.assertEqual(fp.effective_reldate(7, "2026-11-02", None), (7, None))

    def test_daily_run_keeps_reldate(self):
        self.assertEqual(fp.effective_reldate(7, "2026-11-02", "2026-11-01"), (7, 1))

    def test_long_gap_catches_up_with_overlap(self):
        self.assertEqual(fp.effective_reldate(7, "2026-11-02", "2026-10-20"), (14, 13))

    def test_catchup_capped(self):
        self.assertEqual(fp.effective_reldate(7, "2026-11-02", "2025-01-01")[0], fp.MAX_CATCHUP)

    def test_catchup_disabled(self):
        self.assertEqual(fp.effective_reldate(7, "2026-11-02", "2026-10-20", False), (7, 13))

    def test_bad_date_falls_back(self):
        self.assertEqual(fp.effective_reldate(7, "2026-11-02", "yesterday"), (7, None))


class QueryWarningTests(unittest.TestCase):
    def test_typo_phrase_not_found(self):
        """2026-11-02 真实响应结构：'sepsis biomarkr' 的 biomarkr 被静默丢弃。"""
        data = {"errorlist": {"phrasesnotfound": ["biomarkr"], "fieldsnotfound": []}}
        warnings = fp.query_warnings(data)
        self.assertEqual(len(warnings), 1)
        self.assertIn("biomarkr", warnings[0])

    def test_quoted_phrase_split(self):
        data = {"warninglist": {"phrasesignored": [],
                                "quotedphrasesnotfound": ['"sepsis zzqqxx biomarker"'],
                                "outputmessages": []}}
        self.assertIn("拆词", fp.query_warnings(data)[0])

    def test_and_not_operator_dropped(self):
        """2026-11-02 实测：'sepsis AND NOT preprint[pt]' 返回 outputmessages=['NOT', ...]。"""
        data = {"warninglist": {"outputmessages": ["NOT", "No items found."]}}
        warnings = fp.query_warnings(data)
        self.assertEqual(len(warnings), 1)
        self.assertIn("A NOT B", warnings[0])

    def test_no_items_found_is_not_warning(self):
        data = {"warninglist": {"outputmessages": ["No items found."]}}
        self.assertEqual(fp.query_warnings(data), [])

    def test_esearch_error_field_exit_3(self):
        client = mock.Mock()
        client.get.return_value = json.dumps(
            {"esearchresult": {"ERROR": "Invalid query"}}).encode()
        with self.assertRaises(fp.InputError):
            fp.esearch_keyword(client, "x[zz", 100, 7, "f.json")

    def test_esearch_no_sort_param_and_id_limit(self):
        client = mock.Mock()
        client.get.return_value = json.dumps({"esearchresult": {
            "count": "2", "idlist": ["2", "1"], "querytranslation": "x[All Fields]"}}).encode()
        result = fp.esearch_keyword(client, "x", 500, 7, "f.json")
        params = client.get.call_args[0][1]
        self.assertNotIn("sort", params)  # 默认 Most Recent（edat）
        self.assertEqual(params["retmax"], "500")
        self.assertEqual(result["translation"], "x[All Fields]")


ARTICLE_XML = """<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>1</PMID>
<Article><Journal><Title>J</Title><JournalIssue><PubDate><Year>2026</Year></PubDate></JournalIssue></Journal>
<ArticleTitle>T</ArticleTitle><PublicationTypeList>
<PublicationType>Journal Article</PublicationType>{extra}</PublicationTypeList></Article>
{refs}</MedlineCitation><PubmedData/></PubmedArticle></PubmedArticleSet>"""


def parse_one(extra="", refs=""):
    root = ET.fromstring(ARTICLE_XML.format(extra=extra, refs=refs))
    return fp.parse_article(root.find("PubmedArticle"), "1")


class FlagTests(unittest.TestCase):
    def test_plain_article_no_flags(self):
        self.assertEqual(parse_one()["flags"], [])

    def test_retracted_via_comments_corrections(self):
        refs = ('<CommentsCorrectionsList><CommentsCorrections RefType="RetractionIn">'
                '<RefSource>x</RefSource></CommentsCorrections></CommentsCorrectionsList>')
        self.assertEqual(parse_one(refs=refs)["flags"], ["retracted"])

    def test_retraction_notice_current_and_legacy_names(self):
        for name in ("Retraction Notice", "Retraction of Publication", "Published Erratum"):
            flags = parse_one(extra=f"<PublicationType>{name}</PublicationType>")["flags"]
            self.assertEqual(flags, ["notice"], name)

    def test_preprint_and_opinion(self):
        self.assertEqual(fp.classify_flags(["Preprint", "Editorial"]), ["preprint", "opinion"])

    def test_book_flag(self):
        root = ET.fromstring((OFFLINE / "efetch_v1.xml").read_bytes())
        node = root.find("PubmedBookArticle")
        self.assertEqual(fp.parse_book_article(node, "99010006")["flags"], ["book"])


class RetryTests(unittest.TestCase):
    def setUp(self):
        self.client = fp.HttpClient(0.4, None, tool="t", email="")
        patcher = mock.patch.object(fp.time, "sleep")
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)

    def ok(self):
        resp = mock.MagicMock()
        resp.__enter__.return_value.read.return_value = b"ok"
        return resp

    def http_error(self, code, headers=None):
        return urllib.error.HTTPError("u", code, "x", headers or {}, io.BytesIO(b""))

    def test_429_then_success(self):
        with mock.patch.object(fp.urllib.request, "urlopen",
                               side_effect=[self.http_error(429, {"Retry-After": "7"}),
                                            self.ok()]):
            self.assertEqual(self.client.get("esearch", {}), b"ok")
        self.assertIn(mock.call(7.0), self.sleep.call_args_list)  # 尊重 Retry-After
        self.assertEqual(self.client.requests, 2)

    def test_transient_network_error_then_success(self):
        """2026-11-02 改前基线真实遇到 SSL UNEXPECTED_EOF 直接 exit 4。"""
        with mock.patch.object(fp.urllib.request, "urlopen",
                               side_effect=[urllib.error.URLError("ssl eof"), self.ok()]):
            self.assertEqual(self.client.get("esearch", {}), b"ok")

    def test_persistent_failure_exit_4(self):
        with mock.patch.object(fp.urllib.request, "urlopen",
                               side_effect=urllib.error.URLError("down")):
            with self.assertRaises(SystemExit) as cm:
                self.client.get("esearch", {})
        self.assertEqual(cm.exception.code, 4)
        self.assertEqual(self.client.requests, 3)

    def test_400_not_retried(self):
        with mock.patch.object(fp.urllib.request, "urlopen",
                               side_effect=[self.http_error(400)]) as urlopen:
            with self.assertRaises(SystemExit):
                self.client.get("esearch", {})
        self.assertEqual(urlopen.call_count, 1)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.seen = self.tmp / "seen.json"
        shutil.copy(FIX / "seen_partial_v1.json", self.seen)

    def config(self, **overrides):
        data = json.loads((FIX / "config_offline_v1.json").read_text(encoding="utf-8"))
        data.update(overrides)
        path = self.tmp / "config.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def fetch(self, config, *extra, out="c.json", date=RUN_DATE):
        out_path = self.tmp / out
        code = fp.main([str(config), "--seen", str(self.seen), "-o", str(out_path),
                        "--offline", str(OFFLINE), "--date", date, *extra])
        self.assertEqual(code, 0)
        return json.loads(out_path.read_text(encoding="utf-8"))

    def test_deferred_items_return_next_run(self):
        cfg = self.config(retmax=1)
        first = self.fetch(cfg)
        self.assertEqual(first["stats"]["new"], 3)          # 每词 1 篇
        self.assertEqual(first["stats"]["deferred"], 2)
        self.assertEqual(sorted(first["deferred_pmids"]), ["99010003", "99010006"])
        seen = json.loads(self.seen.read_text(encoding="utf-8"))["pmids"]
        self.assertNotIn("99010003", seen)                 # 顺延的不标已读
        second = self.fetch(cfg, out="c2.json")
        self.assertEqual([c["pmid"] for c in second["candidates"]], ["99010003"])
        third = self.fetch(cfg, out="c3.json")
        self.assertEqual([c["pmid"] for c in third["candidates"]], ["99010006"])

    def test_no_commit_then_render_commit(self):
        before = self.seen.read_text(encoding="utf-8")
        data = self.fetch(self.config(), "--no-commit")
        self.assertEqual(self.seen.read_text(encoding="utf-8"), before)
        verdicts = {"verdicts": [{"pmid": c["pmid"], "bucket": "skip"}
                                 for c in data["candidates"]]}
        vpath = self.tmp / "v.json"
        vpath.write_text(json.dumps(verdicts), encoding="utf-8")
        code = rd.main([str(self.tmp / "c.json"), str(vpath), "-o", str(self.tmp / "d.md"),
                        "--commit-seen", str(self.seen)])
        self.assertEqual(code, 0)
        seen = json.loads(self.seen.read_text(encoding="utf-8"))
        self.assertEqual(len(seen["pmids"]), 6)
        self.assertEqual(seen["updated"], RUN_DATE)
        again = self.fetch(self.config(), "--no-commit", out="c2.json")
        self.assertEqual(again["candidates"], [])

    def test_render_failure_does_not_commit(self):
        self.fetch(self.config(), "--no-commit")
        before = self.seen.read_text(encoding="utf-8")
        vpath = self.tmp / "v.json"
        vpath.write_text(json.dumps({"verdicts": []}), encoding="utf-8")
        code = rd.main([str(self.tmp / "c.json"), str(vpath), "-o", str(self.tmp / "d.md"),
                        "--commit-seen", str(self.seen)])
        self.assertEqual(code, 3)
        self.assertEqual(self.seen.read_text(encoding="utf-8"), before)

    def test_catchup_window_recorded(self):
        data = self.fetch(self.config(), date="2026-10-01")  # seen.updated=2026-09-18
        self.assertEqual(data["window"]["reldate"], 14)
        self.assertEqual(data["window"]["base_reldate"], 7)

    def test_render_shows_badges_deferred_and_warnings(self):
        data = self.fetch(self.config(retmax=1), "--no-commit")
        data["keywords"][0]["warnings"] = ["词“biomarkr”在 PubMed 中不存在，已被忽略（检查拼写）"]
        data["keywords"][0]["query_translation"] = "sepsis[All Fields]"
        path = self.tmp / "c.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        verdicts = {"verdicts": [{"pmid": c["pmid"], "bucket": "skip"}
                                 for c in data["candidates"]]}
        vpath = self.tmp / "v.json"
        vpath.write_text(json.dumps(verdicts), encoding="utf-8")
        out = self.tmp / "d.md"
        self.assertEqual(rd.main([str(path), str(vpath), "-o", str(out)]), 0)
        text = out.read_text(encoding="utf-8")
        self.assertIn("另有 2 篇未读新文献超出每词上限", text)
        self.assertIn("biomarkr", text)
        self.assertIn("`sepsis[All Fields]`", text)
        self.assertIn("| 关键词 | 近 7 天命中 | 其中未读 | 本期收录 |", text)

    def test_retracted_cannot_be_must_read(self):
        data = self.fetch(self.config(), "--no-commit")
        data["candidates"][0]["flags"] = ["retracted"]
        path = self.tmp / "c.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        verdicts = {"verdicts": [{"pmid": c["pmid"], "bucket": "skip"}
                                 for c in data["candidates"]]}
        verdicts["verdicts"][0] = {"pmid": data["candidates"][0]["pmid"], "bucket": "must_read",
                                   "one_liner": "一句话", "reason": "理由"}
        vpath = self.tmp / "v.json"
        vpath.write_text(json.dumps(verdicts, ensure_ascii=False), encoding="utf-8")
        out = self.tmp / "d.md"
        self.assertEqual(rd.main([str(path), str(vpath), "-o", str(out)]), 3)
        self.assertFalse(out.exists())
        verdicts["verdicts"][0]["bucket"] = "worth_a_look"
        vpath.write_text(json.dumps(verdicts, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(rd.main([str(path), str(vpath), "-o", str(out)]), 0)
        self.assertIn("⛔ 已撤稿", out.read_text(encoding="utf-8"))

    def test_legacy_candidates_still_render(self):
        """v0.1.x 产物（无 flags/new 字段）仍可渲染，图书条目按 pubtypes 推断徽标。"""
        row = {"pmid": "1", "title": "T", "pubtypes": ["Book"], "abstract": None}
        self.assertEqual(rd.row_flags(row), ["book"])
        legacy = {"run_date": RUN_DATE, "keywords": [{"keyword": "k", "count": 3, "returned": 1}],
                  "stats": {"esearch_hits": 3, "union": 1, "already_seen": 0, "new": 1},
                  "window": {"reldate": 7}, "candidates": [row]}
        markdown = rd.render(legacy, [{"entry": {"pmid": "1", "bucket": "skip"}, "row": row}])
        self.assertIn("| 关键词 | 近 7 天命中 | 取回 |", markdown)
        self.assertIn("📚 图书章节", markdown)


if __name__ == "__main__":
    unittest.main()
