#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scrapers/seiseki_org.py の統合テスト（新パッケージ構造）"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scrapers.seiseki_org import (
    parse_event_list_page, parse_event_detail, parse_dates_from_title,
    extract_pagination_max,
)

# ========= 日付パーステスト =========
def test_dates():
    cases = [
        ("【2026年5月2日（土）開催】RIVER", ("2026-05-02", None)),
        ("【2026年4月23日（木）～26（日）】", ("2026-04-23", "2026-04-26")),
        ("【キッチンカーカレンダー】2026年4月分", ("2026-04-01", "2026-04-30")),
        ("【2025年12月1日（月）～12月22日（月）】", ("2025-12-01", "2025-12-22")),
    ]
    for title, expected in cases:
        actual = parse_dates_from_title(title)
        assert actual == expected, f"{title}: {actual} != {expected}"
    print('  dates OK')

# ========= 一覧パース =========
LIST_HTML = """
<a href="https://seiseki.org/some-event-1/">
  【2026年5月2日（土）開催】RIVER FES
  詳細を見る　→
</a>
<a href="https://seiseki.org/event/page/2/">2</a>
<a href="https://seiseki.org/event/page/10/">10</a>
"""
def test_list():
    items = parse_event_list_page(LIST_HTML)
    assert len(items) == 1, f"expected 1, got {len(items)}"
    assert "RIVER" in items[0]["title"]
    assert extract_pagination_max(LIST_HTML) == 10
    print('  list OK')

# ========= 詳細パース：パターンA（コロン区切り）=========
DETAIL_A = """
<html><body>
<h3>イベント</h3>
<h3>【2026年5月2日（土）開催】RIVER SIDE DOG FES</h3>
<p>開催中</p>
<p>せいせきカワマチ</p>
<img src="https://seiseki.org/wp-content/uploads/2026/04/RIVER.jpg">
<p>人と犬が楽しむ。愛犬と一緒に。</p>
<p>日時：2026年5月２日（土） 10：00 ～ 16：00</p>
<p>場所：せいせきカワマチ（多摩川河川敷芝生広場）</p>
<p>主催：RIVER SIDE DOG FES 実行委員会</p>
</body></html>
"""

def test_detail_a():
    ev = parse_event_detail("https://seiseki.org/dog-fes/", DETAIL_A)
    assert ev.source == "seiseki.org"
    assert "RIVER" in ev.title
    assert ev.date_start == "2026-05-02"
    assert ev.venue and "多摩川河川敷" in ev.venue
    assert ev.organizer == "RIVER SIDE DOG FES 実行委員会"
    assert ev.time_label and "10：00" in ev.time_label
    assert ev.status == "開催中"
    assert "せいせきカワマチ" in ev.tags
    print('  detail-A OK')

# ========= 詳細パース：パターンB+C（縦棒+ブラケット）=========
DETAIL_BC = """
<html><body>
<h3>【2026年4月11日（土）～12日（日）開催】メリーゴーランド Vol.4</h3>
<p>終了</p>
<p>せいせきカワマチ</p>
<img src="https://seiseki.org/wp-content/uploads/2026/03/photo.jpeg">
<p>こだわりのイベント。</p>
<p>｜日時
・2026年4月11日（土）10：00～20：00
※両日ともに荒天中止</p>
<p>｜会場
多摩川河川敷（一ノ宮公園&せいせきカワマチ）</p>
<p>｜主催など
【主催】せいせきさくらがおかメリーゴーランド実行委員会 / 【後援】多摩市 / 【協力】京王電鉄</p>
</body></html>
"""

def test_detail_bc():
    ev = parse_event_detail("https://seiseki.org/merry/", DETAIL_BC)
    assert ev.source == "seiseki.org"
    assert ev.date_start == "2026-04-11" and ev.date_end == "2026-04-12"
    assert ev.venue and "多摩川河川敷" in ev.venue
    assert ev.organizer and "メリーゴーランド実行委員会" in ev.organizer
    # 主催が取れたので接頭辞なし
    assert not ev.organizer.startswith("[")
    assert ev.time_label and "10：00" in ev.time_label
    print('  detail-B+C OK')


if __name__ == "__main__":
    test_dates()
    test_list()
    test_detail_a()
    test_detail_bc()
    print("\nAll seiseki_org tests passed.")
