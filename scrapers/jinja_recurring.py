#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrapers/jinja_recurring.py
聖蹟桜ヶ丘エリアの神社の年中行事（定例イベント）を、
data/recurring_jinja.json に定義された再帰ルールから展開して
events.json に投入する。

source identifier: "jinja-recurring.local"

特徴:
- スクレイピング不要（手動メンテのデータをルールベース展開）
- 過去1年〜未来1年の発生日を計算してイベント化
- 神社の祭事は年により日程が前後するため、note にその旨を記載
- UI側で「ソース：神社（要日程確認）」とわかるよう表示

ルール種別:
- nth_weekday    : 月内のN回目の曜日（例: 9月第2日曜）
- day_of_year    : 固定日（例: 1/1〜1/3）
- sunday_before  : 指定日の直前の日曜（例: 節分2/3 直前の日曜）
"""
from __future__ import annotations

import argparse
import json
import sys
from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scrapers.common import (  # noqa: E402
    Event, now_iso, load_existing, save_events, merge_events,
    DATA_DIR,
)

# ----------------------------------------------------------------------
SOURCE = "jinja-recurring.local"
RECURRING_DATA_FILE = DATA_DIR / "recurring_jinja.json"

WEEKDAY_MAP = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


# ----------------------------------------------------------------------
# ルール展開
# ----------------------------------------------------------------------
def nth_weekday_of_month(year: int, month: int, weekday: int, nth: int) -> date:
    """指定年月の第N回目の曜日の日付を返す。
    weekday: 0=Monday ... 6=Sunday
    nth: 1, 2, 3, 4, 5
    """
    first = date(year, month, 1)
    # その月の最初の指定曜日が何日か
    days_until = (weekday - first.weekday()) % 7
    first_target = 1 + days_until
    target_day = first_target + (nth - 1) * 7
    # 月末超過チェック
    last_day = monthrange(year, month)[1]
    if target_day > last_day:
        raise ValueError(f"{year}-{month} に第{nth}{weekday}曜は存在しません")
    return date(year, month, target_day)


def sunday_before(year: int, month: int, day: int) -> date:
    """指定日の直前の日曜日（指定日が日曜ならその日）を返す"""
    target = date(year, month, day)
    days_back = (target.weekday() - 6) % 7  # 日曜=6
    return target - timedelta(days=days_back)


def expand_rule(rule: dict, year: int) -> tuple[date, date | None] | None:
    """ルールから (start_date, end_date) を計算。
    展開できなければ None。
    """
    rtype = rule.get("type")

    if rtype == "nth_weekday":
        weekday_name = rule.get("weekday", "sunday").lower()
        weekday_idx = WEEKDAY_MAP.get(weekday_name)
        if weekday_idx is None:
            return None
        try:
            base = nth_weekday_of_month(
                year, rule["month"], weekday_idx, rule.get("nth", 1)
            )
        except ValueError:
            return None
        # start_offset_days で開始日をずらす（例：宵宮で前日土曜から）
        offset = rule.get("start_offset_days", 0)
        start = base + timedelta(days=offset)
        # duration_days で期間を計算
        duration = rule.get("duration_days", 1)
        end = start + timedelta(days=duration - 1) if duration > 1 else None
        return (start, end)

    elif rtype == "day_of_year":
        try:
            start = date(year, rule["month"], rule["day"])
        except ValueError:
            return None
        duration = rule.get("duration_days", 1)
        end = start + timedelta(days=duration - 1) if duration > 1 else None
        return (start, end)

    elif rtype == "sunday_before":
        start = sunday_before(year, rule["month"], rule["day"])
        duration = rule.get("duration_days", 1)
        end = start + timedelta(days=duration - 1) if duration > 1 else None
        return (start, end)

    return None


def infer_status(start: date, end: date | None) -> str:
    """日付からステータス推定"""
    today = date.today()
    actual_end = end or start
    if today < start:
        return "開催予定"
    elif start <= today <= actual_end:
        return "開催中"
    else:
        return "終了"


# ----------------------------------------------------------------------
# メインフロー
# ----------------------------------------------------------------------
def expand_events(year_range: tuple[int, int] | None = None) -> list[Event]:
    """recurring_jinja.json から指定年範囲のイベントを展開"""
    if not RECURRING_DATA_FILE.exists():
        print(f"  ! data file not found: {RECURRING_DATA_FILE}", file=sys.stderr)
        return []

    with RECURRING_DATA_FILE.open(encoding="utf-8") as f:
        raw = json.load(f)

    today = date.today()
    if year_range is None:
        # デフォ: 過去1年〜未来1年
        start_year = today.year - 1
        end_year = today.year + 1
    else:
        start_year, end_year = year_range

    new_events: list[Event] = []
    iso_now = now_iso()

    for entry in raw.get("events", []):
        rule = entry.get("rule", {})
        for year in range(start_year, end_year + 1):
            result = expand_rule(rule, year)
            if not result:
                continue
            start, end = result

            ds = start.isoformat()
            de = end.isoformat() if end else None
            status = infer_status(start, end)

            # ID は rule_id + 年で一意化
            event_id = f"{entry['id']}-{year}"

            # note を body に追加して、UIで注意書きとして見える状態に
            base_body = entry.get("body", "")
            note = entry.get("note", "")
            body_parts = []
            if base_body:
                body_parts.append(base_body)
            if note:
                body_parts.append(f"※ {note}")
            body = "\n\n".join(body_parts)

            ev = Event(
                id=event_id,
                source=SOURCE,
                url=entry.get("url", ""),
                title=entry["title"],
                date_label=f"{ds}" + (f" 〜 {de}" if de else ""),
                date_start=ds,
                date_end=de,
                status=status,
                tags=list(entry.get("tags", ["まちなか"])),
                image_url=None,  # 神社系は画像なし運用
                body=body,
                venue=entry.get("venue"),
                organizer=entry.get("organizer"),
                time_label=None,
                is_kitchen_car=False,
                first_seen=iso_now,
                last_seen=iso_now,
            )
            new_events.append(ev)

    return new_events


def crawl(**kwargs) -> None:
    """events.json に神社系定例イベントを書き込む"""
    print(f"[{SOURCE}] expanding recurring jinja events...", file=sys.stderr)
    existing = load_existing()
    new_events = expand_events()
    print(f"[{SOURCE}] expanded {len(new_events)} occurrences", file=sys.stderr)

    # archive_missing=True で、ルールから外れた古いレコードはアーカイブ化
    merge_events(existing, new_events, source=SOURCE, archive_missing=True)
    save_events(existing)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--download-images", action="store_true",
                    help="（未使用、互換のため受取）")
    args = ap.parse_args()
    crawl()


if __name__ == "__main__":
    main()
