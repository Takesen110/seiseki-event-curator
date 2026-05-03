#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrapers/keio_sc.py
京王聖蹟桜ヶ丘ショッピングセンター (keio-sc.jp) のスクレイパー。

source identifier: "keio-sc.jp"

- /eventtopics/?yearmonth=YYYYMM で月別カレンダーから一覧を取得
- /eventtopics/detail/?cd=NNNNNN で詳細ページを取得
- 当月を中心に、前後N ヶ月をスキャンする（デフォルト前後1ヶ月）
- 全イベントのカテゴリは「ショッピングセンター」固定
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, date
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scrapers.common import (  # noqa: E402
    Event, now_iso, make_session, fetch_html,
    load_existing, save_events, merge_events,
    parse_keio_date, infer_status_by_date, download_image,
    IMAGES_DIR,
)

# ----------------------------------------------------------------------
SOURCE = "keio-sc.jp"
BASE_URL = "https://www.keio-sc.jp"
EVENT_LIST_URL = f"{BASE_URL}/eventtopics/"


# ----------------------------------------------------------------------
# 一覧ページ：イベント詳細URLを抽出
# ----------------------------------------------------------------------
def parse_event_list_page(html: str) -> list[dict]:
    """
    一覧ページから、イベント詳細URL一覧を返す。
    一覧上にも、日付ラベル（"5月7日（木）～5月13日（水）"）と
    タイトルがあるので、それも取れれば一緒に拾っておく。
    """
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []
    seen_cds: set[str] = set()

    # 詳細URLは /eventtopics/detail/?cd=NNNNNN の形
    for a in soup.select("a"):
        href = a.get("href", "")
        if "/eventtopics/detail/?cd=" not in href:
            continue
        # cdクエリ抽出
        try:
            qs = parse_qs(urlparse(href).query)
            cd = qs.get("cd", [None])[0]
        except Exception:
            cd = None
        if not cd or cd in seen_cds:
            continue
        seen_cds.add(cd)

        # 一覧上のテキストから日付ラベルを拾う
        # アンカー内テキストを行ごとに見て、日付っぽい行を抽出
        full_text = a.get_text("\n", strip=True)
        lines = [l for l in full_text.split("\n") if l]
        date_label_hint = ""
        title_hint = ""
        for ln in lines:
            # "EVENT" などの種別ラベルは飛ばす
            if ln in ("EVENT", "TOPICS", "INFORMATION"):
                continue
            # 日付っぽい：月日が含まれる
            if re.search(r"\d{1,2}月\d{1,2}日|\d{4}年\d{1,2}月\d{1,2}日", ln) \
                    or re.search(r"\d{1,2}/\d{1,2}", ln):
                if not date_label_hint:
                    date_label_hint = ln
                    continue
            # それ以外で空でない行 → タイトル候補
            if not title_hint and len(ln) > 3:
                title_hint = ln

        # 詳細ページURLを正規化（クエリのみ ?cd=... に揃える）
        full_url = href if href.startswith("http") else f"{BASE_URL}{href}"

        results.append({
            "cd": cd,
            "url": full_url,
            "date_label_hint": date_label_hint,
            "title_hint": title_hint,
        })

    return results


# ----------------------------------------------------------------------
# 月切替URLビルダー
# ----------------------------------------------------------------------
def month_url(year: int, month: int) -> str:
    return f"{EVENT_LIST_URL}?yearmonth={year:04d}{month:02d}"


def yearmonth_iter(center: date, span: int) -> list[tuple[int, int]]:
    """中心月の前後 span ヶ月の (year, month) リストを返す（過去→未来順）"""
    result = []
    y, m = center.year, center.month
    for offset in range(-span, span + 1):
        nm = m + offset
        ny = y
        while nm <= 0:
            nm += 12
            ny -= 1
        while nm > 12:
            nm -= 12
            ny += 1
        result.append((ny, nm))
    return result


# ----------------------------------------------------------------------
# 詳細ページパース
# ----------------------------------------------------------------------
def parse_event_detail(url: str, html: str, hint_year: int,
                        date_label_fallback: str = "") -> Event:
    soup = BeautifulSoup(html, "html.parser")

    # ナビ・フッターを除去
    for tag_name in ("noscript", "script", "style", "header", "footer", "nav"):
        for el in soup.find_all(tag_name):
            el.decompose()

    # タイトル：<title>タグから「| イベント&トピックス…」より前の部分を取る
    title = ""
    title_tag = soup.find("title")
    if title_tag:
        t = title_tag.get_text(strip=True)
        # "母の日 ハンドメイドワークショップを開催します！ | イベント&トピックス｜..."
        title = re.split(r"\s*\|\s*", t)[0].strip()

    # 画像：詳細ページ上の最初のイベント関連画像を取る
    image_url = None
    for img in soup.select("img"):
        src = img.get("src", "")
        if "/uploads/images/" in src and "frame" not in src and "logo" not in src:
            if not src.startswith("http"):
                src = BASE_URL + src
            image_url = src
            break

    # 構造化されたメタ項目を抽出
    # 詳細ページには「期間」「時間」「場所」「参加方法」「お問い合わせ」「備考」などが
    # ラベル+値の形で並んでいる。
    meta_pairs = _extract_meta_pairs(soup)

    period = meta_pairs.get("期間", "")
    time_label = meta_pairs.get("時間")
    venue = meta_pairs.get("場所")
    organizer = meta_pairs.get("お問い合わせ")
    fee = meta_pairs.get("参加費")
    contact_tel = meta_pairs.get("(TEL)") or meta_pairs.get("TEL")

    # 本文（メイン領域のテキストを集める）
    body_parts: list[str] = []
    main = soup.find("main") or soup
    for p in main.select("p, li"):
        txt = p.get_text("\n", strip=True)
        if not txt:
            continue
        if len(txt) < 3:
            continue
        # ナビ・SNSリンク等を除外
        if any(w in txt for w in (
            "BACK TO LIST", "SHARE", "FaceBook", "LINE",
            "営業時間", "サイトポリシー", "プライバシーポリシー",
            "Copyright", "ENGLISH", "トリミングフレーム",
        )):
            continue
        body_parts.append(txt)

    body = "\n\n".join(body_parts).strip()

    # 日付ラベルを決定：構造化された「期間」を優先、なければ一覧でのヒント
    date_text = period or date_label_fallback
    date_start, date_end = parse_keio_date(date_text, hint_year)

    # ステータス推定：start/end と今日の関係から
    status = infer_status_by_date(date_start, date_end)

    # 京王SCはすべてSCカテゴリ
    tags = ["ショッピングセンター"]

    iso = now_iso()
    return Event(
        id=_id_from_url(url),
        source=SOURCE,
        url=url,
        title=title,
        date_label=date_text,
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
    """?cd=NNNNNN から ID を作る"""
    qs = parse_qs(urlparse(url).query)
    cd = qs.get("cd", ["unknown"])[0]
    return f"keiosc-{cd}"


def _extract_meta_pairs(soup) -> dict[str, str]:
    """詳細ページの「期間」「時間」「場所」など、ラベル+値の構造を辞書化。

    京王SCの詳細ページは li 要素に
        <li>期間5月7日（木）～5月13日（水）</li>
    のように、ラベル直後にスペースなしで値が続く形式。
    既知のラベル接頭辞でマッチさせる。
    """
    KNOWN_LABELS = (
        "期間", "時間", "場所", "参加方法", "参加費",
        "お問い合わせ", "備考", "対象", "定員", "申込", "予約",
    )
    pairs: dict[str, str] = {}
    for li in soup.select("li"):
        txt = li.get_text("\n", strip=True)
        if not txt:
            continue
        # "期間5月7日（木）～..." or "期間 5月7日..." or "期間：5月7日..."
        for label in KNOWN_LABELS:
            m = re.match(rf"^{re.escape(label)}\s*[：:]?\s*(.+)", txt, flags=re.S)
            if m:
                val = m.group(1).strip()
                # 「お問い合わせ」のような行は複数行になる場合があるので最初の数行だけ
                val_first_line = val.split("\n")[0].strip()
                if label in pairs:
                    continue
                pairs[label] = val_first_line
                break
        # TEL情報も拾う
        m = re.search(r"\(TEL\)\s*([\d\-]+)", txt)
        if m and "TEL" not in pairs:
            pairs["TEL"] = m.group(1)
    return pairs


# ----------------------------------------------------------------------
# メインフロー
# ----------------------------------------------------------------------
def crawl(months_span: int = 1, download_images: bool = False, **kwargs) -> None:
    """
    months_span: 現在月から前後何ヶ月までスキャンするか（デフォルト1）
    download_images: 画像をローカルにダウンロードするか
    kwargs: 互換のため余分な引数を受け取るだけ
    """
    session = make_session()
    existing = load_existing()

    today = date.today()
    months = yearmonth_iter(today, months_span)
    print(f"[{SOURCE}] scanning months: {months}", file=sys.stderr)

    # 一覧から候補URL収集
    candidates: list[dict] = []
    months_per_url: dict[str, int] = {}  # 各URLが見つかった月（年補完用）
    for y, m in months:
        url = month_url(y, m)
        try:
            html = fetch_html(session, url)
        except Exception as e:
            print(f"  ! failed to fetch {url}: {e}", file=sys.stderr)
            continue
        items = parse_event_list_page(html)
        for it in items:
            if it["cd"] not in months_per_url:
                months_per_url[it["cd"]] = y  # 最初に見つかった月の年を採用
            candidates.append(it)

    # 重複排除（cdベース）
    seen_cds: set[str] = set()
    unique = []
    for c in candidates:
        if c["cd"] in seen_cds:
            continue
        seen_cds.add(c["cd"])
        unique.append(c)

    print(f"[{SOURCE}] found {len(unique)} unique events", file=sys.stderr)

    # 詳細ページ取得
    new_events: list[Event] = []
    for i, c in enumerate(unique, 1):
        try:
            print(f"[{SOURCE}] [{i}/{len(unique)}] {c['url']}", file=sys.stderr)
            html = fetch_html(session, c["url"])
            hint_year = months_per_url.get(c["cd"], today.year)
            ev = parse_event_detail(
                c["url"], html,
                hint_year=hint_year,
                date_label_fallback=c.get("date_label_hint", ""),
            )
            if download_images and ev.image_url:
                local = download_image(session, ev.image_url, IMAGES_DIR)
                if local:
                    ev.image_local = local
            new_events.append(ev)
        except Exception as e:
            print(f"  ! error: {e}", file=sys.stderr)
            continue

    merge_events(existing, new_events, source=SOURCE, archive_missing=False)
    # 注：archive_missing=False にしている理由：
    # 京王SCは月別に取得範囲を絞るため、範囲外のイベントを誤って archived 扱いに
    # しないようにしている。古いイベントは自然に終了ステータスのまま残す。
    save_events(existing)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months-span", type=int, default=1,
                    help="現在月から前後N ヶ月をスキャン（デフォルト1）")
    ap.add_argument("--download-images", action="store_true",
                    help="画像をローカルダウンロード")
    ap.add_argument("--pages", type=int, default=None,
                    help="（互換用）")
    args = ap.parse_args()
    crawl(months_span=args.months_span, download_images=args.download_images)


if __name__ == "__main__":
    main()
