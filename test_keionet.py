#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scrapers/keionet.py のテスト"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scrapers.keionet import parse_topics_page, build_event


# 実データを参考にした最小再現
TOPICS_HTML = """
<html><body>
<header><a href="/info/seisekisakuragaoka/">聖蹟桜ヶ丘店TOP</a></header>
<main>
<a href="https://www.keionet.com/info/seisekisakuragaoka/topics/006328.html">
  <img src="https://www.keionet.com/info/seisekisakuragaoka/topics/cms_img/260510KAOFES_01.jpg">
  KAOFES2026
  5/10(日)
</a>
<a href="https://www.keionet.com/info/seisekisakuragaoka/topics/006205.html">
  <img src="https://www.keionet.com/info/seisekisakuragaoka/topics/cms_img/c55e8607.png">
  [キル フェ ボン]期間限定販売
  4/30(木)→5/13(水)
</a>
<a href="https://www.keionet.com/info/seisekisakuragaoka/topics/005204.html">
  <img src="https://www.keionet.com/info/seisekisakuragaoka/topics/cms_img/miki_thumbnail.jpg">
  [ミキハウス]出産準備セミナー
  毎月開催
</a>
<a href="https://www.keionet.com/info/seisekisakuragaoka/topics/006121.html">
  <img src="https://www.keionet.com/info/seisekisakuragaoka/topics/cms_img/a2c156b6.png">
  北欧屋台
  4/30(木)→5/6(水・振休)
</a>
<a href="https://www.keionet.com/info/seisekisakuragaoka/topics/006358.html">
  <img src="https://www.keionet.com/info/seisekisakuragaoka/topics/cms_img/260501curry_rogo.jpg">
  にっぽんカレー博 せいせき40th限定品
  5/1(金)→13(水)
</a>
<a href="/info/seisekisakuragaoka/">トップに戻る</a>
<a href="/info/inquiry/">お問い合わせ</a>
</main>
</body></html>
"""


def test_parse_topics():
    cards = parse_topics_page(TOPICS_HTML)
    print(f"  found {len(cards)} cards")
    for c in cards:
        print(f"    id={c['id']}  title={c['title']!r}  date={c['date_label']!r}")
    assert len(cards) == 5, f"expected 5 cards (anchors without IDs are filtered), got {len(cards)}"

    # KAOFES
    kaofes = next(c for c in cards if c["id"] == "006328")
    assert kaofes["title"] == "KAOFES2026"
    assert kaofes["date_label"] == "5/10(日)"
    assert kaofes["image_url"] and "260510KAOFES_01.jpg" in kaofes["image_url"]

    # ミキハウス（毎月開催）
    miki = next(c for c in cards if c["id"] == "005204")
    assert "ミキハウス" in miki["title"]
    assert miki["date_label"] == "毎月開催"

    # キル フェ ボン
    kil = next(c for c in cards if c["id"] == "006205")
    assert "キル フェ ボン" in kil["title"]
    assert "4/30" in kil["date_label"] and "5/13" in kil["date_label"]


def test_build_event():
    cards = parse_topics_page(TOPICS_HTML)
    kaofes = next(c for c in cards if c["id"] == "006328")
    ev = build_event(kaofes, hint_year=2026)
    print(f"  KAOFES: id={ev.id}  source={ev.source}")
    print(f"          date={ev.date_start}~{ev.date_end}  status={ev.status}")
    print(f"          title={ev.title}")
    print(f"          tags={ev.tags}  organizer={ev.organizer}")
    assert ev.source == "keionet.com"
    assert ev.id == "keionet-006328"
    assert ev.date_start == "2026-05-10"
    assert ev.date_end is None
    assert "ショッピングセンター" in ev.tags
    assert ev.organizer == "京王百貨店 聖蹟桜ヶ丘店"
    assert ev.title == "KAOFES2026"

    # 範囲日付（4/30→5/13）
    kil = next(c for c in cards if c["id"] == "006205")
    ev = build_event(kil, hint_year=2026)
    print(f"  キルフェボン: date={ev.date_start}~{ev.date_end}")
    assert ev.date_start == "2026-04-30"
    assert ev.date_end == "2026-05-13"

    # 「毎月開催」のような日付なしケース
    miki = next(c for c in cards if c["id"] == "005204")
    ev = build_event(miki, hint_year=2026)
    print(f"  ミキハウス: date={ev.date_start}~{ev.date_end}  status={ev.status}")
    assert ev.date_start is None
    assert ev.status is None  # 日付なしならステータスもなし


if __name__ == "__main__":
    print("=== parse_topics_page ===")
    test_parse_topics()
    print("=== build_event ===")
    test_build_event()
    print("\nAll keionet tests passed.")
