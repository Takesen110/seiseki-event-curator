#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrapers/seiseki_org.py
聖蹟桜ヶ丘エリアマネジメント公式サイト (seiseki.org) のスクレイパー。

source identifier: "seiseki.org"
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote

from bs4 import BeautifulSoup

# Allow running as either `python -m scrapers.seiseki_org` or
# `python scrapers/seiseki_org.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scrapers.common import (  # noqa: E402
    Event, KNOWN_TAGS, IMAGES_DIR, now_iso, parse_date_jp,
    make_session, fetch_html, load_existing, save_events, merge_events,
)

# ----------------------------------------------------------------------
SOURCE = "seiseki.org"
BASE_URL = "https://seiseki.org"
EVENT_LIST_URL = f"{BASE_URL}/event/"
MAX_PAGES = 15  # 念のための上限


# ----------------------------------------------------------------------
# 一覧ページパース
# ----------------------------------------------------------------------
def parse_event_list_page(html: str) -> list[dict]:
    """一覧ページから {url, title} を抽出"""
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []
    seen_urls: set[str] = set()

    for a in soup.select("a"):
        href = a.get("href", "")
        text = a.get_text(strip=True)
        if not href.startswith(BASE_URL):
            continue
        if "/event" in href or "/eventtag" in href or "/news" in href:
            continue
        if "/gallery" in href or "/about" in href or "/contact" in href:
            continue
        if "詳細を見る" not in text and "→" not in text:
            continue

        if href in seen_urls:
            continue
        seen_urls.add(href)

        full_text = a.get_text("\n", strip=True)
        lines = [l for l in full_text.split("\n") if l]
        title = lines[0] if lines else ""

        results.append({"url": href, "title": title})

    return results


def extract_pagination_max(html: str) -> int:
    """一覧の最大ページ数を抽出（取れなければ1）"""
    soup = BeautifulSoup(html, "html.parser")
    max_page = 1
    for a in soup.select("a"):
        href = a.get("href", "")
        m = re.search(r"/event/page/(\d+)/?", href)
        if m:
            n = int(m.group(1))
            if n > max_page:
                max_page = n
    return max_page


# ----------------------------------------------------------------------
# 詳細ページパース
# ----------------------------------------------------------------------
def slug_from_url(url: str) -> str:
    """URLからスラッグ（IDとして使う）を取り出す"""
    path = url.replace(BASE_URL, "").strip("/")
    return unquote(path)


def parse_dates_from_title(title: str) -> tuple[str | None, str | None]:
    """seiseki.org独自：キッチンカーカレンダー対応 + 通常の日付パース"""
    # キッチンカーカレンダーは月単位
    m = re.search(r"(\d{4})年(\d{1,2})月分", title)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        from calendar import monthrange
        last = monthrange(y, mo)[1]
        return (f"{y:04d}-{mo:02d}-01", f"{y:04d}-{mo:02d}-{last:02d}")
    # 通常の日付（共通関数）
    return parse_date_jp(title)


def parse_event_detail(url: str, html: str) -> Event:
    """詳細ページからEventを生成"""
    soup = BeautifulSoup(html, "html.parser")

    # タイトル
    title = ""
    for h in soup.select("h3"):
        t = h.get_text(strip=True)
        if t and "イベント" not in t:
            title = t
            break
    if not title:
        h1 = soup.select_one("h2, h1")
        if h1:
            title = h1.get_text(strip=True)

    # 画像
    image_url = None
    for img in soup.select("img"):
        src = img.get("src", "")
        if "/wp-content/uploads/" in src and "logo" not in src:
            image_url = src
            break

    # 本文クリーニング
    nav_words = {
        "私たちについて", "イベント", "お知らせ", "ギャラリー",
        "河川敷の利用について", "お問い合わせ", "View All",
        "詳細を見る", "プライバシーポリシー", "View More",
    }
    for tag_name in ("noscript", "script", "style", "header", "footer", "nav"):
        for el in soup.find_all(tag_name):
            el.decompose()

    paragraphs: list[str] = []
    for p in soup.select("p"):
        txt = p.get_text("\n", strip=True)
        if not txt:
            continue
        if any(w in txt for w in nav_words) and len(txt) < 30:
            continue
        if "JavaScript" in txt and len(txt) < 60:
            continue
        if re.fullmatch(r"\d{4}\.\d{2}\.\d{2}\s*", txt):
            continue
        if txt.strip() in ("開催中", "開催予定", "終了"):
            continue
        if txt.strip() in KNOWN_TAGS:
            continue
        paragraphs.append(txt)

    body = "\n\n".join(paragraphs).strip()

    # 日時 / 場所 / 主催の抽出（パターンA/B/C対応）
    venue, organizer, time_label = _extract_event_fields(body)

    # ステータス
    status = None
    page_text = soup.get_text("\n", strip=True)
    for s in ("開催中", "開催予定", "終了"):
        if s in page_text.split("\n"):
            status = s
            break

    # サイトタグ
    tags: list[str] = []
    for tag in KNOWN_TAGS:
        if tag in page_text:
            tags.append(tag)

    # 日付
    date_start, date_end = parse_dates_from_title(title)

    is_kitchen_car = "キッチンカー" in title

    iso = now_iso()
    return Event(
        id=slug_from_url(url),
        source=SOURCE,
        url=url,
        title=title,
        date_label=f"{date_start or ''}{(' 〜 ' + date_end) if date_end else ''}",
        date_start=date_start,
        date_end=date_end,
        status=status,
        tags=tags,
        image_url=image_url,
        body=body,
        venue=venue,
        organizer=organizer,
        time_label=time_label,
        is_kitchen_car=is_kitchen_car,
        first_seen=iso,
        last_seen=iso,
    )


def _extract_event_fields(body: str) -> tuple[str | None, str | None, str | None]:
    """本文から (venue, organizer, time_label) を抽出。
    A: コロン区切り、B: ラベル+次行値、C: 【主催】xxx / 【後援】yyy 形式
    """
    venue = None
    organizer = None
    time_label = None
    organizer_candidates: dict[str, str] = {}

    PREFIX_RE = r"^[\s｜■●○◆◇▼▲・\-\*\[【「]*"
    TIME_KEYS = ("日時", "開催日時", "開催日", "時間")
    VENUE_KEYS = ("場所", "会場", "開催場所")
    ORG_KEYS_PRIORITY = ("主催", "主催者", "共催", "後援", "特別協賛", "協賛", "協力")
    ORG_KEYS_MATCH = ("主催者", "特別協賛", "後援", "共催", "協賛", "協力", "主催")

    def _match_inline(line: str, keyword: str) -> str | None:
        m = re.match(PREFIX_RE + re.escape(keyword) + r"[\s】\]」]*[：:]\s*(.+)", line)
        return m.group(1).strip() if m else None

    def _is_label_only(line: str, keyword: str) -> bool:
        m = re.match(PREFIX_RE + re.escape(keyword) + r"[\s】\]」]*$",
                     line.rstrip("：:　 "))
        return bool(m)

    def _extract_bracket_items(line: str) -> list[tuple[str, str]]:
        items = []
        for m in re.finditer(r"[【\[]([^】\]]+)[】\]]\s*([^【\[/／]+)", line):
            key = m.group(1).strip()
            val = m.group(2).strip(" /／、,")
            if val:
                items.append((key, val))
        return items

    lines = [l.strip().replace("　", " ") for l in re.split(r"\n+", body) if l.strip()]

    for i, line in enumerate(lines):
        # (A) コロン区切り
        if time_label is None:
            for kw in TIME_KEYS:
                v = _match_inline(line, kw)
                if v:
                    time_label = v
                    break
        if venue is None:
            for kw in VENUE_KEYS:
                v = _match_inline(line, kw)
                if v:
                    venue = v
                    break
        for kw in ORG_KEYS_MATCH:
            v = _match_inline(line, kw)
            if v and kw not in organizer_candidates:
                organizer_candidates[kw] = v
                break

        # (B) ラベルだけの行 → 次の行を値として採用
        next_line = lines[i + 1] if i + 1 < len(lines) else ""
        if next_line and not any(
            re.match(PREFIX_RE + re.escape(k), next_line)
            for k in TIME_KEYS + VENUE_KEYS + ORG_KEYS_MATCH
        ):
            if time_label is None:
                for kw in TIME_KEYS:
                    if _is_label_only(line, kw):
                        time_label = next_line.lstrip("・* -")
                        break
            if venue is None:
                for kw in VENUE_KEYS:
                    if _is_label_only(line, kw):
                        venue = next_line.lstrip("・* -")
                        break
            for kw in ORG_KEYS_MATCH:
                if _is_label_only(line, kw) and kw not in organizer_candidates:
                    organizer_candidates[kw] = next_line.lstrip("・* -")
                    break

        # (C) ブラケット形式 【主催】xxx / 【後援】yyy
        for key, val in _extract_bracket_items(line):
            for kw in ORG_KEYS_MATCH:
                if key == kw and kw not in organizer_candidates:
                    organizer_candidates[kw] = val
                    break

    for kw in ORG_KEYS_PRIORITY:
        if kw in organizer_candidates:
            organizer = organizer_candidates[kw]
            if kw not in ("主催", "主催者"):
                organizer = f"[{kw}] {organizer}"
            break

    return venue, organizer, time_label


# ----------------------------------------------------------------------
# 画像ダウンロード
# ----------------------------------------------------------------------
def download_image(session, url: str, dest_dir: Path) -> str | None:
    if not url:
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    fname = unquote(url.split("/")[-1])
    fname = re.sub(r"[^\w.\-]", "_", fname)
    path = dest_dir / fname
    if path.exists():
        return str(path)
    print(f"  IMG {url}", file=sys.stderr)
    import time as _t
    r = session.get(url, timeout=30)
    if r.status_code == 200:
        path.write_bytes(r.content)
        _t.sleep(0.5)
        return str(path)
    return None


# ----------------------------------------------------------------------
# メインフロー
# ----------------------------------------------------------------------
def crawl(max_pages: int = MAX_PAGES, download_images: bool = False) -> None:
    session = make_session()
    existing = load_existing()

    print(f"[{SOURCE}] Fetching event list page 1...", file=sys.stderr)
    first_html = fetch_html(session, EVENT_LIST_URL)
    site_max = extract_pagination_max(first_html)
    pages_to_fetch = min(max_pages, site_max)
    print(f"[{SOURCE}] site has {site_max} pages, will fetch {pages_to_fetch}",
          file=sys.stderr)

    page_htmls = [first_html]
    for p in range(2, pages_to_fetch + 1):
        page_htmls.append(fetch_html(session, f"{BASE_URL}/event/page/{p}/"))

    candidates: list[dict] = []
    for html in page_htmls:
        candidates.extend(parse_event_list_page(html))

    seen_urls: set[str] = set()
    unique_candidates = []
    for c in candidates:
        if c["url"] in seen_urls:
            continue
        seen_urls.add(c["url"])
        unique_candidates.append(c)

    print(f"[{SOURCE}] found {len(unique_candidates)} unique event URLs",
          file=sys.stderr)

    new_events: list[Event] = []
    for i, c in enumerate(unique_candidates, 1):
        url = c["url"]
        try:
            print(f"[{SOURCE}] [{i}/{len(unique_candidates)}] parsing detail",
                  file=sys.stderr)
            detail_html = fetch_html(session, url)
            ev = parse_event_detail(url, detail_html)
        except Exception as e:
            print(f"  ! error: {e}", file=sys.stderr)
            continue

        if download_images and ev.image_url:
            local = download_image(session, ev.image_url, IMAGES_DIR)
            if local:
                ev.image_local = local

        new_events.append(ev)

    merge_events(existing, new_events, source=SOURCE, archive_missing=True)
    save_events(existing)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=MAX_PAGES,
                    help=f"取得するページ数（最大 {MAX_PAGES}）")
    ap.add_argument("--download-images", action="store_true",
                    help="チラシ画像をローカルにダウンロード")
    args = ap.parse_args()
    crawl(max_pages=args.pages, download_images=args.download_images)


if __name__ == "__main__":
    main()
