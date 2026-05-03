#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrapers/common.py
全スクレイパーで共有する型定義・保存・分類ロジック。

各サイト固有のスクレイパー（seiseki_org.py, keio_sc.py 等）は、
ここで定義された Event を生成して save_events() に渡す。

データの一意性は (source, id) のペアで管理する。
"""
from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

import requests

# ----------------------------------------------------------------------
# 共通定数
# ----------------------------------------------------------------------
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36 "
    "(seiseki-curator/0.2; HoloLab Marketing)"
)
REQUEST_INTERVAL_SEC = 1.0
REQUEST_TIMEOUT_SEC = 30

# 全スクレイパー共通のデータディレクトリ（curator.html もここを見る）
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
EVENTS_JSON = DATA_DIR / "events.json"
IMAGES_DIR = DATA_DIR / "images"

# 既知の場所カテゴリタグ（seiseki.org由来。他ソースでは事実上空でもよい）
KNOWN_TAGS = {
    "せいせきカワマチ",
    "ショッピングセンター",
    "まちなか",
}

# ----------------------------------------------------------------------
# カテゴリ / ジャンル / ハッシュタグの設定
# ----------------------------------------------------------------------
CATEGORY_PRIMARY_ORDER = ("せいせきカワマチ", "まちなか", "ショッピングセンター")

LOCATION_HASHTAGS: dict[str, list[str]] = {
    "せいせきカワマチ": ["#せいせきカワマチ", "#聖蹟桜ヶ丘"],
    "ショッピングセンター": ["#せいせきSC", "#聖蹟桜ヶ丘"],
    "まちなか": ["#聖蹟桜ヶ丘"],
    "その他": ["#聖蹟桜ヶ丘"],
}

# 全イベント共通で付ける（curator UI が COMMON_HASHTAGS をどう扱うかは UI 側の責務）
COMMON_HASHTAGS: list[str] = []  # 武仙さん運用に合わせて空（カテゴリ別が主）

GENRE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "kitchen_car": ("キッチンカー", "屋台", "出店者"),
    "family":      ("子ども", "こども", "親子", "ファミリー", "キッズ", "KID"),
    "pet":         ("犬と", "愛犬", "ワンコ", "ドッグ", "DOG", "ペット同伴"),
    "market":      ("マルシェ", "蚤の市", "フリマ", "マーケット", "手作り市"),
    "culture":     ("ライブ", "コンサート", "音楽イベント", "アート", "映画祭",
                    "ステージ", "シャイニーカラーズ", "アイドルマスター"),
    "beer":        ("ビールまつり", "クラフトビール", "BEER", "ブルワリー", "ビアガーデン"),
    "wellness":    ("ヨガ", "ウェルネス", "フィットネス", "リトリート", "Retreat"),
    "xmas":        ("クリスマス", "Xmas", "イルミネーション", "Christmas"),
    "seasonal_sakura": ("桜まつり", "桜祭り", "お花見", "夜桜", "花見イベント"),
    "seasonal_summer": ("夏祭り", "盆踊り", "花火大会"),
    "seasonal_autumn": ("紅葉狩り", "ハロウィン", "Halloween"),
    "ninja":       ("忍者の日", "忍者イベント", "NINJA"),
}

GENRE_NEGATIVE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "seasonal_sakura": ("桜ヶ丘", "桜が丘", "桜丘"),
}


# ----------------------------------------------------------------------
# データ構造
# ----------------------------------------------------------------------
@dataclass
class Event:
    """1イベントの構造化データ（全ソース共通）"""
    id: str                              # ソース内で一意のID（URLスラッグなど）
    source: str                          # データソース識別子（"seiseki.org" 等）
    url: str                             # 詳細ページURL
    title: str
    date_label: str                      # 表示用の日付ラベル
    date_start: str | None = None        # ISO形式 YYYY-MM-DD
    date_end: str | None = None
    status: str | None = None            # 開催予定 / 開催中 / 終了
    tags: list[str] = field(default_factory=list)
    category_primary: str | None = None
    genres: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)
    image_url: str | None = None
    image_local: str | None = None
    body: str = ""
    venue: str | None = None
    organizer: str | None = None
    time_label: str | None = None
    is_kitchen_car: bool = False
    first_seen: str = ""
    last_seen: str = ""
    archived: bool = False


# ----------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------
def make_session() -> requests.Session:
    """User-Agent付きの共通セッション"""
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def fetch_html(session: requests.Session, url: str,
                encoding: str | None = None) -> str:
    """HTML取得 + レート制限。
    encoding 指定時はそれを使う（Shift_JISサイト等）。
    """
    print(f"  GET {url}", file=sys.stderr)
    r = session.get(url, timeout=REQUEST_TIMEOUT_SEC)
    r.raise_for_status()
    if encoding:
        r.encoding = encoding
    else:
        r.encoding = r.apparent_encoding or "utf-8"
    time.sleep(REQUEST_INTERVAL_SEC)
    return r.text


# ----------------------------------------------------------------------
# 分類ロジック
# ----------------------------------------------------------------------
def determine_category_primary(tags: list[str]) -> str:
    """サイトの複数タグから、プライマリ場所カテゴリを1つ決める"""
    for kw in CATEGORY_PRIMARY_ORDER:
        if kw in tags:
            return kw
    return "その他"


def detect_genres(title: str, body: str) -> list[str]:
    """タイトル＋本文からジャンルIDの一覧を返す"""
    text = f"{title}\n{body}"
    found: list[str] = []
    for genre_id, kws in GENRE_KEYWORDS.items():
        pos_hits = sum(text.count(kw) for kw in kws)
        if pos_hits == 0:
            continue
        neg_kws = GENRE_NEGATIVE_KEYWORDS.get(genre_id, ())
        neg_hits = sum(text.count(kw) for kw in neg_kws)
        if neg_kws and neg_hits >= pos_hits:
            continue
        found.append(genre_id)
    return found


def build_hashtags(category_primary: str, genres: list[str]) -> list[str]:
    """場所カテゴリ＋ジャンルから、推奨ハッシュタグの配列を作る（重複排除）

    注：curator.html 側で実際の投稿用ハッシュタグはユーザーが選択するため、
    ここで返す hashtags は「初期候補」として参考程度の意味合い。
    """
    tags: list[str] = []
    tags.extend(COMMON_HASHTAGS)
    if category_primary in LOCATION_HASHTAGS:
        tags.extend(LOCATION_HASHTAGS[category_primary])
    seen: set[str] = set()
    result: list[str] = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result


def enrich_event(ev: Event) -> Event:
    """Event に category_primary / genres / hashtags を計算してセットする"""
    ev.tags = sorted(set(ev.tags))
    ev.category_primary = determine_category_primary(ev.tags)
    ev.genres = detect_genres(ev.title, ev.body)
    if ev.is_kitchen_car and "kitchen_car" not in ev.genres:
        ev.genres.append("kitchen_car")
    ev.hashtags = build_hashtags(ev.category_primary, ev.genres)
    return ev


# ----------------------------------------------------------------------
# 永続化
# ----------------------------------------------------------------------
def _composite_key(source: str, eid: str) -> str:
    """events.json内での一意キー（source||id）。
    内部辞書のキーとして使う（JSON出力には現れない）。
    """
    return f"{source}||{eid}"


def load_existing() -> dict[str, dict]:
    """既存 events.json を読み、(source, id) をキーとする辞書を返す。
    旧形式（source未設定）のレコードは source='seiseki.org' を補完する。
    """
    if not EVENTS_JSON.exists():
        return {}
    with EVENTS_JSON.open(encoding="utf-8") as f:
        items = json.load(f)
    result: dict[str, dict] = {}
    for e in items:
        # 旧データのマイグレーション
        if "source" not in e or not e["source"]:
            e["source"] = "seiseki.org"
        result[_composite_key(e["source"], e["id"])] = e
    return result


def save_events(events_by_key: dict[str, dict]) -> None:
    """events.json に保存。開始日の新しい順に並べる。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    items = list(events_by_key.values())
    items.sort(key=lambda e: (e.get("date_start") or "0000"), reverse=True)
    with EVENTS_JSON.open("w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f"saved {len(items)} events -> {EVENTS_JSON}", file=sys.stderr)


def merge_events(existing: dict[str, dict],
                 new_events: list[Event],
                 source: str,
                 archive_missing: bool = True) -> None:
    """新規取得したイベント群を既存マップにマージする。

    - 同じ (source, id) があれば first_seen / image_local を保持して上書き
    - サイトから消えたものは archive_missing=True なら archived=True に
    - 他ソースのレコードには影響しない
    """
    seen_keys: set[str] = set()
    for ev in new_events:
        ev = enrich_event(ev)
        key = _composite_key(source, ev.id)
        seen_keys.add(key)
        ev_dict = asdict(ev)
        if key in existing:
            ev_dict["first_seen"] = existing[key].get("first_seen", ev_dict["first_seen"])
            if not ev_dict.get("image_local") and existing[key].get("image_local"):
                ev_dict["image_local"] = existing[key]["image_local"]
        existing[key] = ev_dict

    if archive_missing:
        for k, e in existing.items():
            if e.get("source") != source:
                continue  # 別ソースのレコードは触らない
            if k not in seen_keys:
                e["archived"] = True


# ----------------------------------------------------------------------
# 共通ヘルパー
# ----------------------------------------------------------------------
def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def parse_date_jp(text: str) -> tuple[str | None, str | None]:
    """日本語の日付テキストから ISO形式 (start, end) を抽出。
    各スクレイパーで使う共通関数。

    対応:
      "2026年5月10日（日）"
      "2026年4月23日（木）～26（日）"
      "2026年4月11日（土）～12日（日）"
      "2025年12月1日（月）～12月22日（月）"
    """
    if not text:
        return (None, None)

    # 範囲パターン
    # 終了側：「日」付きでも「日」省略でもOK。ただし時刻表記（XX:XX）は除外
    # 例: "2026年5月10日(日)11:00〜19:30" の "19:30" を「19日」と誤認しない
    # 例: "2026年4月23日（木）～26（日）" の "26" は終了日として正しく拾う
    # 終了側数字の直後に「数字」「コロン」が来ない（＝時刻表記でない）こと
    m = re.search(
        r"(\d{4})年(\d{1,2})月(\d{1,2})日.*?(?:～|〜|~)\s*(?:(\d{1,2})月)?(\d{1,2})日?(?!\d)(?!\s*[:：])",
        text,
    )
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        end_mo = int(m.group(4)) if m.group(4) else mo
        end_d = int(m.group(5))
        return (f"{y:04d}-{mo:02d}-{d:02d}", f"{y:04d}-{end_mo:02d}-{end_d:02d}")

    # 単発
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return (f"{y:04d}-{mo:02d}-{d:02d}", None)

    return (None, None)


def parse_keio_date(text: str, hint_year: int) -> tuple[str | None, str | None]:
    """京王系（keio-sc.jp / keionet.com）共通の日付表記をパース。
    年が省略されている場合は hint_year を使う。

    対応:
      "5月16日（土）・17日（日）"            → (HY-05-16, HY-05-17)
      "2026年4月1日(水)～2026年5月10日(日)"  → (2026-04-01, 2026-05-10)
      "4/29（水・祝）→5/6（水・振休）"        → (HY-04-29, HY-05-06)
      "5月7日（木）～5月13日（水）"           → (HY-05-07, HY-05-13)
      "5月3日（日・祝）～5月4日（月・祝）"     → (HY-05-03, HY-05-04)
      "4/30(木)→5/13(水)"                  → (HY-04-30, HY-05-13)
      "5/10(日)"                            → (HY-05-10, None)
      "12月25日（木）～1月10日（土）"         → (HY-12-25, HY+1-01-10)（年またぎ）
    """
    if not text:
        return (None, None)
    s = text.strip()

    # フル年付き範囲
    m = re.search(
        r"(\d{4})年(\d{1,2})月(\d{1,2})日.*?(?:～|〜|~|→).*?(\d{4})年(\d{1,2})月(\d{1,2})日",
        s,
    )
    if m:
        y1, mo1, d1 = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y2, mo2, d2 = int(m.group(4)), int(m.group(5)), int(m.group(6))
        return (f"{y1:04d}-{mo1:02d}-{d1:02d}",
                f"{y2:04d}-{mo2:02d}-{d2:02d}")

    # 開始だけ年付き
    m = re.search(
        r"(\d{4})年(\d{1,2})月(\d{1,2})日.*?(?:～|〜|~|→).*?(\d{1,2})月(\d{1,2})日",
        s,
    )
    if m:
        y1, mo1, d1 = int(m.group(1)), int(m.group(2)), int(m.group(3))
        mo2, d2 = int(m.group(4)), int(m.group(5))
        y2 = y1 if mo2 >= mo1 else y1 + 1
        return (f"{y1:04d}-{mo1:02d}-{d1:02d}",
                f"{y2:04d}-{mo2:02d}-{d2:02d}")

    # 年なし範囲（M月D日 ～ M月D日）
    m = re.search(
        r"(\d{1,2})月(\d{1,2})日.*?(?:～|〜|~|→).*?(\d{1,2})月(\d{1,2})日",
        s,
    )
    if m:
        mo1, d1 = int(m.group(1)), int(m.group(2))
        mo2, d2 = int(m.group(3)), int(m.group(4))
        y1 = hint_year
        y2 = y1 if mo2 >= mo1 else y1 + 1
        return (f"{y1:04d}-{mo1:02d}-{d1:02d}",
                f"{y2:04d}-{mo2:02d}-{d2:02d}")

    # 年なし範囲（M/D ～ M/D）
    m = re.search(
        r"(\d{1,2})/(\d{1,2}).*?(?:～|〜|~|→).*?(\d{1,2})/(\d{1,2})",
        s,
    )
    if m:
        mo1, d1 = int(m.group(1)), int(m.group(2))
        mo2, d2 = int(m.group(3)), int(m.group(4))
        y1 = hint_year
        y2 = y1 if mo2 >= mo1 else y1 + 1
        return (f"{y1:04d}-{mo1:02d}-{d1:02d}",
                f"{y2:04d}-{mo2:02d}-{d2:02d}")

    # 年なし範囲（M/D → D）の月省略：「5/1(金)→13(水)」
    # 開始の M/D に対して、終了側が「日だけ」のケース（同月扱い）
    # 例: "5/1(金)→13(水)" → start=5/1, end=5/13
    # ※ M/D → M/D のパターンの後に書く必要がある（先に書くとそちらにマッチしないため）
    m = re.search(
        r"(?<!\d)(\d{1,2})/(\d{1,2}).*?(?:～|〜|~|→)\s*\(?(\d{1,2})\b",
        s,
    )
    if m:
        mo1, d1 = int(m.group(1)), int(m.group(2))
        d2 = int(m.group(3))
        # 終了の日数が開始日より小さければ、翌月扱いになる
        # （例：5/28→3 は 6/3 とすべき）
        mo2 = mo1 if d2 >= d1 else mo1 + 1
        y1 = hint_year
        y2 = y1 if mo2 <= 12 else y1 + 1
        if mo2 > 12:
            mo2 -= 12
        return (f"{y1:04d}-{mo1:02d}-{d1:02d}",
                f"{y2:04d}-{mo2:02d}-{d2:02d}")

    # 年なし範囲（M月D日 → M月D日）の片方が日数省略：「5月7日（木）→13(水)」
    # 開始月のみ書かれて終了側が日だけ："5月7日(木)→13(水)"
    m = re.search(
        r"(\d{1,2})月(\d{1,2})日.*?(?:～|〜|~|→).*?(?:(\d{1,2})月)?(\d{1,2})日?",
        s,
    )
    if m:
        mo1, d1 = int(m.group(1)), int(m.group(2))
        mo2 = int(m.group(3)) if m.group(3) else mo1
        d2 = int(m.group(4))
        y1 = hint_year
        y2 = y1 if mo2 >= mo1 else y1 + 1
        return (f"{y1:04d}-{mo1:02d}-{d1:02d}",
                f"{y2:04d}-{mo2:02d}-{d2:02d}")

    # 年なし複数日："5月16日（土）・17日（日）" → 16〜17
    m = re.search(r"(\d{1,2})月(\d{1,2})日[^0-9]+(\d{1,2})日", s)
    if m:
        mo, d1, d2 = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return (f"{hint_year:04d}-{mo:02d}-{d1:02d}",
                f"{hint_year:04d}-{mo:02d}-{d2:02d}")

    # 年付き単発
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return (f"{y:04d}-{mo:02d}-{d:02d}", None)

    # 年なし単発「M月D日」
    m = re.search(r"(\d{1,2})月(\d{1,2})日", s)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        return (f"{hint_year:04d}-{mo:02d}-{d:02d}", None)

    # M/D 単発
    m = re.search(r"(?<!\d)(\d{1,2})/(\d{1,2})(?!\d)", s)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        return (f"{hint_year:04d}-{mo:02d}-{d:02d}", None)

    return (None, None)


def infer_status_by_date(date_start: str | None, date_end: str | None) -> str | None:
    """日付から「開催予定/開催中/終了」を推定（実行時の今日を基準）"""
    if not date_start:
        return None
    today = datetime.now().date().isoformat()
    end = date_end or date_start
    if today < date_start:
        return "開催予定"
    elif date_start <= today <= end:
        return "開催中"
    else:
        return "終了"


def download_image(session: requests.Session, url: str, dest_dir: Path) -> str | None:
    """画像をローカルにダウンロード。既存があればスキップ。
    ファイル名はURLから取り、危険な文字は除去する。

    URLが相対パスの場合は呼び出し側で絶対化してから渡すこと。
    """
    if not url:
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    from urllib.parse import unquote
    fname = unquote(url.split("/")[-1].split("?")[0])  # クエリパラメータは捨てる
    fname = re.sub(r"[^\w.\-]", "_", fname)
    if not fname or "." not in fname:
        # 拡張子がないURLは無理に保存しない
        return None
    path = dest_dir / fname
    if path.exists():
        return str(path)
    print(f"  IMG {url}", file=sys.stderr)
    try:
        r = session.get(url, timeout=REQUEST_TIMEOUT_SEC)
    except Exception as e:
        print(f"  ! image fetch failed: {e}", file=sys.stderr)
        return None
    if r.status_code == 200:
        path.write_bytes(r.content)
        time.sleep(REQUEST_INTERVAL_SEC * 0.5)
        return str(path)
    return None
