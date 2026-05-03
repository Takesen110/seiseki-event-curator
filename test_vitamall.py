#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scrapers/vitamall.py のテスト"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scrapers.vitamall import (
    parse_news_event_page, parse_event_detail, _extract_venue,
)


# 一覧ページ最小再現
LIST_HTML = """
<html><body>
<h1>ニュース＆イベント</h1>
<ul>
<li>
<a href="https://vitamallseiseki.jp/news_event/flowerbox/">
  <img src="https://vitamallseiseki.jp/wp-content/uploads/2026/05/6a271d48.jpg">
  2026.05.10
  親子で楽しもう！フラワーボックス作り
</a>
</li>
<li>
<a href="https://vitamallseiseki.jp/news_event/dance-mitsushima/">
  <img src="https://vitamallseiseki.jp/wp-content/uploads/2026/05/ff4d108f.png">
  ダンスイベント～三つの島の舞～
</a>
</li>
<li>
<a href="https://vitamallseiseki.jp/news_event/kyushinbi/">
  <img src="https://vitamallseiseki.jp/wp-content/uploads/2026/04/198156fd.png">
  休診日のお知らせ
</a>
</li>
<li>
<a href="https://vitamallseiseki.jp/news_event/pola/">
  <img src="https://vitamallseiseki.jp/wp-content/uploads/2026/03/IMG_8471.png">
  POLA肌分析＆ハンドマッサージ無料体験会
</a>
</li>
<li>
<a href="https://vitamallseiseki.jp/news_event/kodomonohi/">
  <img src="https://vitamallseiseki.jp/wp-content/uploads/2026/04/dc13e59e.jpg">
  2026.04.25
  子どもの日限定！LINE抽選会
</a>
</li>
</ul>
</body></html>
"""


def test_parse_list():
    cards = parse_news_event_page(LIST_HTML)
    print(f"  found {len(cards)} cards")
    for c in cards:
        print(f"    slug={c['slug']}  post_date={c['post_date']!r}  title={c['title_hint']!r}")
    assert len(cards) == 5

    flower = next(c for c in cards if c["slug"] == "flowerbox")
    assert flower["post_date"] == "2026-05-10"
    assert "フラワーボックス" in flower["title_hint"]

    # 投稿日なしのケース
    dance = next(c for c in cards if c["slug"] == "dance-mitsushima")
    assert dance["post_date"] == ""
    assert "ダンス" in dance["title_hint"]


# 詳細ページHTML（実データ参考）
DETAIL_HTML = """
<html><body>
<main>
<h1>親子で楽しもう！フラワーボックス作り</h1>
<img src="https://vitamallseiseki.jp/wp-content/uploads/2026/05/6a271d48.jpg">
<h1>親子で楽しもう！フラワーボックス作り</h1>
<p>2026.05.10〜2026.05.10</p>
<p>NEWS</p>
<h2>＼5/10(日)は母の日イベント開催／</h2>
<p>「いつもありがとう」の気持ちをこめて、お母さんにお花のプレゼントをしませんか？</p>
<p>お好きな花を選んで、オリジナルBOXをお作りいただけます！</p>
<p>■ 実施日時</p>
<p>【日時】5/10(日) ①11:00～12:00 ②13:00～14:00 ③14:00～15:00 ④15:00～16:00</p>
<p>■ 実施場所</p>
<p>1F スターバックス横 特設会場</p>
<p>■ 参加条件</p>
<p>当日のお買上げレシート2,000円以上のご提示</p>
</main>
</body></html>
"""


def test_detail():
    hints = {
        "slug": "flowerbox",
        "post_date": "2026-05-10",
        "title_hint": "親子で楽しもう！フラワーボックス作り",
        "image_url": "https://vitamallseiseki.jp/wp-content/uploads/2026/05/6a271d48.jpg",
    }
    ev = parse_event_detail(
        "https://vitamallseiseki.jp/news_event/flowerbox/",
        DETAIL_HTML, hints,
    )
    print(f"  id        = {ev.id}")
    print(f"  title     = {ev.title}")
    print(f"  date      = {ev.date_start} ~ {ev.date_end}")
    print(f"  status    = {ev.status}")
    print(f"  venue     = {ev.venue}")
    print(f"  organizer = {ev.organizer}")
    print(f"  tags      = {ev.tags}")
    assert ev.source == "vitamallseiseki.jp"
    assert ev.id == "vita-flowerbox"
    assert "フラワーボックス" in ev.title
    # "2026.05.10〜2026.05.10" が同日のため、end は None になる
    assert ev.date_start == "2026-05-10"
    assert ev.date_end is None
    assert ev.venue and "スターバックス横" in ev.venue
    assert "ショッピングセンター" in ev.tags


def test_venue_extract():
    body = """■ 実施場所
1F スターバックス横 特設会場
■ 参加条件"""
    v = _extract_venue(body)
    print(f"  venue: {v!r}")
    assert v and "スターバックス横" in v


if __name__ == "__main__":
    print("=== parse_list ===")
    test_parse_list()
    print("=== venue_extract ===")
    test_venue_extract()
    print("=== detail ===")
    test_detail()
    print("\nAll vitamall tests passed.")
