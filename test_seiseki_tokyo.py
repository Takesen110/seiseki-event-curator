#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scrapers/seiseki_tokyo.py のテスト"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scrapers.seiseki_tokyo import (
    parse_archive_page, parse_event_detail, _infer_tags,
)


# 一覧ページHTMLの最小再現（実データ参考）
ARCHIVE_HTML = """
<html><body>
<h2>イベント一覧</h2>
<ul>
<li>
  <a href="https://seiseki.tokyo/news/machi_news010.html">
    <img src="https://seiseki.tokyo/news/test20260501c.jpg" alt="耳をすませば関連イベント告知画像">
  </a>
  <p>EVENTNEWS</p>
  <p>2026.05.01</p>
  <h3><a href="https://seiseki.tokyo/news/machi_news010.html">『耳をすませば』関連イベント開催予定 in 聖蹟桜ヶ丘</a></h3>
  <p>聖蹟桜ヶ丘で『耳をすませば』関連イベントが開催予定。記念展示やトークショーを予定しています。</p>
</li>
<li>
  <a href="https://seiseki.tokyo/news/machi_news009.html">
    <img src="https://seiseki.tokyo/news/20260405.png">
  </a>
  <p>EVENTNEWS</p>
  <p>2026.04.05</p>
  <h3><a href="https://seiseki.tokyo/news/machi_news009.html">せいせきお宝マップ 2026春が完成しました！</a></h3>
  <p>みなさまと一緒に作り上げた「せいせきお宝マップ 2026春」が、昨年を上回る大盛況のうちに完成しました。</p>
  <p>終了しました</p>
</li>
<li>
  <a href="https://seiseki.tokyo/news/machi_news006.html">
    <img src="https://seiseki.tokyo/news/machi_news006.png">
  </a>
  <p>EVENTNEWS</p>
  <p>2025.12.08</p>
  <h3><a href="https://seiseki.tokyo/news/machi_news006.html">第21回 せいせきハートフルコンサート</a></h3>
  <p>2026年も、スタジオジブリ制作の映画『耳をすませば』の参考となった街「聖蹟桜ヶ丘」にて、本名陽子さんをお迎えし、開催。</p>
  <p>終了しました</p>
</li>
</ul>
</body></html>
"""


def test_parse_archive():
    cards = parse_archive_page(ARCHIVE_HTML)
    print(f"  found {len(cards)} cards")
    for c in cards:
        print(f"    id={c['id']}  title={c['title_hint']!r}")
        print(f"      ended={c['is_ended']}  date={c['date_label_hint']}")
    assert len(cards) == 3

    # ID 010：耳すま関連、開催予定
    ten = next(c for c in cards if c["id"] == "010")
    assert "耳をすませば" in ten["title_hint"]
    assert ten["is_ended"] is False
    assert ten["date_label_hint"] == "2026-05-01"

    # ID 009：お宝マップ、終了
    nine = next(c for c in cards if c["id"] == "009")
    assert nine["is_ended"] is True

    # ID 006：ハートフルコンサート、終了
    six = next(c for c in cards if c["id"] == "006")
    assert "ハートフルコンサート" in six["title_hint"]
    assert six["is_ended"] is True


# 詳細ページHTML（実データ参考）
DETAIL_HEARTFUL_HTML = """
<html>
<head><title>第21回 せいせきハートフルコンサート | せいせき観光まちづくり会議</title></head>
<body>
<h2>第21回 せいせきハートフルコンサート</h2>
<p>2025.12.08</p>
<p>イベント</p>
<img src="https://seiseki.tokyo/news/machi_news006.png">

<p>2026年も、スタジオジブリ制作の映画『耳をすませば』の参考となった街「聖蹟桜ヶ丘」にて、本名陽子さんをお迎えし、「せいせきハートフルコンサート」を開催いたします。</p>
<p>みなさまにとって、心温まる素敵な時間をお届けできれば幸いです。</p>

<h3>開催概要</h3>
<ul>
<li>日時：2026年2月15日（日）開場 13:30 ／ 開演 14:00（終演予定 15:30）</li>
<li>会場：多摩市立関戸公民館 8階 ヴィータホール（京王線 聖蹟桜ヶ丘駅より徒歩3分）</li>
<li>入場：無料（事前申込制・抽選）／定員200名</li>
</ul>

<h3>出演</h3>
<ul>
<li>本名陽子（声優・歌手）</li>
<li>Kao（ヴァイオリン）</li>
</ul>

<h3>応募方法</h3>
<p>往復ハガキによる事前申込制となります。</p>
<p>締切：2025年12月31日（水）必着</p>

</body></html>
"""


def test_detail_heartful():
    hints = {
        "title_hint": "第21回 せいせきハートフルコンサート",
        "image_url": "https://seiseki.tokyo/news/machi_news006.png",
        "date_label_hint": "2025-12-08",
        "is_ended": True,
    }
    ev = parse_event_detail(
        "https://seiseki.tokyo/news/machi_news006.html",
        DETAIL_HEARTFUL_HTML, hints,
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

    assert ev.source == "seiseki.tokyo"
    assert ev.id == "seitokyo-006"
    assert "ハートフルコンサート" in ev.title
    assert ev.date_start == "2026-02-15"
    assert ev.venue and "ヴィータホール" in ev.venue
    assert ev.time_label and "2026年2月15日" in ev.time_label
    assert ev.organizer == "せいせき観光まちづくり会議"  # 本文に主催記述なし → デフォルト
    # is_ended が hints で渡されているので status は "終了"
    assert ev.status == "終了"
    # まちなか + 京王線駅徒歩3分系で「ショッピングセンター」キーワードに反応してないか
    assert "まちなか" in ev.tags


def test_infer_tags():
    # デフォルトはまちなか
    tags = _infer_tags("耳をすませば関連イベント", "聖蹟桜ヶ丘の地域文化", None)
    assert tags == ["まちなか"]

    # SC言及あり → SC追加
    tags = _infer_tags("展", "京王SC 7階で開催", None)
    assert "ショッピングセンター" in tags
    assert "まちなか" in tags

    # カワマチ言及あり → カワマチ追加
    tags = _infer_tags("夏祭り", "せいせきカワマチ多摩川河川敷で", None)
    assert "せいせきカワマチ" in tags
    assert "まちなか" in tags

    print("  infer_tags OK")


if __name__ == "__main__":
    print("=== parse_archive ===")
    test_parse_archive()
    print("=== detail (ハートフル) ===")
    test_detail_heartful()
    print("=== infer_tags ===")
    test_infer_tags()
    print("\nAll seiseki_tokyo tests passed.")
