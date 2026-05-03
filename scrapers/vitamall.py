#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrapers/vitamall.py
ヴィータモールせいせき (vitamallseiseki.jp) のスクレイパー。

source identifier: "vitamallseiseki.jp"

特徴:
- WordPress製、UTF-8、JSなし
- 一覧URL: /news_event/
- 個別記事URL: /news_event/{slug}/
- 詳細ページに "2026.05.10〜2026.05.10" 形式の明示的な範囲がある
- カテゴリは「ショッピングセンター」固定
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scrapers.common import (  # noqa: E402
    Event, now_iso, make_session, fetch_html,
    load_existing, save_events, merge_events,
    parse_keio_date, infer_status_by_date, download_image,
    IMAGES_DIR,
)

# ----------------------------------------------------------------------
SOURCE = "vitamallseiseki.jp"
BASE_URL = "https://vitamallseiseki.jp"
NEWS_EVENT_URL = f"{BASE_URL}/news_event/"


# ----------------------------------------------------------------------
# 一覧ページ：個別記事URLを抽出
# ----------------------------------------------------------------------
def parse_news_event_page(html: str) -> list[dict]:
    """
    /news_event/ から個別記事カードを抽出。

    各カードは <a href="/news_event/{slug}/"> で、内部に
    <img> + 投稿日（YYYY.MM.DD）+ タイトルが入っている。
    投稿日がないカード（タイトルだけ）も存在する。
    """
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []
    seen_slugs: set[str] = set()

    for a in soup.select("a"):
        href = a.get("href", "")
        if "/news_event/" not in href:
            continue
        # 一覧トップURLそのものはスキップ
        m = re.search(r"/news_event/([^/]+)/?$", href)
        if not m:
            continue
        slug = m.group(1)
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        full_url = href if href.startswith("http") else f"{BASE_URL}{href}"

        # アンカー内のテキストから情報を抽出
        full_text = a.get_text("\n", strip=True)
        lines = [l.strip() for l in full_text.split("\n") if l.strip()]

        post_date = ""
        title = ""
        for ln in lines:
            # YYYY.MM.DD パターン
            m_d = re.match(r"^(\d{4})\.(\d{1,2})\.(\d{1,2})$", ln)
            if m_d and not post_date:
                y, mo, d = int(m_d.group(1)), int(m_d.group(2)), int(m_d.group(3))
                post_date = f"{y:04d}-{mo:02d}-{d:02d}"
                continue
            # それ以外である程度の長さを持つ行 → タイトル
            if not title and len(ln) > 3:
                title = ln

        # 画像
        img = a.find("img")
        image_url = None
        if img and img.get("src"):
            src = img["src"]
            image_url = src if src.startswith("http") else f"{BASE_URL}{src}"

        if not title:
            continue

        results.append({
            "slug": slug,
            "url": full_url,
            "post_date": post_date,
            "title_hint": title,
            "image_url": image_url,
        })

    return results


# ----------------------------------------------------------------------
# 詳細ページパース
# ----------------------------------------------------------------------
# 詳細ページには「2026.05.10〜2026.05.10」形式の明示的なイベント期間がある。
# それを最優先で拾う。
EVENT_PERIOD_RE = re.compile(
    r"(\d{4})\.(\d{1,2})\.(\d{1,2})\s*[〜～~\-]\s*(\d{4})\.(\d{1,2})\.(\d{1,2})"
)


def parse_event_detail(url: str, html: str, hints: dict) -> Event:
    soup = BeautifulSoup(html, "html.parser")

    # ナビ・フッター除去
    for tag_name in ("script", "style", "nav", "header", "footer"):
        for el in soup.find_all(tag_name):
            el.decompose()

    # タイトル：h1
    title = ""
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)
    if not title:
        title = hints.get("title_hint", "")

    # 画像：本文中の wp-content/uploads
    image_url = hints.get("image_url")
    for img in soup.select("img"):
        src = img.get("src", "")
        if not src:
            continue
        if "/wp-content/uploads/" in src and "logo" not in src and "header" not in src:
            image_url = src if src.startswith("http") else f"{BASE_URL}{src}"
            break

    # 本文：記事本文を集める
    body_lines: list[str] = []
    main = soup.find("main") or soup.find("article") or soup
    for p in main.select("p, dd, li, h2, h3"):
        txt = p.get_text("\n", strip=True)
        if not txt or len(txt) < 5:
            continue
        if any(w in txt for w in (
            "Copyright", "サイトマップ", "vita mall seiseki",
            "東京都多摩市関戸4丁目72番地", "営業時間", "お問い合わせ",
            "個人情報保護方針", "ACCESS", "アクセス",
        )):
            continue
        body_lines.append(txt)
    body = "\n\n".join(body_lines).strip()

    # 日付：詳細ページの "2026.05.10〜2026.05.10" 形式を最優先
    date_start, date_end = None, None
    full_text = soup.get_text("\n")
    m = EVENT_PERIOD_RE.search(full_text)
    if m:
        y1, mo1, d1 = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y2, mo2, d2 = int(m.group(4)), int(m.group(5)), int(m.group(6))
        date_start = f"{y1:04d}-{mo1:02d}-{d1:02d}"
        date_end = f"{y2:04d}-{mo2:02d}-{d2:02d}"
        if date_start == date_end:
            date_end = None

    # 上記でも取れなかったら、本文から M/D〜M/D 等を試す
    if not date_start:
        post_date = hints.get("post_date", "")
        hint_year = int(post_date.split("-")[0]) if post_date else 2026
        for line in body.split("\n"):
            if re.search(r"\d{1,2}[/月]\d{1,2}.*?(?:～|〜|~|→|-)", line):
                date_start, date_end = parse_keio_date(line, hint_year)
                if date_start:
                    break

    # 「休診日のお知らせ」などはイベントというよりお知らせなので、
    # status=None のままでよい（curator UIの「開催予定/開催中」フィルタで非表示になる）
    status = infer_status_by_date(date_start, date_end)

    # カテゴリ
    tags = ["ショッピングセンター"]

    # 場所：本文中の「実施場所」「場所」「会場」を拾う
    venue = _extract_venue(body)

    iso = now_iso()
    return Event(
        id=f"vita-{hints['slug']}",
        source=SOURCE,
        url=url,
        title=title,
        date_label="",
        date_start=date_start,
        date_end=date_end,
        status=status,
        tags=tags,
        image_url=image_url,
        body=body,
        venue=venue,
        organizer="ヴィータモールせいせき",
        time_label=None,
        is_kitchen_car=False,
        first_seen=iso,
        last_seen=iso,
    )


def _extract_venue(body: str) -> str | None:
    """本文から「実施場所:」「場所:」「会場:」の値を取り出す。

    パターン:
    - 同一行: "実施場所: 1F 特設会場"
    - 次行  : "■ 実施場所" → 次の行に "1F スターバックス横 特設会場"
    """
    lines = body.split("\n")
    label_re = re.compile(r"^\s*[■●]?\s*(?:実施場所|場所|会場)\s*[:：]?\s*(.*)$")
    for i, line in enumerate(lines):
        m = label_re.match(line)
        if not m:
            continue
        # 同一行に値があるか
        v = m.group(1).strip()
        if v and len(v) < 100:
            return v
        # 次の非空行を値として採用
        for j in range(i + 1, min(i + 4, len(lines))):
            nxt = lines[j].strip()
            if not nxt:
                continue
            # 別ラベル行ならスキップ
            if label_re.match(nxt) or re.match(r"^\s*[■●]\s*(?:参加条件|実施日時|お問い|備考|料金|応募|定員)", nxt):
                break
            if len(nxt) < 100:
                return nxt
            break
    return None


# ----------------------------------------------------------------------
# メインフロー
# ----------------------------------------------------------------------
def crawl(download_images: bool = False, **kwargs) -> None:
    session = make_session()
    existing = load_existing()

    print(f"[{SOURCE}] fetching news/event list...", file=sys.stderr)
    html = fetch_html(session, NEWS_EVENT_URL)
    cards = parse_news_event_page(html)
    print(f"[{SOURCE}] found {len(cards)} cards", file=sys.stderr)

    new_events: list[Event] = []
    for i, c in enumerate(cards, 1):
        try:
            print(f"[{SOURCE}] [{i}/{len(cards)}] {c['url']}", file=sys.stderr)
            detail_html = fetch_html(session, c["url"])
            ev = parse_event_detail(c["url"], detail_html, hints=c)
        except Exception as e:
            print(f"  ! error: {e}", file=sys.stderr)
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
