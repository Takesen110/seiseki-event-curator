#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scrapers/jinja_recurring.py のテスト"""
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scrapers.jinja_recurring import (
    nth_weekday_of_month, sunday_before, expand_rule,
    expand_events, WEEKDAY_MAP,
)


def test_nth_weekday():
    # 2026年9月第2日曜 = 9/13(日)
    d = nth_weekday_of_month(2026, 9, WEEKDAY_MAP["sunday"], 2)
    print(f"  2026/9 第2日曜 = {d}")
    assert d == date(2026, 9, 13)

    # 2025年9月第2日曜 = 9/14(日)（実際の小野神社例大祭日と一致）
    d = nth_weekday_of_month(2025, 9, WEEKDAY_MAP["sunday"], 2)
    print(f"  2025/9 第2日曜 = {d}")
    assert d == date(2025, 9, 14)

    # 2026年9月第2土曜 = 9/12(土)（白山神社例大祭）
    d = nth_weekday_of_month(2026, 9, WEEKDAY_MAP["saturday"], 2)
    print(f"  2026/9 第2土曜 = {d}")
    assert d == date(2026, 9, 12)

    # 2026年4月第1日曜 = 4/5(日)（小野神社春の祭礼）
    d = nth_weekday_of_month(2026, 4, WEEKDAY_MAP["sunday"], 1)
    print(f"  2026/4 第1日曜 = {d}")
    assert d == date(2026, 4, 5)


def test_sunday_before():
    # 2026年節分（2/3）の直前の日曜 = 2/1(日)
    d = sunday_before(2026, 2, 3)
    print(f"  2026 節分(2/3) 直前の日曜 = {d}")
    assert d == date(2026, 2, 1)

    # 2027年節分（2/3）の直前の日曜 = 1/31(日)
    d = sunday_before(2027, 2, 3)
    print(f"  2027 節分(2/3) 直前の日曜 = {d}")
    assert d == date(2027, 1, 31)

    # 2024年は節分が土曜だったので、その前の日曜 = 1/28
    d = sunday_before(2024, 2, 3)
    print(f"  2024 節分(2/3) 直前の日曜 = {d}")
    assert d == date(2024, 1, 28)


def test_expand_rule():
    # nth_weekday with offset (例大祭の宵宮+本祭)
    rule = {
        "type": "nth_weekday",
        "month": 9,
        "weekday": "sunday",
        "nth": 2,
        "duration_days": 2,
        "start_offset_days": -1,
    }
    start, end = expand_rule(rule, 2026)
    print(f"  例大祭 2026: {start} 〜 {end}")
    assert start == date(2026, 9, 12)  # 第2日曜の前日 = 土曜
    assert end == date(2026, 9, 13)

    # day_of_year (初詣)
    rule = {
        "type": "day_of_year",
        "month": 1,
        "day": 1,
        "duration_days": 3,
    }
    start, end = expand_rule(rule, 2026)
    print(f"  初詣 2026: {start} 〜 {end}")
    assert start == date(2026, 1, 1)
    assert end == date(2026, 1, 3)

    # sunday_before (節分祭)
    rule = {"type": "sunday_before", "month": 2, "day": 3}
    start, end = expand_rule(rule, 2026)
    print(f"  節分祭 2026: {start} ({end})")
    assert start == date(2026, 2, 1)
    assert end is None


def test_expand_events():
    """recurring_jinja.json を実際に読み込んで展開"""
    events = expand_events(year_range=(2025, 2026))
    print(f"  expanded {len(events)} events for 2025-2026")
    # 9件のルール × 2年 = 18 件
    assert len(events) == 18

    # 全イベントに「要日程確認」note が含まれていることを確認
    sample = events[0]
    print(f"  sample id    = {sample.id}")
    print(f"  sample title = {sample.title}")
    print(f"  sample dates = {sample.date_start} 〜 {sample.date_end}")
    print(f"  sample body  = {sample.body[:80]}...")
    assert sample.source == "jinja-recurring.local"
    assert "※" in sample.body  # 注意書きが含まれている

    # 小野神社例大祭2026年版を確認
    ono26 = next(e for e in events if e.id == "ono-reitaisai-2026")
    print(f"  ono-reitaisai-2026: {ono26.date_start} 〜 {ono26.date_end}")
    assert ono26.date_start == "2026-09-12"  # 9月第2土曜（宵宮）
    assert ono26.date_end == "2026-09-13"    # 9月第2日曜（本祭）
    assert "最新情報は" in ono26.body

    # 関戸熊野神社の節分祭2026年版
    setsubun26 = next(e for e in events if e.id == "kumano-setsubun-2026")
    print(f"  kumano-setsubun-2026: {setsubun26.date_start}")
    assert setsubun26.date_start == "2026-02-01"  # 節分(2/3)直前の日曜

    # 連光寺白山神社2026
    hakusan26 = next(e for e in events if e.id == "hakusan-reitaisai-2026")
    print(f"  hakusan-reitaisai-2026: {hakusan26.date_start}")
    assert hakusan26.date_start == "2026-09-12"  # 9月第2土曜


if __name__ == "__main__":
    print("=== nth_weekday_of_month ===")
    test_nth_weekday()
    print("=== sunday_before ===")
    test_sunday_before()
    print("=== expand_rule ===")
    test_expand_rule()
    print("=== expand_events ===")
    test_expand_events()
    print("\nAll jinja_recurring tests passed.")
