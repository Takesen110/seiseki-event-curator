#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrapers/seiseki_s.py
聖蹟桜ヶ丘ショップドットコム (seiseki-s.com) のスクレイパー。
聖蹟桜ヶ丘商店会連合会の運営する公式サイト。

source identifier: "seiseki-s.com"

特徴:
- 文字コードは Shift_JIS（HTMLのmeta指定）
- イベント一覧：/htm/ssr/evt_list.htm
- 詳細ページ：/htm/ssr/evt_detail.asp?n=NNN
- 商店街の地域イベント（桜まつり等）と SCイベントが混在
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scrapers.common import (  # noqa: E402
    Event, now_iso, make_session, fetch_html,
    load_existing, save_events, merge_events,
    parse_date_jp, infer_status_by_date, download_image,
    IMAGES_DIR,
)

# ----------------------------------------------------------------------
SOURCE = "seiseki-s.com"
BASE_URL = "https://seiseki-s.com"
EVENT_LIST_URL = f"{BASE_URL}/htm/ssr/evt_list.htm"
ENCODING = "shift_jis"


# ----------------------------------------------------------------------
# 一覧ページ：詳細URLとタイトル/日付ヒントを取得
# ----------------------------------------------------------------------
def parse_event_list_page(html: str) -> list[dict]:
    """
    一覧ページ形式：
      <dl>
        <dt>26/03/30掲載
            <a href="/htm/ssr/evt_detail.asp?n=202">第45回せいせき桜まつり</a>
            日時：4月5日（日）...</dt>
        <dd>概要：...</dd>
      </dl>
    """
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []
    seen_ids: set[str] = set()

    # 詳細ページへのリンクを起点に拾う
    for a in soup.select("a"):
        href = a.get("href", "")
        if "evt_detail.asp" not in href:
            continue
        # 相対URLをフルURL化
        # 想定パターン:
        #   "evt_detail.asp?n=202"        （同階層相対）
        #   "/htm/ssr/evt_detail.asp?n=202"  （ルート相対）
        #   "https://seiseki-s.com/..."   （絶対）
        if href.startswith("http"):
            full_url = href
        elif href.startswith("/"):
            full_url = f"{BASE_URL}{href}"
        else:
            # 同階層の相対パス → 一覧URLが /htm/ssr/ にあるので、そこからの相対
            full_url = f"{BASE_URL}/htm/ssr/{href}"

        try:
            qs = parse_qs(urlparse(full_url).query)
            n = qs.get("n", [None])[0]
        except Exception:
            n = None
        if not n or n in seen_ids:
            continue

        # 「[詳細はこちらをクリック]」のような誘導リンクは飛ばす
        link_text = a.get_text(strip=True)
        # ※細かい誘導リンクは無視して、最初に出てくるタイトルを採用
        if "詳細" in link_text and "クリック" in link_text:
            # この場合タイトルは別の場所（dt 内のテキスト）から取る必要がある
            # → 親要素を見る
            parent = a.find_parent(["dt", "li", "dd"])
            if parent:
                t = parent.get_text(" ", strip=True)
                # 「26/03/30掲載」のような日付プレフィックスを取り除く
                t = re.sub(r"^\d{2}/\d{2}/\d{2}掲載", "", t).strip()
                # 「→[詳細はこちらをクリック]」を取り除く
                t = re.sub(r"→?\s*\[?詳細[^]]*\]?", "", t).strip()
                # 最初の20文字くらいがタイトル候補
                title_hint = t.split("日時")[0].strip()[:80]
            else:
                title_hint = ""
            seen_ids.add(n)
            results.append({
                "id": n,
                "url": full_url,
                "title_hint": title_hint,
            })
        else:
            # アンカーテキストがそのままタイトルのケース
            seen_ids.add(n)
            results.append({
                "id": n,
                "url": full_url,
                "title_hint": link_text,
            })

    return results


# ----------------------------------------------------------------------
# 詳細ページパース
# ----------------------------------------------------------------------
def parse_event_detail(url: str, html: str) -> Event:
    soup = BeautifulSoup(html, "html.parser")

    # ナビゲーション類を除去
    for tag_name in ("script", "style", "nav", "header", "footer"):
        for el in soup.find_all(tag_name):
            el.decompose()

    # タイトル：<title>タグから「-- ... --」のパターンを取る
    title = ""
    title_tag = soup.find("title")
    if title_tag:
        t = title_tag.get_text(strip=True)
        # "--第45回せいせき桜まつり-- せいせきショップ.com編集"
        m = re.match(r"^--(.+?)--", t)
        if m:
            title = m.group(1).strip()
    # フォールバック：h4を探す
    if not title:
        for h in soup.select("h4"):
            t = h.get_text(strip=True)
            if t and "イベント" not in t:
                title = t
                break

    # 画像：本文中の最初の /images/event/ にあるもの
    image_url = None
    for img in soup.select("img"):
        src = img.get("src", "")
        if "/images/event/" in src or "/images/" in src and src.endswith((".png", ".jpg", ".jpeg", ".gif")):
            if "icon" in src or "common" in src or "logo" in src:
                continue
            if not src.startswith("http"):
                src = f"{BASE_URL}{src}" if src.startswith("/") else f"{BASE_URL}/{src}"
            image_url = src
            break

    # 構造化メタ：h5見出し直下のテキストを集める
    # 例:
    #   <h5>日時：</h5>
    #   全日5日（日）10:00〜17:00...
    #   <h5>場所：</h5>
    #   京王聖蹟桜ヶ丘駅周辺...
    meta = _extract_h5_pairs(soup)

    time_label = meta.get("日時") or meta.get("時間") or meta.get("開催日") or meta.get("開催日時")
    venue = meta.get("場所") or meta.get("会場") or meta.get("開催場所")

    # 主催系：複数候補から優先度順に採用
    organizer_keys = ["主催", "主催者", "共催", "後援", "協賛", "特別協賛", "協力"]
    organizer = None
    for kw in organizer_keys:
        if kw in meta and meta[kw]:
            organizer = meta[kw]
            if kw not in ("主催", "主催者"):
                organizer = f"[{kw}] {organizer}"
            break

    # 本文：h5の値（meta）も含めて、検索性とカテゴリ判定に使う
    body_lines: list[str] = []
    main = soup.find("section") or soup.find("article") or soup
    for el in main.select("p, dd"):
        txt = el.get_text("\n", strip=True)
        if not txt or len(txt) < 5:
            continue
        if any(w in txt for w in (
            "Copyright", "サイトマップ", "お問い合わせ", "リンク",
            "トップページ", "詳細はこちら", "ホームページ",
        )):
            continue
        body_lines.append(txt)

    # h5 の値も本文に追加（カテゴリ判定でフルテキスト検索するため）
    for k, v in meta.items():
        body_lines.append(f"{k}: {v}")

    body = "\n\n".join(body_lines).strip()

    # 日付パース：time_label を最優先、なければ body から探す
    date_text = time_label or ""
    date_start, date_end = parse_date_jp(date_text)
    if not date_start and body:
        # 本文中に「2026年X月Y日」のような完全な日付が書かれていれば使う
        date_start, date_end = parse_date_jp(body)

    # ステータス
    status = infer_status_by_date(date_start, date_end)

    # カテゴリ判定：本文・場所から推測
    tags = _infer_tags(title, body, venue)

    iso = now_iso()
    return Event(
        id=f"sssc-{_id_from_url(url)}",
        source=SOURCE,
        url=url,
        title=title,
        date_label=time_label or "",
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
    qs = parse_qs(urlparse(url).query)
    return qs.get("n", ["unknown"])[0]


def _extract_h5_pairs(soup) -> dict[str, str]:
    """h5見出しとその直後のテキストを辞書化する。
    見出しの末尾の「：」はキーから取り除く。
    複数の段落にまたがる値は \n で結合。
    """
    pairs: dict[str, str] = {}
    for h5 in soup.select("h5"):
        key = h5.get_text(strip=True).rstrip("：:").strip()
        if not key:
            continue
        # h5 の次の兄弟ノードからテキストを集める（次の h5 までが値）
        values: list[str] = []
        for sib in h5.next_siblings:
            if hasattr(sib, "name") and sib.name == "h5":
                break
            if hasattr(sib, "get_text"):
                t = sib.get_text("\n", strip=True)
                if t:
                    values.append(t)
            elif isinstance(sib, str):
                t = sib.strip()
                if t:
                    values.append(t)
        val = "\n".join(values).strip()
        if val:
            pairs[key] = val
    return pairs


# 場所カテゴリ推定のキーワード
SC_KEYWORDS = (
    "京王聖蹟桜ヶ丘ショッピングセンター", "京王SC", "京王S.C", "京王プラザ",
    "ヴィータモール", "VITA MALL", "京王百貨店",
    "オーパ", "OPA",
)
KAWAMACHI_KEYWORDS = (
    "せいせきカワマチ", "カワマチ", "多摩川河川敷", "一ノ宮公園",
)
# 「まちなか系」と判定する商店会・地域団体キーワード
MACHINAKA_KEYWORDS = (
    "商店会", "商店街", "実行委員会", "関戸", "桜まつり",
    "せいせき桜まつり", "聖蹟桜ヶ丘大通り",
    "桜が丘商店", "観光協会",
)


def _infer_tags(title: str, body: str, venue: str | None) -> list[str]:
    """本文・場所から場所カテゴリを推定。

    複数該当する場合はすべてつける（CATEGORY_PRIMARY_ORDER で優先1つが採用される）。
    商店会系・実行委員会系のイベントは、SC会場と連携していても「まちなか」を必ず付ける。
    """
    text = f"{title}\n{body}\n{venue or ''}"
    tags: list[str] = []
    if any(k in text for k in KAWAMACHI_KEYWORDS):
        tags.append("せいせきカワマチ")
    if any(k in text for k in SC_KEYWORDS):
        tags.append("ショッピングセンター")
    # 商店会・実行委員会系のキーワードがあれば「まちなか」を追加
    if any(k in text for k in MACHINAKA_KEYWORDS):
        if "まちなか" not in tags:
            tags.append("まちなか")
    # SC・カワマチ・まちなか いずれにも該当しない → デフォは「まちなか」
    if not tags:
        tags.append("まちなか")
    return tags


# ----------------------------------------------------------------------
# メインフロー
# ----------------------------------------------------------------------
def crawl(download_images: bool = False, **kwargs) -> None:
    session = make_session()
    existing = load_existing()

    print(f"[{SOURCE}] fetching event list...", file=sys.stderr)
    list_html = fetch_html(session, EVENT_LIST_URL, encoding=ENCODING)
    candidates = parse_event_list_page(list_html)
    print(f"[{SOURCE}] found {len(candidates)} events", file=sys.stderr)

    new_events: list[Event] = []
    for i, c in enumerate(candidates, 1):
        try:
            print(f"[{SOURCE}] [{i}/{len(candidates)}] {c['url']}", file=sys.stderr)
            html = fetch_html(session, c["url"], encoding=ENCODING)
            ev = parse_event_detail(c["url"], html)
            # タイトルが取れなかった場合は一覧ページのヒントで補完
            if not ev.title and c.get("title_hint"):
                ev.title = c["title_hint"]
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
