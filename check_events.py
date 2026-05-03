#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
events.json の中身をチェックするユーティリティ。
PowerShellで `python check_events.py` のように呼び出す。

オプション:
  --upcoming     開催予定のみ
  --kawamachi    せいせきカワマチタグ付きのみ
  --kitchencar   キッチンカーカレンダーのみ
  --missing      venue/organizer/time_label のいずれかが欠損しているもの
  --category X   プライマリカテゴリで絞る（カワマチ/まちなか/SC/その他）
  --genre X      ジャンルIDで絞る（kitchen_car/family/pet/market/...）
  --hashtags     ハッシュタグも表示
"""
import argparse
import json
import sys
from pathlib import Path


CATEGORY_ALIASES = {
    "カワマチ": "せいせきカワマチ",
    "kawamachi": "せいせきカワマチ",
    "SC": "ショッピングセンター",
    "sc": "ショッピングセンター",
    "まちなか": "まちなか",
    "machinaka": "まちなか",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--upcoming", action="store_true")
    ap.add_argument("--kawamachi", action="store_true")
    ap.add_argument("--kitchencar", action="store_true")
    ap.add_argument("--missing", action="store_true")
    ap.add_argument("--category", type=str, default=None,
                    help="プライマリ場所カテゴリで絞る（カワマチ/SC/まちなか/その他）")
    ap.add_argument("--genre", type=str, default=None,
                    help="ジャンルIDで絞る（kitchen_car/family/pet/market/culture/beer/...）")
    ap.add_argument("--source", type=str, default=None,
                    help="データソースで絞る（seiseki.org / keio-sc.jp / seiseki-s.com / ...）")
    ap.add_argument("--hashtags", action="store_true",
                    help="ハッシュタグも表示")
    ap.add_argument("--limit", type=int, default=0,
                    help="表示件数（0で全件）")
    args = ap.parse_args()

    path = Path(__file__).parent / "data" / "events.json"
    if not path.exists():
        print(f"data/events.json が見つかりません。先に scraper を実行してください。",
              file=sys.stderr)
        sys.exit(1)

    with path.open(encoding="utf-8") as f:
        events = json.load(f)

    items = events
    if args.upcoming:
        items = [e for e in items if e.get("status") == "開催予定"]
    if args.kawamachi:
        items = [e for e in items if "せいせきカワマチ" in e.get("tags", [])]
    if args.kitchencar:
        items = [e for e in items if e.get("is_kitchen_car")]
    if args.category:
        cat = CATEGORY_ALIASES.get(args.category, args.category)
        items = [e for e in items if e.get("category_primary") == cat]
    if args.genre:
        items = [e for e in items if args.genre in e.get("genres", [])]
    if args.source:
        items = [e for e in items if e.get("source") == args.source]
    if args.missing:
        items = [e for e in items
                 if not e.get("venue") or not e.get("organizer") or not e.get("time_label")]

    print(f"# 全 {len(events)} 件中、条件に合致 {len(items)} 件\n")

    if args.limit > 0:
        items = items[:args.limit]

    for e in items:
        print(f"--- {e['title']}")
        print(f"  source  : {e.get('source', '-')}")
        print(f"  date    : {e.get('date_start')} 〜 {e.get('date_end') or '-'}")
        print(f"  status  : {e.get('status')}")
        print(f"  category: {e.get('category_primary')}  (tags: {' / '.join(e.get('tags', []))})")
        print(f"  genres  : {', '.join(e.get('genres', [])) or '-'}")
        print(f"  time    : {e.get('time_label') or '(取得できず)'}")
        print(f"  venue   : {e.get('venue') or '(取得できず)'}")
        print(f"  org     : {e.get('organizer') or '(取得できず)'}")
        if args.hashtags:
            print(f"  tags    : {' '.join(e.get('hashtags', []))}")
        print(f"  url     : {e.get('url')}")
        print()


if __name__ == "__main__":
    main()
