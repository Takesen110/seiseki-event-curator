#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrapers/seiseki_tokyo.py
せいせき観光まちづくり会議 (seiseki.tokyo) のスクレイパー。
聖蹟桜ヶ丘の観光・聖地巡礼・地域文化系イベントを扱う。

source identifier: "seiseki.tokyo"

特徴:
- UTF-8、静的HTML
- アーカイブページ /machi_news_archive.php に全イベントが並ぶ
- 各記事のURLは /news/machi_newsNNN.html
- ### 開催概要 配下の <ul> に日時・会場・入場料が構造化されている
- 「終了しました」表示が一覧と詳細にある
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scrapers.common import (  # noqa: E402
    Event, now_iso, make_session, fetch_html,
    load_existing, save_events, merge_events,
    parse_date_jp, infer_status_by_date, download_image,
    IMAGES_DIR,
)

# ----------------------------------------------------------------------
SOURCE = "seiseki.tokyo"
BASE_URL = "https://seiseki.tokyo"
ARCHIVE_URL = f"{BASE_URL}/machi_news_archive.php"


# ----------------------------------------------------------------------
# 一覧ページ：イベント記事URLを抽出
# ----------------------------------------------------------------------
def parse_archive_page(html: str) -> list[dict]:
    """
    アーカイブページから各イベントのURL・タイトル・日付・画像・終了フラグを抽出。

    ページ構造（マークダウン化されたものから推測）:
      <li>
        <a href="/news/machi_newsNNN.html"><img src="..."></a>
        EVENTNEWS
        2026.05.01
        <h3><a href="/news/machi_newsNNN.html">タイトル</a></h3>
        概要文
        終了しました（あれば）
      </li>
    """
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []
    seen_ids: set[str] = set()

    # 各記事URLを軸に拾う
    for a in soup.select("a"):
        href = a.get("href", "")
        if "/news/machi_news" not in href:
            continue
        if not href.endswith(".html"):
            continue

        # ID抽出 (machi_news010.html → 010)
        m = re.search(r"machi_news(\d+)\.html", href)
        if not m:
            continue
        nid = m.group(1)
        if nid in seen_ids:
            continue
        seen_ids.add(nid)

        full_url = href if href.startswith("http") else f"{BASE_URL}{href}"

        # 一覧上の各カードは <li> ベースのはず。親リスト要素から情報を拾う
        parent = a.find_parent(["li", "article", "div"])
        meta = _extract_archive_card(parent) if parent else {}

        # 画像（このアンカー内に img があれば優先）
        image_url = None
        img = a.find("img")
        if img and img.get("src"):
            src = img["src"]
            image_url = src if src.startswith("http") else f"{BASE_URL}{src}"
        if not image_url:
            image_url = meta.get("image_url")

        # タイトル：a.get_text() がアイキャッチ画像のalt文字列のことが多いので、
        # 親内から h3 を探すのが優先。
        title = meta.get("title") or a.get_text(strip=True)

        results.append({
            "id": nid,
            "url": full_url,
            "title_hint": title,
            "image_url": image_url,
            "date_label_hint": meta.get("date_label", ""),
            "summary_hint": meta.get("summary", ""),
            "is_ended": meta.get("is_ended", False),
        })

    return results


def _extract_archive_card(parent) -> dict:
    """親要素の中から、日付・タイトル・概要・終了フラグ・画像を抽出"""
    out: dict = {"is_ended": False}

    # 全テキストから「YYYY.MM.DD」パターンを検出
    text = parent.get_text("\n", strip=True)

    m = re.search(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        out["date_label"] = f"{y:04d}-{mo:02d}-{d:02d}"

    if "終了しました" in text:
        out["is_ended"] = True

    # タイトル：h3 > a のテキスト
    h3 = parent.find(["h3", "h2", "h4"])
    if h3:
        a = h3.find("a")
        out["title"] = (a.get_text(strip=True) if a else h3.get_text(strip=True)).strip()

    # 概要：h3 の後に出てくる本文テキスト（短め）
    # h3 の次のテキスト的要素の最初の100文字くらいを採用
    if h3:
        for sib in h3.next_siblings:
            if hasattr(sib, "get_text"):
                t = sib.get_text(" ", strip=True)
                if t and t != "終了しました" and len(t) > 5:
                    out["summary"] = t[:200]
                    break

    # 画像
    img = parent.find("img")
    if img and img.get("src"):
        src = img["src"]
        out["image_url"] = src if src.startswith("http") else f"{BASE_URL}{src}"

    return out


# ----------------------------------------------------------------------
# 詳細ページパース
# ----------------------------------------------------------------------
def parse_event_detail(url: str, html: str, hints: dict) -> Event:
    soup = BeautifulSoup(html, "html.parser")

    # ナビ・フッター除去
    for tag_name in ("script", "style", "nav", "header", "footer"):
        for el in soup.find_all(tag_name):
            el.decompose()

    # タイトル：h1 / h2 が記事タイトル
    title = ""
    h = soup.find(["h1", "h2"])
    if h:
        title = h.get_text(strip=True)
    if not title:
        # <title>タグから「| サイト名」を取り除く
        title_tag = soup.find("title")
        if title_tag:
            t = title_tag.get_text(strip=True)
            title = re.split(r"\s*\|\s*", t)[0].strip()
    if not title:
        title = hints.get("title_hint", "")

    # 画像：本文中の画像を優先、なければ一覧ヒント
    image_url = hints.get("image_url")
    for img in soup.select("img"):
        src = img.get("src", "")
        if not src:
            continue
        if "logo" in src or "common" in src:
            continue
        if "/news/" in src:
            image_url = src if src.startswith("http") else f"{BASE_URL}{src}"
            break

    # 「### 開催概要」セクション配下の <ul><li> を抽出
    overview = _extract_overview_list(soup)
    time_label = overview.get("日時") or overview.get("開催日") or overview.get("開催日時")
    venue = overview.get("会場") or overview.get("場所")
    fee = overview.get("入場") or overview.get("参加費") or overview.get("料金")

    # 出演者・主催情報：### 出演 や ### 主催 セクションがあれば拾う
    organizer = _extract_section_text(soup, ("主催", "主催者")) or "せいせき観光まちづくり会議"

    # 本文：h1/h2 以降の主要テキスト
    body_lines: list[str] = []
    for p in soup.select("p, li"):
        txt = p.get_text("\n", strip=True)
        if not txt or len(txt) < 5:
            continue
        if any(w in txt for w in (
            "TOPへ戻る", "ニュース一覧に戻る", "(C) せいせき観光まちづくり会議",
            "無断転載", "プライバシーポリシー", "せいせき観光まちづくり会議",
        )):
            continue
        body_lines.append(txt)
    body = "\n\n".join(body_lines).strip()

    # 日付パース：time_label を最優先、次に body、最後に一覧の掲載日
    date_text = time_label or ""
    date_start, date_end = parse_date_jp(date_text)
    if not date_start and body:
        date_start, date_end = parse_date_jp(body)

    # ステータス：一覧で「終了しました」フラグがある or 日付ベースで判定
    if hints.get("is_ended"):
        status = "終了"
    else:
        status = infer_status_by_date(date_start, date_end)
        # 日付が取れずヒントもないなら、status は None のまま

    # カテゴリ判定：基本「まちなか」、本文に SC や カワマチ言及があれば併記
    tags = _infer_tags(title, body, venue)

    iso = now_iso()
    return Event(
        id=f"seitokyo-{_id_from_url(url)}",
        source=SOURCE,
        url=url,
        title=title,
        date_label=time_label or hints.get("date_label_hint", ""),
        date_start=date_start,
        date_end=date_end,
        status=status,
        tags=tags,
        image_url=image_url,
        body=body,
        venue=venue,
        organizer=organizer,
        time_label=time_label,
        is_kitchen_car=False,
        first_seen=iso,
        last_seen=iso,
    )


def _id_from_url(url: str) -> str:
    """URLからID（machi_newsNNN.html → NNN）を取り出す"""
    m = re.search(r"machi_news(\d+)\.html", url)
    return m.group(1) if m else "unknown"


def _extract_overview_list(soup) -> dict[str, str]:
    """「### 開催概要」直下の <ul><li> を辞書化。

    例:
      <h3>開催概要</h3>
      <ul>
        <li>日時：2026年2月15日（日）開場 13:30 ／ 開演 14:00</li>
        <li>会場：多摩市立関戸公民館 8階 ヴィータホール</li>
        <li>入場：無料（事前申込制・抽選）／定員200名</li>
      </ul>
    """
    pairs: dict[str, str] = {}
    # 開催概要セクションを探す
    target_h = None
    for h in soup.select("h2, h3, h4"):
        ht = h.get_text(strip=True)
        if "開催概要" in ht or "概要" == ht:
            target_h = h
            break

    if target_h:
        # h見出しの次の ul を探す
        ul = target_h.find_next_sibling()
        while ul and (not hasattr(ul, "name") or ul.name not in ("ul", "ol")):
            ul = ul.find_next_sibling()
            if ul is None or (hasattr(ul, "name") and ul.name in ("h2", "h3", "h4")):
                break
        if ul and ul.name in ("ul", "ol"):
            for li in ul.find_all("li", recursive=False):
                txt = li.get_text("\n", strip=True)
                # "日時：2026年..." → key="日時", value="2026年..."
                m = re.match(r"^([^：:\n]{1,20})[：:]\s*(.+)", txt, flags=re.S)
                if m:
                    key = m.group(1).strip()
                    val = m.group(2).strip()
                    if key not in pairs:
                        pairs[key] = val
    # フォールバック：ページ全体から「日時：」「会場：」を探す（ul外でも書かれる場合）
    if not pairs:
        for li in soup.select("li, p"):
            txt = li.get_text("\n", strip=True)
            for kw in ("日時", "会場", "場所", "入場", "参加費"):
                m = re.match(rf"^{kw}\s*[：:]\s*(.+)", txt, flags=re.S)
                if m and kw not in pairs:
                    pairs[kw] = m.group(1).strip().split("\n")[0].strip()
                    break
    return pairs


def _extract_section_text(soup, keywords: tuple[str, ...]) -> str | None:
    """指定キーワードを含む見出しの直下のテキスト塊を返す"""
    for h in soup.select("h2, h3, h4"):
        ht = h.get_text(strip=True)
        if any(kw in ht for kw in keywords):
            # 次の見出しまでのテキストを集める
            collected: list[str] = []
            for sib in h.next_siblings:
                if hasattr(sib, "name") and sib.name in ("h2", "h3", "h4"):
                    break
                if hasattr(sib, "get_text"):
                    t = sib.get_text(" ", strip=True)
                    if t:
                        collected.append(t)
            return " ".join(collected).strip() or None
    return None


# 場所カテゴリ推定のキーワード（seiseki_s.py と同じロジックを共有してもよいが、
# サイトごとに微調整する余地を残すため個別定義）
SC_KEYWORDS = (
    "京王聖蹟桜ヶ丘ショッピングセンター", "京王SC", "京王S.C", "京王プラザ",
    "ヴィータモール", "VITA MALL", "京王百貨店",
    "オーパ", "OPA",
)
KAWAMACHI_KEYWORDS = (
    "せいせきカワマチ", "カワマチ", "多摩川河川敷", "一ノ宮公園",
)


def _infer_tags(title: str, body: str, venue: str | None) -> list[str]:
    """seiseki.tokyo は基本まちなか系。SCやカワマチ言及があれば併記。"""
    text = f"{title}\n{body}\n{venue or ''}"
    tags: list[str] = ["まちなか"]  # デフォルト
    if any(k in text for k in KAWAMACHI_KEYWORDS):
        tags.append("せいせきカワマチ")
    if any(k in text for k in SC_KEYWORDS):
        tags.append("ショッピングセンター")
    return tags


# ----------------------------------------------------------------------
# メインフロー
# ----------------------------------------------------------------------
def crawl(download_images: bool = False, **kwargs) -> None:
    session = make_session()
    existing = load_existing()

    print(f"[{SOURCE}] fetching news archive...", file=sys.stderr)
    archive_html = fetch_html(session, ARCHIVE_URL)
    cards = parse_archive_page(archive_html)
    print(f"[{SOURCE}] found {len(cards)} cards", file=sys.stderr)

    new_events: list[Event] = []
    for i, c in enumerate(cards, 1):
        try:
            print(f"[{SOURCE}] [{i}/{len(cards)}] {c['url']}", file=sys.stderr)
            html = fetch_html(session, c["url"])
            ev = parse_event_detail(c["url"], html, hints=c)
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
