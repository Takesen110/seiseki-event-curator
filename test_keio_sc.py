#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scrapers/keio_sc.py のテスト"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scrapers.keio_sc import (
    parse_event_list_page, parse_event_detail, parse_keio_date,
    yearmonth_iter, _id_from_url,
)
from datetime import date


def test_parse_keio_date():
    """京王SC独自の日付表記をパース"""
    cases = [
        # (入力, hint_year, 期待値)
        ("5月16日（土）・17日（日）",            2026, ("2026-05-16", "2026-05-17")),
        ("2026年4月1日(水)～2026年5月10日(日)",  2026, ("2026-04-01", "2026-05-10")),
        ("4/29（水・祝）～5/6（水・振休）",       2026, ("2026-04-29", "2026-05-06")),
        ("5月7日（木）～5月13日（水）",           2026, ("2026-05-07", "2026-05-13")),
        ("5月3日（日・祝）～5月4日（月・祝）",     2026, ("2026-05-03", "2026-05-04")),
        ("12月25日（木）～1月10日（土）",          2025, ("2025-12-25", "2026-01-10")),  # 年またぎ
        ("2026年4月1日(水)～5月10日(日)",         2026, ("2026-04-01", "2026-05-10")),  # 終了側だけ年なし
        ("5月10日（日）",                          2026, ("2026-05-10", None)),
        ("",                                      2026, (None, None)),
    ]
    for text, hint, expected in cases:
        actual = parse_keio_date(text, hint)
        ok = actual == expected
        mark = "OK" if ok else "NG"
        print(f"  [{mark}] {text!r} (hint={hint}) -> {actual}")
        assert ok, f"expected {expected}"


def test_yearmonth_iter():
    """前後N ヶ月のリスト生成"""
    # 2026/05中心、span=1 → 04, 05, 06
    months = yearmonth_iter(date(2026, 5, 15), 1)
    assert months == [(2026, 4), (2026, 5), (2026, 6)]
    print(f"  OK 2026/05 span=1 → {months}")

    # 年またぎ: 2026/01中心、span=2 → 25/11, 25/12, 26/01, 26/02, 26/03
    months = yearmonth_iter(date(2026, 1, 15), 2)
    assert months == [(2025, 11), (2025, 12), (2026, 1), (2026, 2), (2026, 3)]
    print(f"  OK 2026/01 span=2 → {months}")


def test_id_from_url():
    assert _id_from_url("https://www.keio-sc.jp/eventtopics/detail/?cd=000709") == "keiosc-000709"
    print("  OK id-from-url")


# 一覧ページHTMLの最小再現
LIST_HTML = """
<html><body>
<a href="https://www.keio-sc.jp/eventtopics/detail/?cd=000710">
  <img src="/uploads/images/seiseki/.../sample.jpg">
  EVENT
  5月16日（土）・17日（日）
  せいせきサステナ Happy 2days
</a>
<a href="https://www.keio-sc.jp/eventtopics/detail/?cd=000709">
  EVENT
  5月7日（木）～5月13日（水）
  母の日 ハンドメイドワークショップ
</a>
<a href="https://www.keio-sc.jp/eventtopics/?yearmonth=202604">04APR</a>
</body></html>
"""

def test_list():
    items = parse_event_list_page(LIST_HTML)
    print(f"  found {len(items)} events")
    for it in items:
        print(f"    {it}")
    assert len(items) == 2
    cds = [it["cd"] for it in items]
    assert "000710" in cds and "000709" in cds
    # 日付ヒントが取れている
    target = next(i for i in items if i["cd"] == "000709")
    assert "5月7日" in target["date_label_hint"]
    assert "母の日" in target["title_hint"]


# 詳細ページHTMLの最小再現（実データを参考に）
DETAIL_HTML = """
<html>
<head><title>母の日 ハンドメイドワークショップを開催します！ | イベント&トピックス｜せいせき：京王聖蹟桜ヶ丘ショッピングセンター</title></head>
<body>
<header><a href="/">ホーム</a></header>
<main>
<h2>母の日 ハンドメイドワークショップを開催します！</h2>
<img src="https://www.keio-sc.jp/uploads/images/resized/0x300/seiseki/000002/000002/1664b1f8.jpg">
<p>🌸母の日 ハンドメイドワークショップを開催します🌸</p>
<p>お子様から大人までお楽しみいただけます！</p>
<p>日時：5月7日（木）～5月13日（水）　10：00～17：00</p>
<p>場所：B館2階センターコート</p>

<ul>
<li>期間5月7日（木）～5月13日（水）</li>
<li>時間10：00～17：00</li>
<li>場所B館2階センターコート</li>
<li>参加方法予約不要</li>
<li>お問い合わせ麻布Amy（エイミィ）</li>
<li>お問い合わせ(TEL)03-6277-7366</li>
<li>備考・ワークショップキットの販売はいたしません。</li>
</ul>
</main>
<footer>BACK TO LIST</footer>
</body></html>
"""

def test_detail():
    ev = parse_event_detail(
        "https://www.keio-sc.jp/eventtopics/detail/?cd=000709",
        DETAIL_HTML, hint_year=2026,
    )
    print(f"  id        = {ev.id}")
    print(f"  source    = {ev.source}")
    print(f"  title     = {ev.title}")
    print(f"  date      = {ev.date_start} ~ {ev.date_end}")
    print(f"  status    = {ev.status}")
    print(f"  venue     = {ev.venue}")
    print(f"  organizer = {ev.organizer}")
    print(f"  time      = {ev.time_label}")
    print(f"  tags      = {ev.tags}")
    print(f"  image     = {ev.image_url}")

    assert ev.source == "keio-sc.jp"
    assert ev.id == "keiosc-000709"
    assert "母の日" in ev.title
    assert ev.date_start == "2026-05-07"
    assert ev.date_end == "2026-05-13"
    assert ev.venue == "B館2階センターコート"
    assert ev.organizer == "麻布Amy（エイミィ）"
    assert ev.time_label and "10：00" in ev.time_label
    assert "ショッピングセンター" in ev.tags
    assert ev.image_url and "1664b1f8.jpg" in ev.image_url


if __name__ == "__main__":
    print("=== parse_keio_date ===")
    test_parse_keio_date()
    print("=== yearmonth_iter ===")
    test_yearmonth_iter()
    print("=== id_from_url ===")
    test_id_from_url()
    print("=== list ===")
    test_list()
    print("=== detail ===")
    test_detail()
    print("\nAll keio_sc tests passed.")
