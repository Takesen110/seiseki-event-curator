#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_all.py
全ソースのスクレイパーを順次実行する司令塔。

Usage:
    python run_all.py                    # 全ソース取得（画像なし）
    python run_all.py --download-images  # 画像も保存
    python run_all.py --sources seiseki.org  # 特定ソースだけ
    python run_all.py --reclassify       # スクレイピングせずカテゴリ等を再計算
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scrapers.common import (
    load_existing, save_events, enrich_event, Event,
    EVENTS_JSON,
)
from scrapers import (
    seiseki_org, keio_sc, keionet,
    seiseki_s, seiseki_tokyo,
    square_sc, vitamall, tamapon,
    jinja_recurring,
)


# 利用可能なソース → (モジュール, 表示名) のマップ
SOURCES = {
    "seiseki.org":              (seiseki_org, "聖蹟桜ヶ丘エリアマネジメント公式"),
    "keio-sc.jp":               (keio_sc, "京王聖蹟桜ヶ丘ショッピングセンター"),
    "keionet.com":              (keionet, "京王百貨店 聖蹟桜ヶ丘店"),
    "seiseki-s.com":            (seiseki_s, "聖蹟桜ヶ丘ショップドットコム（商店会）"),
    "seiseki.tokyo":            (seiseki_tokyo, "せいせき観光まちづくり会議"),
    "square-sc.com":            (square_sc, "ザ・スクエア聖蹟桜ヶ丘"),
    "vitamallseiseki.jp":       (vitamall, "ヴィータモールせいせき"),
    "tamapon.com":              (tamapon, "多摩ポン（聖蹟桜ヶ丘エリア絞込）"),
    "jinja-recurring.local":    (jinja_recurring, "聖蹟桜ヶ丘エリアの神社（年中行事）"),
}


def reclassify_only() -> None:
    """既存JSONを読んで category_primary / genres / hashtags を再計算"""
    if not EVENTS_JSON.exists():
        print(f"events.json が見つかりません: {EVENTS_JSON}", file=sys.stderr)
        sys.exit(1)
    existing = load_existing()
    for key, e in existing.items():
        # dict から Event を復元して enrich → dict に戻す
        ev = Event(
            id=e["id"], source=e.get("source", "seiseki.org"),
            url=e.get("url", ""), title=e.get("title", ""),
            date_label=e.get("date_label", ""),
            date_start=e.get("date_start"), date_end=e.get("date_end"),
            status=e.get("status"),
            tags=e.get("tags", []) or [],
            image_url=e.get("image_url"),
            image_local=e.get("image_local"),
            body=e.get("body", ""),
            venue=e.get("venue"),
            organizer=e.get("organizer"),
            time_label=e.get("time_label"),
            is_kitchen_car=bool(e.get("is_kitchen_car")),
            first_seen=e.get("first_seen", ""),
            last_seen=e.get("last_seen", ""),
            archived=bool(e.get("archived")),
        )
        ev = enrich_event(ev)
        # 元辞書に上書き（archived等は保持される）
        for k, v in asdict(ev).items():
            e[k] = v
    save_events(existing)
    print(f"reclassified {len(existing)} events", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", nargs="*",
                    help=f"対象ソース（省略時は全部）。利用可: {list(SOURCES.keys())}")
    ap.add_argument("--pages", type=int, default=15,
                    help="seiseki.org: ソース内の最大ページ数")
    ap.add_argument("--months-span", type=int, default=1,
                    help="keio-sc.jp: 現在月から前後N ヶ月をスキャン（デフォルト1）")
    ap.add_argument("--download-images", action="store_true",
                    help="画像をローカルダウンロード")
    ap.add_argument("--reclassify", action="store_true",
                    help="スクレイピングせず分類のみ再計算")
    args = ap.parse_args()

    if args.reclassify:
        reclassify_only()
        return

    targets = args.sources or list(SOURCES.keys())
    for src in targets:
        if src not in SOURCES:
            print(f"unknown source: {src}", file=sys.stderr)
            continue
        mod, label = SOURCES[src]
        print(f"\n========== {src} ({label}) ==========", file=sys.stderr)
        # crawl() のシグネチャはソースごとに違う。kwargs で渡せるものだけ渡す。
        kwargs: dict = {}
        if src == "seiseki.org":
            kwargs = {"max_pages": args.pages or 15,
                      "download_images": args.download_images}
        elif src == "keio-sc.jp":
            kwargs = {"months_span": args.months_span,
                      "download_images": args.download_images}
        elif src == "keionet.com":
            kwargs = {"download_images": args.download_images}
        elif src == "seiseki-s.com":
            kwargs = {"download_images": args.download_images}
        elif src == "seiseki.tokyo":
            kwargs = {"download_images": args.download_images}
        elif src == "square-sc.com":
            kwargs = {"download_images": args.download_images}
        elif src == "vitamallseiseki.jp":
            kwargs = {"download_images": args.download_images}
        elif src == "tamapon.com":
            kwargs = {"download_images": args.download_images,
                      "max_pages": 5}
        elif src == "jinja-recurring.local":
            kwargs = {}  # 神社系はスクレイピング不要なので画像DLも不要
        else:
            kwargs = {"download_images": args.download_images}
        try:
            mod.crawl(**kwargs)
        except Exception as e:
            print(f"  !! {src} failed: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
