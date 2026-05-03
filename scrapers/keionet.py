#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrapers/keionet.py
京王百貨店 聖蹟桜ヶ丘店 (keionet.com) のスクレイパー。

source identifier: "keionet.com"

- 一覧ページ /info/seisekisakuragaoka/topics/ から各カードを抽出
- 各カードは画像 + 短いタイトル + 日付ラベルを含む
- 個別記事には行かず、一覧の情報だけで Event を作る
  （タイトル・画像・日付があれば SNS 投稿の素材として十分）
- カテゴリは「ショッピングセンター」固定
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scrapers.common import (  # noqa: E402
    Event, now_iso, make_session, fetch_html,
    load_existing, save_events, merge_events,
    parse_keio_date, infer_status_by_date, download_image,
    IMAGES_DIR,
)

# ----------------------------------------------------------------------
SOURCE = "keionet.com"
BASE_URL = "https://www.keionet.com"
TOPICS_URL = f"{BASE_URL}/info/seisekisakuragaoka/topics/"
HOME_URL = f"{BASE_URL}/info/seisekisakuragaoka/"


# 日付として確実に取れる正規表現（月日を含むもの）
HARD_DATE_RE = re.compile(
    r"\d{1,2}月\d{1,2}日|"     # 5月10日
    r"\d{1,2}/\d{1,2}|"        # 5/10
    r"\d{4}年\d{1,2}月\d{1,2}日"  # 2026年5月10日
)
# 日付ラベルとして許容するソフトな表現（月日がなくても拾う）
SOFT_DATE_RE = re.compile(r"^(?:毎月|毎週|実施中)")


def parse_topics_page(html: str) -> list[dict]:
    """
    トピックス一覧から各イベントカードを抽出。

    各カードは <a href="/info/seisekisakuragaoka/topics/NNNNNN.html"> で始まり、
    内部に <img src="..."> と短いテキストが含まれる。
    テキストは複数行に分かれており、月日を含む行が日付ラベル、それ以外がタイトル。
    """
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []
    seen_urls: set[str] = set()

    for a in soup.select("a"):
        href = a.get("href", "")
        if "/info/seisekisakuragaoka/topics/" not in href:
            continue
        if not href.endswith(".html"):
            continue
        m = re.search(r"/topics/(\d{6})\.html", href)
        if not m:
            continue
        topic_id = m.group(1)

        full_url = href if href.startswith("http") else (
            f"{BASE_URL}{href}" if href.startswith("/")
            else f"{BASE_URL}/info/seisekisakuragaoka/topics/{topic_id}.html"
        )
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        # 画像
        img = a.find("img")
        image_url = None
        if img:
            src = img.get("src", "")
            if src:
                image_url = src if src.startswith("http") else (
                    f"{BASE_URL}{src}" if src.startswith("/") else None
                )

        # テキストを行ごとに見る
        full_text = a.get_text("\n", strip=True)
        lines = [l.strip() for l in full_text.split("\n") if l.strip()]

        # 1パス目：HARD_DATE（月日を含む行）を最優先で日付候補に
        date_label = ""
        title_lines: list[str] = []
        for ln in lines:
            if not date_label and HARD_DATE_RE.search(ln):
                date_label = ln
            else:
                title_lines.append(ln)

        # 2パス目：HARD_DATEがなければSOFT_DATE（毎月開催など）を拾う
        if not date_label:
            remaining: list[str] = []
            for ln in title_lines:
                if not date_label and SOFT_DATE_RE.search(ln):
                    date_label = ln
                else:
                    remaining.append(ln)
            title_lines = remaining

        title = " ".join(title_lines).strip()
        if len(title) < 3:
            continue

        results.append({
            "id": topic_id,
            "url": full_url,
            "title": title,
            "date_label": date_label,
            "image_url": image_url,
        })

    return results


def build_event(card: dict, hint_year: int) -> Event:
    """一覧で取れた情報からEventオブジェクトを作る"""
    title = card["title"]
    url = card["url"]
    date_label = card.get("date_label", "")
    image_url = card.get("image_url")

    date_start, date_end = parse_keio_date(date_label, hint_year)
    status = infer_status_by_date(date_start, date_end)

    # ステータスが取れない（日付なし or 「毎月開催」「実施中」等）は None のまま
    # → status=None のレコードは UI で「未取得」扱いになる

    iso = now_iso()
    return Event(
        id=f"keionet-{card['id']}",
        source=SOURCE,
        url=url,
        title=title,
        date_label=date_label,
        date_start=date_start,
        date_end=date_end,
        status=status,
        tags=["ショッピングセンター"],
        image_url=image_url,
        body="",  # 詳細ページに行かないので空。タイトルだけ持つ
        venue=None,
        organizer="京王百貨店 聖蹟桜ヶ丘店",
        time_label=None,
        is_kitchen_car=False,
        first_seen=iso,
        last_seen=iso,
    )


def crawl(download_images: bool = False, **kwargs) -> None:
    """
    keionet.com から聖蹟桜ヶ丘店のトピックス一覧を取得。

    一覧ページ1枚で足りるので、ページネーションはなし。
    archive_missing=False（範囲外と判別できないので、消えたら自動アーカイブにはしない）
    """
    session = make_session()
    existing = load_existing()

    print(f"[{SOURCE}] fetching topics list...", file=sys.stderr)
    html = fetch_html(session, TOPICS_URL)
    cards = parse_topics_page(html)
    print(f"[{SOURCE}] found {len(cards)} cards", file=sys.stderr)

    hint_year = date.today().year
    new_events: list[Event] = []
    for card in cards:
        try:
            ev = build_event(card, hint_year)
        except Exception as e:
            print(f"  ! error building event: {e}", file=sys.stderr)
            continue

        if download_images and ev.image_url:
            local = download_image(session, ev.image_url, IMAGES_DIR)
            if local:
                ev.image_local = local

        new_events.append(ev)

    merge_events(existing, new_events, source=SOURCE, archive_missing=False)
    save_events(existing)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--download-images", action="store_true",
                    help="画像をローカルダウンロード")
    args = ap.parse_args()
    crawl(download_images=args.download_images)


if __name__ == "__main__":
    main()
