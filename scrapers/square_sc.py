#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrapers/square_sc.py
ザ・スクエア聖蹟桜ヶ丘 (square-sc.com) のスクレイパー。

source identifier: "square-sc.com"

特徴:
- WordPress製、UTF-8、JSなし
- 一覧URL: https://square-sc.com/ （ショップニュースがトップページに展開される）
- 個別記事URL: /shopnews/{slug}/
- 投稿日と開催期間が別。開催期間は本文中に書かれている（"4/1〜5/31までの限定" 等）
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
SOURCE = "square-sc.com"
BASE_URL = "https://square-sc.com"
TOP_URL = f"{BASE_URL}/"


# ----------------------------------------------------------------------
# 一覧ページ：ショップニュース記事URLを抽出
# ----------------------------------------------------------------------
def parse_top_page(html: str) -> list[dict]:
    """
    トップページ上の「ショップニュース」セクションから個別記事カードを抽出。

    各記事は <a href="/shopnews/{slug}/"> の中に画像とタイトル・概要が入っている。
    一覧上のテキスト：
      "2026年4月15日 2F 9ROUND ts-tan
       【4～5月限定】周年記念キャンペーン
       《4/1～5/31までの限定キャンペーン開催中》..."
    """
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []
    seen_slugs: set[str] = set()

    for a in soup.select("a"):
        href = a.get("href", "")
        if "/shopnews/" not in href:
            continue
        # スラッグ抽出
        m = re.search(r"/shopnews/([^/]+)/?$", href)
        if not m:
            continue
        slug = m.group(1)
        # 一覧トップへのリンク（"/shopnews/" だけ）はスキップ
        if not slug or slug == "shopnews":
            continue
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        full_url = href if href.startswith("http") else f"{BASE_URL}{href}"

        # アンカー内のテキストから情報を抽出
        full_text = a.get_text("\n", strip=True)
        lines = [l.strip() for l in full_text.split("\n") if l.strip()]

        post_date = ""
        floor_shop = ""
        title = ""
        summary = ""

        # パターン: 1行目に日付+フロア+ショップ+投稿者、2行目以降にタイトル＋概要
        # "2026年4月15日2F 9ROUNDts-tan" のように貼り付いている場合もある
        for ln in lines:
            m_date = re.match(r"^(\d{4})年(\d{1,2})月(\d{1,2})日(.*)", ln)
            if m_date and not post_date:
                y, mo, d = int(m_date.group(1)), int(m_date.group(2)), int(m_date.group(3))
                post_date = f"{y:04d}-{mo:02d}-{d:02d}"
                # 残り（"2F 9ROUNDts-tan"）はフロア+ショップ
                rest = m_date.group(4).strip()
                # 末尾の投稿者名（"ts-tan", "shino" など短い英数字+ハイフン）を取り除く
                rest = re.sub(r"[a-z][a-z0-9\-]+$", "", rest).strip()
                floor_shop = rest
                continue
            # 短いタイトル候補（### で始まる行 = h4 と見ているはず）
            if not title and len(ln) >= 3 and len(ln) < 80:
                title = ln
                continue
            # それ以降は概要
            if title and not summary:
                summary = ln[:200]

        # 画像
        img = a.find("img")
        image_url = None
        if img and img.get("src"):
            src = img["src"]
            image_url = src if src.startswith("http") else f"{BASE_URL}{src}"

        results.append({
            "slug": slug,
            "url": full_url,
            "post_date": post_date,
            "floor_shop": floor_shop,
            "title_hint": title,
            "summary_hint": summary,
            "image_url": image_url,
        })

    return results


# ----------------------------------------------------------------------
# 詳細ページパース
# ----------------------------------------------------------------------
def parse_event_detail(url: str, html: str, hints: dict) -> Event:
    soup = BeautifulSoup(html, "html.parser")

    # ナビ・フッター除去
    for tag_name in ("script", "style", "nav", "header", "footer"):
        for el in soup.find_all(tag_name):
            el.decompose()

    # タイトル：h1（記事タイトル）
    title = ""
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)
    if not title:
        title = hints.get("title_hint", "")

    # 画像：本文中の最初の wp-content/uploads
    image_url = hints.get("image_url")
    for img in soup.select("img"):
        src = img.get("src", "")
        if not src:
            continue
        if "/wp-content/uploads/" in src and "logo" not in src:
            image_url = src if src.startswith("http") else f"{BASE_URL}{src}"
            break

    # 投稿日
    post_date = hints.get("post_date", "")

    # 本文：記事本文を集める
    body_lines: list[str] = []
    main = soup.find("main") or soup.find("article") or soup
    for p in main.select("p, dd, li"):
        txt = p.get_text("\n", strip=True)
        if not txt or len(txt) < 5:
            continue
        if any(w in txt for w in (
            "Copyright", "サイトマップ", "Powered by",
            "営業時間", "B1F～2Fショッピングフロア",
            "次回休館日", "駐輪場", "スタッフ募集",
            "ファッション", "ライフ＆カルチャー",
        )):
            continue
        body_lines.append(txt)
    body = "\n\n".join(body_lines).strip()

    # 店舗名（dd dt 構造で「店舗名:」の値）
    venue = None
    shop_name = _extract_shop_name(soup)
    if shop_name:
        venue = shop_name
    elif hints.get("floor_shop"):
        venue = hints["floor_shop"]

    # イベント期間：本文から「M/D〜M/D」「M月D日〜M月D日」をパース
    # ただし投稿日とは違う「開催期間」を優先
    date_start, date_end = _extract_event_period(body, post_date)

    # ステータス
    status = infer_status_by_date(date_start, date_end)

    # カテゴリ：常にSC
    tags = ["ショッピングセンター"]

    iso = now_iso()
    return Event(
        id=f"sqsc-{hints['slug']}",
        source=SOURCE,
        url=url,
        title=title,
        date_label=hints.get("summary_hint", "")[:40],  # 概要の冒頭を一覧用に
        date_start=date_start,
        date_end=date_end,
        status=status,
        tags=tags,
        image_url=image_url,
        body=body,
        venue=venue,
        organizer="ザ・スクエア聖蹟桜ヶ丘",
        time_label=None,
        is_kitchen_car=False,
        first_seen=iso,
        last_seen=iso,
    )


def _extract_shop_name(soup) -> str | None:
    """詳細ページの「店舗名: ...」セクションから店名を取り出す"""
    for dt in soup.select("dt"):
        if "店舗名" in dt.get_text(strip=True):
            dd = dt.find_next_sibling("dd")
            if dd:
                return dd.get_text(strip=True)
    return None


def _extract_event_period(body: str, post_date: str) -> tuple[str | None, str | None]:
    """本文中からイベント期間を抽出。投稿日とは異なる「開催期間」を返す。

    パース戦略：
    1. 本文先頭から、開催期間を示すフレーズを探す
       - "《4/1〜5/31までの限定》"
       - "4/15〜5/12"
       - "5月7日（木）〜5月13日（水）"
    2. 投稿日と被っている場合は弾く（「2026年4月15日」のような掲載日表記）
    3. 何も取れなければ (None, None)

    開催期間と判定したいテキスト形式は parse_keio_date が拾えるパターン全般。
    投稿日の年と異なる年は、投稿日年を hint_year として補完する。
    """
    if not body:
        return (None, None)

    hint_year = int(post_date.split("-")[0]) if post_date else 2026

    # 本文の「開催期間っぽい」段落を抽出
    # 〈山括弧《》〉や ■ で始まる段落をブースト
    # 単純に最初に見つかった日付範囲を採用（実用上それで十分）
    for line in body.split("\n"):
        line = line.strip()
        # M/D〜M/D, M/D→M/D, M月D日〜M月D日 のいずれか
        if re.search(r"\d{1,2}[/月]\d{1,2}.*?(?:～|〜|~|→).*?\d{1,2}", line):
            start, end = parse_keio_date(line, hint_year)
            if start:
                return start, end

    # 範囲なし、単発のM月D日 / M/D
    for line in body.split("\n"):
        line = line.strip()
        if re.search(r"\d{1,2}[/月]\d{1,2}", line):
            start, end = parse_keio_date(line, hint_year)
            if start:
                return start, end

    return (None, None)


# ----------------------------------------------------------------------
# メインフロー
# ----------------------------------------------------------------------
def crawl(download_images: bool = False, **kwargs) -> None:
    session = make_session()
    existing = load_existing()

    print(f"[{SOURCE}] fetching top page (shop news section)...", file=sys.stderr)
    html = fetch_html(session, TOP_URL)
    cards = parse_top_page(html)
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
