#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scrapers/tamapon.py のテスト"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scrapers.tamapon import (
    parse_archive_page, parse_event_detail, _infer_tags,
    is_seiseki_related, _extract_field,
    SEISEKI_KEYWORDS, NON_SEISEKI_TITLE_KEYWORDS,
)


# 多摩ポンのカテゴリアーカイブの最小再現
ARCHIVE_HTML = """
<html><body>
<main>
<article>
  <a href="https://tamapon.com/2026/04/27/curryhakuinseiseki2026/">
    <img src="https://tamapon.com/wp-content/uploads/2026/04/curryhaku.jpg">
  </a>
  <h2><a href="https://tamapon.com/2026/04/27/curryhakuinseiseki2026/">「にっぽんカレー博 in せいせき」5/1(金)開幕！全国の人気カレー26店舗が聖蹟に集結</a></h2>
  <p>2026.04.27</p>
</article>

<article>
  <a href="https://tamapon.com/2026/04/14/kaofes2026/">
    <img src="https://tamapon.com/wp-content/uploads/2026/04/kaofes.jpg">
  </a>
  <h2><a href="https://tamapon.com/2026/04/14/kaofes2026/">聖蹟桜ヶ丘「KAOFES 2026」が5/10(日)“母の日”に開催！夜はしゃぼん玉舞う幻想フィナーレも</a></h2>
  <p>2026.04.14</p>
</article>

<article>
  <a href="https://tamapon.com/2026/03/14/seiseki-merrygoround2026/">
    <img src="https://tamapon.com/wp-content/uploads/2026/03/merry.jpg">
  </a>
  <h2><a href="https://tamapon.com/2026/03/14/seiseki-merrygoround2026/">せいせきさくらがおか MERRY GO ROUND Vol.4が4/11(土)から開催！初の2日間開催へ</a></h2>
  <p>2026.03.14</p>
</article>

<article>
  <a href="https://tamapon.com/2026/04/20/tachikawa-festival/">
    <img src="https://tamapon.com/wp-content/uploads/2026/04/tachi.jpg">
  </a>
  <h2><a href="https://tamapon.com/2026/04/20/tachikawa-festival/">立川グリーンスプリングスで「立川蚤の市」がGWに初開催！古道具からフードまで40組が集結</a></h2>
  <p>2026.04.20</p>
</article>

<article>
  <a href="https://tamapon.com/2026/03/01/tamacenter-park/">
    <img src="https://tamapon.com/wp-content/uploads/2026/03/tamac.jpg">
  </a>
  <h2><a href="https://tamapon.com/2026/03/01/tamacenter-park/">GWは多摩センターが丸ごと遊び場に！「こどもまつり2026」が5/3(日祝)から3日間開催</a></h2>
  <p>2026.03.01</p>
</article>

<a href="https://tamapon.com/category/event/page/2/" rel="next">次のページ</a>
</main>
</body></html>
"""


def test_parse_archive():
    cards = parse_archive_page(ARCHIVE_HTML)
    print(f"  found {len(cards)} cards")
    for c in cards:
        print(f"    slug={c['slug']}  date={c['post_date']}")
        print(f"      title={c['title_hint'][:50]!r}")
    assert len(cards) == 5

    curry = next(c for c in cards if "curryhaku" in c["slug"])
    assert curry["post_date"] == "2026-04-27"
    assert "カレー博" in curry["title_hint"]
    assert curry["image_url"] and "curryhaku.jpg" in curry["image_url"]

    kaofes = next(c for c in cards if "kaofes" in c["slug"])
    assert "KAOFES" in kaofes["title_hint"]


def test_is_seiseki_related():
    # 明示的に聖蹟桜ヶ丘
    assert is_seiseki_related("聖蹟桜ヶ丘で「第45回せいせき桜まつり」4/5(日)開催", "")
    assert is_seiseki_related("せいせきカワマチで開催", "")
    # 多摩センターで聖蹟言及なし → 除外
    assert not is_seiseki_related(
        "GWは多摩センターが丸ごと遊び場に！「こどもまつり2026」", "")
    # 立川 → 除外
    assert not is_seiseki_related(
        "立川グリーンスプリングスで「立川蚤の市」", "")
    # 多摩センター × 聖蹟連携 → タイトルに聖蹟あり、採用
    assert is_seiseki_related(
        "多摩センターと聖蹟桜ヶ丘で連携イベント", "")
    # タイトルでは判定不能、本文に聖蹟あり → 採用
    assert is_seiseki_related(
        "GWイベント特集",
        "...そして関戸公民館では...")
    # タイトル本文ともに聖蹟言及なし
    assert not is_seiseki_related("府中で花火大会", "夜空に1万4000発")
    print("  is_seiseki_related OK")


# 詳細ページHTML（実データから簡素化したもの）
DETAIL_KAOFES_HTML = """
<html>
<head>
<meta property="og:image" content="https://tamapon.com/wp-content/uploads/2026/04/kaofes-og.jpg">
<title>聖蹟桜ヶ丘「KAOFES 2026」が5/10(日)“母の日”に開催！</title>
</head>
<body>
<main>
<article>
<h1>聖蹟桜ヶ丘「KAOFES 2026」が5/10(日)"母の日"に開催！夜はしゃぼん玉舞う幻想フィナーレも</h1>

<p>多摩市・聖蹟桜ヶ丘の一ノ宮公園にて「KAOFES2026」が、2026年5月10日(日)の"母の日"に開催されます。</p>

<p>子どもたちが主役の体験型コンテンツが充実した注目イベント。</p>
<p>会場は、京王線・聖蹟桜ヶ丘駅近くの一ノ宮公園にある多摩川河川敷・カワマチエリアです。</p>

<p>開催日時：2026年5月10日(日)11:00〜19:30 ※雨天中止</p>
<p>場所：『約束の場所』多摩市 一ノ宮公園・カワマチエリア（京王線・聖蹟桜ヶ丘駅近く）</p>
<p>特別協賛：赤枝医院</p>
<p>共催：聖蹟桜ヶ丘エリアマネジメント</p>
<p>後援：多摩市、多摩商工会議所</p>

</article>
</main>
</body></html>
"""


def test_detail_kaofes():
    hints = {
        "slug": "kaofes2026",
        "post_date": "2026-04-14",
        "title_hint": "聖蹟桜ヶ丘「KAOFES 2026」が5/10(日)母の日に開催！",
        "image_url": "https://tamapon.com/wp-content/uploads/2026/04/kaofes.jpg",
    }
    ev = parse_event_detail(
        "https://tamapon.com/2026/04/14/kaofes2026/",
        DETAIL_KAOFES_HTML, hints,
    )
    print(f"  id        = {ev.id}")
    print(f"  title     = {ev.title[:50]}")
    print(f"  date      = {ev.date_start} ~ {ev.date_end}")
    print(f"  status    = {ev.status}")
    print(f"  venue     = {ev.venue}")
    print(f"  organizer = {ev.organizer}")
    print(f"  tags      = {ev.tags}")

    assert ev.source == "tamapon.com"
    assert ev.id == "tamapon-kaofes2026"
    assert "KAOFES" in ev.title
    assert ev.date_start == "2026-05-10"
    assert ev.venue and "一ノ宮公園" in ev.venue
    # カワマチエリアなので せいせきカワマチ タグつく
    assert "せいせきカワマチ" in ev.tags


def test_extract_field():
    body = """開催日時：2026年5月10日(日)11:00〜19:30 ※雨天中止
場所：多摩市 一ノ宮公園
主催：聖蹟桜ヶ丘エリアマネジメント"""
    assert _extract_field(body, ("開催日時", "日時")) == "2026年5月10日(日)11:00〜19:30 ※雨天中止"
    assert _extract_field(body, ("場所", "会場")) == "多摩市 一ノ宮公園"
    assert _extract_field(body, ("主催",)) == "聖蹟桜ヶ丘エリアマネジメント"
    print("  _extract_field OK")


def test_infer_tags():
    # カワマチ × まちなか系（桜まつり）
    tags = _infer_tags(
        "せいせき桜まつり",
        "多摩川河川敷でせいせき桜まつり実行委員会主催",
        "聖蹟桜ヶ丘駅周辺")
    assert "せいせきカワマチ" in tags
    assert "まちなか" in tags

    # SC系（KAOFES会場のSC）
    tags = _infer_tags(
        "せいせきたのしいおやつフェス",
        "京王聖蹟桜ヶ丘SC A館6階アウラホール",
        "")
    assert "ショッピングセンター" in tags

    # デフォまちなか
    tags = _infer_tags("ハートフルコンサート", "関戸公民館で開催", "ヴィータホール")
    assert "まちなか" in tags
    print("  infer_tags OK")


if __name__ == "__main__":
    print("=== parse_archive ===")
    test_parse_archive()
    print("=== is_seiseki_related ===")
    test_is_seiseki_related()
    print("=== _extract_field ===")
    test_extract_field()
    print("=== infer_tags ===")
    test_infer_tags()
    print("=== detail (KAOFES) ===")
    test_detail_kaofes()
    print("\nAll tamapon tests passed.")
