#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scrapers/square_sc.py のテスト"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scrapers.square_sc import (
    parse_top_page, parse_event_detail, _extract_event_period,
)


# トップページの最小再現
TOP_HTML = """
<html><body>
<h2>ショップニュース</h2>
<a href="https://square-sc.com/shopnews/abc-anniversary/">
  <img src="https://square-sc.com/wp-content/uploads/2026/04/db903a66.jpg">
  2026年4月15日2F 9ROUNDts-tan
  【4～5月限定】周年記念キャンペーン
  《4/1～5/31までの限定キャンペーン開催中》 お得な3大特典+入会初月の月会費無料！
</a>
<a href="https://square-sc.com/shopnews/tully-tiramisu/">
  <img src="https://square-sc.com/wp-content/uploads/2026/04/39a9fc58.jpg">
  2026年4月14日1Fタリーズコーヒーts-tan
  プチ贅沢感のある「ティラミス」でご褒美シェイク
  4/15～5/12 プチ贅沢感のある「ティラミス」でご褒美シェイク
</a>
<a href="https://square-sc.com/shopnews/janken/">
  <img src="https://square-sc.com/wp-content/uploads/2025/09/janken.jpg">
  2025年9月9日B1F カラフルパークts-tan
  じゃんけんイベント
  対象：小学生以下のお子様 スタッフにじゃんけんを挑み...
</a>
<a href="/shopnews/">ショップニュース一覧</a>
</body></html>
"""


def test_parse_top():
    cards = parse_top_page(TOP_HTML)
    print(f"  found {len(cards)} cards")
    for c in cards:
        print(f"    slug={c['slug']}  date={c['post_date']}  title={c['title_hint']!r}")
    assert len(cards) == 3

    anv = next(c for c in cards if c["slug"] == "abc-anniversary")
    assert anv["post_date"] == "2026-04-15"
    assert "9ROUND" in anv["floor_shop"]
    assert "周年記念" in anv["title_hint"]

    tully = next(c for c in cards if c["slug"] == "tully-tiramisu")
    assert tully["post_date"] == "2026-04-14"


def test_extract_event_period():
    body = """《4/1〜5/31までの限定キャンペーン開催中》
お得な3大特典+入会初月の月会費無料！"""
    s, e = _extract_event_period(body, "2026-04-15")
    print(f"  4/1〜5/31: {s} ~ {e}")
    assert s == "2026-04-01"
    assert e == "2026-05-31"

    body2 = "4/15～5/12 プチ贅沢感のある「ティラミス」でご褒美シェイク"
    s, e = _extract_event_period(body2, "2026-04-14")
    print(f"  4/15〜5/12: {s} ~ {e}")
    assert s == "2026-04-15"
    assert e == "2026-05-12"

    # イベント期間なし → None
    body3 = "キッズメニューも取り揃えております。お子様とご一緒にお過ごしください。"
    s, e = _extract_event_period(body3, "2024-05-07")
    print(f"  no date: {s} ~ {e}")
    assert s is None


# 詳細ページHTMLの最小再現
DETAIL_HTML = """
<html><body>
<header>nav</header>
<main>
<nav>パンくず</nav>
<h1>【4～5月限定】周年記念キャンペーン</h1>
<p>《4/1〜5/31までの限定キャンペーン開催中》</p>
<p>お得な3大特典+入会初月の月会費無料！</p>
<p>さらに、体験後その場でご入会いただいた場合グローブ＆バンテージもプレゼント</p>
<dl>
  <dt>店舗名</dt>
  <dd>2F 9ROUND</dd>
</dl>
</main>
</body></html>
"""


def test_detail():
    hints = {
        "slug": "abc-anniversary",
        "post_date": "2026-04-15",
        "floor_shop": "2F 9ROUND",
        "title_hint": "【4～5月限定】周年記念キャンペーン",
        "summary_hint": "《4/1～5/31までの限定キャンペーン開催中》",
        "image_url": "https://square-sc.com/wp-content/uploads/2026/04/db903a66.jpg",
    }
    ev = parse_event_detail(
        "https://square-sc.com/shopnews/abc-anniversary/",
        DETAIL_HTML, hints,
    )
    print(f"  id        = {ev.id}")
    print(f"  title     = {ev.title}")
    print(f"  date      = {ev.date_start} ~ {ev.date_end}")
    print(f"  status    = {ev.status}")
    print(f"  venue     = {ev.venue}")
    print(f"  organizer = {ev.organizer}")
    print(f"  tags      = {ev.tags}")
    assert ev.source == "square-sc.com"
    assert ev.id == "sqsc-abc-anniversary"
    assert "周年記念" in ev.title
    assert ev.date_start == "2026-04-01"
    assert ev.date_end == "2026-05-31"
    assert ev.status == "開催中"  # 5/3時点で範囲内
    assert ev.venue == "2F 9ROUND"
    assert ev.organizer == "ザ・スクエア聖蹟桜ヶ丘"
    assert "ショッピングセンター" in ev.tags


if __name__ == "__main__":
    print("=== parse_top ===")
    test_parse_top()
    print("=== extract_event_period ===")
    test_extract_event_period()
    print("=== detail ===")
    test_detail()
    print("\nAll square_sc tests passed.")
