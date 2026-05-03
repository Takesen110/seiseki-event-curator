#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrapers/tamapon.py
多摩ポン (tamapon.com) のスクレイパー。多摩エリア地域メディアのため、
聖蹟桜ヶ丘エリアの記事のみをフィルタして採用する。

source identifier: "tamapon.com"

特徴:
- WordPress製、UTF-8
- イベントカテゴリ /category/event/ から記事一覧を取得（複数ページ）
- 記事URLパターン: /YYYY/MM/DD/{slug}/
- 本文に「聖蹟桜ヶ丘」「せいせき」「多摩川河川敷」「カワマチ」等を含む記事のみ採用

注意:
- 多摩ポンは多摩エリア全体メディアなので、フィルタなしだと多摩センター・八王子・
  立川・調布・府中などのイベントが大量に入る。今回は聖蹟桜ヶ丘エリアに絞る。
- 同じイベントが他ソース（seiseki.org、keio-sc.jp等）にも存在することは想定済み。
  multi-source duplicate OK 運用なので、そのまま入れる。
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
    parse_date_jp, parse_keio_date, infer_status_by_date, download_image,
    IMAGES_DIR,
)

# ----------------------------------------------------------------------
SOURCE = "tamapon.com"
BASE_URL = "https://tamapon.com"

# イベントカテゴリのアーカイブ
EVENT_ARCHIVE_URL = f"{BASE_URL}/category/event/"

# 聖蹟桜ヶ丘エリア判定キーワード
# タイトルまたは本文に少なくとも1つ含まれていれば採用
SEISEKI_KEYWORDS = (
    "聖蹟桜ヶ丘", "聖蹟", "せいせき", "せいせきカワマチ",
    "カワマチ", "多摩川河川敷", "一ノ宮公園", "一ノ宮",
    "関戸", "桜ヶ丘", "桜ケ丘", "桜が丘",
    "京王聖蹟", "ヴィータモール", "ザ・スクエア",
    "聖ヶ丘", "聖が丘",
)

# 「多摩エリア全体」だけれど聖蹟と無関係なものを除外するキーワード
# （タイトルに含まれていたら除外）
NON_SEISEKI_TITLE_KEYWORDS = (
    "多摩センター", "唐木田", "永山", "貝取", "聖蹟以外",
    "立川", "八王子", "府中", "調布", "町田",
    "日野", "国立", "国分寺", "高尾", "若葉台",
    "稲城", "京王よみうりランド", "京王多摩川",
    "桜ヶ丘四丁目",  # この「桜ヶ丘」はバス停名で、実は聖蹟桜ヶ丘とは別エリア
)


# ----------------------------------------------------------------------
# カテゴリアーカイブから記事URLを抽出
# ----------------------------------------------------------------------
ARTICLE_URL_RE = re.compile(
    r"https?://tamapon\.com/(\d{4})/(\d{1,2})/(\d{1,2})/([^/]+)/?"
)


def parse_archive_page(html: str) -> list[dict]:
    """
    カテゴリアーカイブページから個別記事のURLとサムネ・タイトル・日付ヒントを抽出。

    WordPress標準的なテーマで、各記事は <article> または <li> 内に：
      <a href="https://tamapon.com/YYYY/MM/DD/slug/">
        <img src="...">
        <h2 or h3>タイトル</h2>
      </a>
      日付（投稿日）

    パターンが多少違っても、URLパターンを正規表現でマッチさせて拾う。
    """
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []
    seen_urls: set[str] = set()

    for a in soup.select("a"):
        href = a.get("href", "")
        m = ARTICLE_URL_RE.match(href)
        if not m:
            continue
        # 記事URLを正規化（末尾スラッシュなし）
        full_url = f"{BASE_URL}/{m.group(1)}/{m.group(2)}/{m.group(3)}/{m.group(4)}/"
        if full_url in seen_urls:
            continue

        y, mo, d, slug = m.group(1), m.group(2), m.group(3), m.group(4)
        post_date = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"

        # 画像（アンカー内に img があれば）
        image_url = None
        img = a.find("img")
        if img and img.get("src"):
            src = img.get("src")
            image_url = src if src.startswith("http") else f"{BASE_URL}{src}"
        # data-src（lazy load）も見る
        if not image_url and img and img.get("data-src"):
            src = img.get("data-src")
            image_url = src if src.startswith("http") else f"{BASE_URL}{src}"

        # タイトル：アンカー内テキスト or 親要素から h2/h3 を探す
        title = a.get_text(strip=True)
        # タイトル候補が「画像のalt」や「続きを読む」のような場合は親から拾う
        if not title or len(title) < 3 or "続きを読む" in title:
            parent = a.find_parent(["article", "li", "div"])
            if parent:
                h = parent.find(["h2", "h3", "h4"])
                if h:
                    title = h.get_text(strip=True)

        seen_urls.add(full_url)
        results.append({
            "slug": slug,
            "url": full_url,
            "post_date": post_date,
            "title_hint": title,
            "image_url": image_url,
        })

    return results


def find_next_page_url(html: str, current_url: str) -> str | None:
    """ページネーションの次ページURLを探す（WordPress標準）"""
    soup = BeautifulSoup(html, "html.parser")
    # rel="next" のリンク
    for a in soup.select("a[rel='next']"):
        href = a.get("href")
        if href:
            return href if href.startswith("http") else f"{BASE_URL}{href}"
    # .next クラス
    for a in soup.select("a.next, a.nextpostslink"):
        href = a.get("href")
        if href:
            return href if href.startswith("http") else f"{BASE_URL}{href}"
    # /page/N/ パターンを次のページ番号で探す
    m = re.search(r"/page/(\d+)/?$", current_url)
    cur_n = int(m.group(1)) if m else 1
    target = f"/page/{cur_n + 1}/"
    for a in soup.select("a"):
        href = a.get("href", "")
        if target in href and "category/event" in href:
            return href if href.startswith("http") else f"{BASE_URL}{href}"
    return None


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

    # 画像：本文中の最初の wp-content/uploads（OGP画像、サムネを優先）
    image_url = hints.get("image_url")
    if not image_url:
        og = soup.find("meta", attrs={"property": "og:image"})
        if og and og.get("content"):
            image_url = og["content"]
    if not image_url:
        for img in soup.select("img"):
            src = img.get("src", "")
            if not src and img.get("data-src"):
                src = img.get("data-src")
            if not src:
                continue
            if "/wp-content/uploads/" in src and "logo" not in src:
                image_url = src if src.startswith("http") else f"{BASE_URL}{src}"
                break

    # 本文：article または entry-content
    article = soup.find("article") or soup.find(class_=re.compile("entry-content|post-content"))
    if not article:
        article = soup

    body_lines: list[str] = []
    for p in article.select("p, li, h2, h3"):
        txt = p.get_text("\n", strip=True)
        if not txt or len(txt) < 5:
            continue
        if any(w in txt for w in (
            "Copyright", "サイトマップ", "本記事に含まれる広告",
            "関連記事", "Tweet", "コメント", "シェア",
        )):
            continue
        body_lines.append(txt)
    body = "\n\n".join(body_lines).strip()

    # 「開催日：YYYY年M月D日」「日時：YYYY年M月D日」のような構造化情報を本文から抽出
    time_label = _extract_field(body, ("開催日時", "開催日", "日時", "実施日"))
    venue = _extract_field(body, ("会場", "場所", "開催場所"))
    organizer = _extract_field(body, ("主催", "主催者"))

    # 日付パース
    date_start, date_end = None, None
    if time_label:
        date_start, date_end = parse_date_jp(time_label)
        if not date_start:
            # M/D形式や月省略を含む可能性
            post_year = int(hints["post_date"].split("-")[0]) if hints.get("post_date") else 2026
            date_start, date_end = parse_keio_date(time_label, post_year)
    # それでも取れなかったら本文全体から
    if not date_start and body:
        date_start, date_end = parse_date_jp(body)

    status = infer_status_by_date(date_start, date_end)

    # カテゴリ判定：本文・タイトルから推定
    tags = _infer_tags(title, body, venue)

    iso = now_iso()
    return Event(
        id=f"tamapon-{hints['slug'][:60]}",  # スラッグが長すぎる場合があるので切る
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
        organizer=organizer or "（多摩ポン記事）",
        time_label=time_label,
        is_kitchen_car=False,
        first_seen=iso,
        last_seen=iso,
    )


def _extract_field(body: str, keywords: tuple[str, ...]) -> str | None:
    """本文から「{キーワード}：値」または「{キーワード} 値」を抽出"""
    for line in body.split("\n"):
        line = line.strip()
        for kw in keywords:
            # "開催日：2026年4月5日(日)"
            m = re.match(rf"^\s*[■●]?\s*{kw}\s*[:：]\s*(.+)$", line)
            if m:
                v = m.group(1).strip()
                if v and len(v) < 200:
                    return v
    return None


# 場所カテゴリ推定（他のスクレイパーと同じロジックを流用）
SC_KEYWORDS = (
    "京王聖蹟桜ヶ丘ショッピングセンター", "京王SC", "京王S.C", "京王プラザ",
    "ヴィータモール", "VITA MALL", "京王百貨店",
    "オーパ", "OPA", "ザ・スクエア",
    "アウラホール",  # 京王SC A館6階のホール
)
KAWAMACHI_KEYWORDS = (
    "せいせきカワマチ", "カワマチ", "多摩川河川敷", "一ノ宮公園",
)
MACHINAKA_KEYWORDS = (
    "商店会", "商店街", "実行委員会",
    "せいせき桜まつり", "桜まつり", "ハートフルコンサート",
    "観光まちづくり", "せいせき音フェス",
)


def _infer_tags(title: str, body: str, venue: str | None) -> list[str]:
    """タイトル＋本文から場所カテゴリを推定。複数ヒットなら併記。"""
    text = f"{title}\n{body}\n{venue or ''}"
    tags: list[str] = []
    if any(k in text for k in KAWAMACHI_KEYWORDS):
        tags.append("せいせきカワマチ")
    if any(k in text for k in SC_KEYWORDS):
        tags.append("ショッピングセンター")
    if any(k in text for k in MACHINAKA_KEYWORDS):
        if "まちなか" not in tags:
            tags.append("まちなか")
    if not tags:
        tags.append("まちなか")  # デフォルト
    return tags


# ----------------------------------------------------------------------
# 聖蹟桜ヶ丘フィルタ
# ----------------------------------------------------------------------
def is_seiseki_related(title: str, body: str = "") -> bool:
    """タイトル or 本文に聖蹟桜ヶ丘エリアキーワードを含むか判定"""
    text = f"{title}\n{body}"
    # まず除外キーワード（タイトル）にヒットしたら、聖蹟キーワードで明示的に
    # 含まれているか確認。聖蹟キーワードが無いなら除外。
    if any(k in title for k in NON_SEISEKI_TITLE_KEYWORDS):
        # 明示的に「聖蹟」「せいせき」が含まれているなら採用
        # （多摩センター × 聖蹟連携イベントなど）
        if not any(k in title for k in ("聖蹟", "せいせき", "カワマチ")):
            return False
    # ポジティブ判定
    return any(k in text for k in SEISEKI_KEYWORDS)


# ----------------------------------------------------------------------
# メインフロー
# ----------------------------------------------------------------------
def crawl(download_images: bool = False, max_pages: int = 5,
          max_articles: int | None = None, **kwargs) -> None:
    """
    多摩ポンのイベントカテゴリから記事を取得し、聖蹟桜ヶ丘関連だけを採用。

    max_pages: アーカイブの最大ページ数（1ページ10〜20件×N）
    max_articles: 取得する記事の最大数（テスト用）
    """
    session = make_session()
    existing = load_existing()

    # 全ページ巡回して記事URL一覧を作る
    all_cards: list[dict] = []
    seen_urls: set[str] = set()
    page_url = EVENT_ARCHIVE_URL

    for page_no in range(1, max_pages + 1):
        print(f"[{SOURCE}] fetching archive page {page_no}: {page_url}", file=sys.stderr)
        try:
            html = fetch_html(session, page_url)
        except Exception as e:
            print(f"  ! page fetch error: {e}", file=sys.stderr)
            break

        cards = parse_archive_page(html)
        new_count = 0
        for c in cards:
            if c["url"] in seen_urls:
                continue
            seen_urls.add(c["url"])
            all_cards.append(c)
            new_count += 1
        print(f"  → {new_count} new article URLs (total {len(all_cards)})",
              file=sys.stderr)

        if new_count == 0:
            break  # ページネーションが終わったか取得失敗
        if max_articles and len(all_cards) >= max_articles:
            break

        next_url = find_next_page_url(html, page_url)
        if not next_url:
            print(f"  → no next page link", file=sys.stderr)
            break
        page_url = next_url

    print(f"[{SOURCE}] total {len(all_cards)} candidate articles, "
          f"filtering for 聖蹟桜ヶ丘 area...", file=sys.stderr)

    # タイトルでまず一次フィルタ（明らかに違う地域は本文取得をスキップ）
    pre_filtered = []
    for c in all_cards:
        title = c.get("title_hint", "")
        if any(kw in title for kw in SEISEKI_KEYWORDS):
            pre_filtered.append(c)
        elif any(kw in title for kw in NON_SEISEKI_TITLE_KEYWORDS):
            # 明らかに別エリア → 本文も見ない
            pass
        else:
            # タイトルだけでは判定できない → 本文確認のため候補に残す
            pre_filtered.append(c)

    print(f"[{SOURCE}] pre-filtered to {len(pre_filtered)} articles "
          f"(skipped obviously non-seiseki titles)", file=sys.stderr)

    new_events: list[Event] = []
    skipped = 0
    for i, c in enumerate(pre_filtered, 1):
        if max_articles and (len(new_events) + skipped) >= max_articles:
            break
        try:
            print(f"[{SOURCE}] [{i}/{len(pre_filtered)}] {c['url']}", file=sys.stderr)
            detail_html = fetch_html(session, c["url"])
            ev = parse_event_detail(c["url"], detail_html, hints=c)
        except Exception as e:
            print(f"  ! error: {e}", file=sys.stderr)
            continue

        # 本文込みで聖蹟桜ヶ丘関連か再判定
        if not is_seiseki_related(ev.title, ev.body):
            print(f"  ↪ skipped (not seiseki-related): {ev.title[:40]}",
                  file=sys.stderr)
            skipped += 1
            continue

        if download_images and ev.image_url:
            local = download_image(session, ev.image_url, IMAGES_DIR)
            if local:
                ev.image_local = local

        new_events.append(ev)

    print(f"[{SOURCE}] adopted {len(new_events)} articles, "
          f"skipped {skipped} as non-seiseki", file=sys.stderr)

    merge_events(existing, new_events, source=SOURCE, archive_missing=False)
    save_events(existing)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--download-images", action="store_true",
                    help="画像をローカルダウンロード")
    ap.add_argument("--max-pages", type=int, default=5,
                    help="アーカイブの最大ページ数（デフォルト5）")
    ap.add_argument("--max-articles", type=int, default=None,
                    help="取得する記事の最大数（テスト用）")
    args = ap.parse_args()
    crawl(
        download_images=args.download_images,
        max_pages=args.max_pages,
        max_articles=args.max_articles,
    )


if __name__ == "__main__":
    main()
