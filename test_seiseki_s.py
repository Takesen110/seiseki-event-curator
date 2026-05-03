#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scrapers/seiseki_s.py のテスト"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scrapers.seiseki_s import (
    parse_event_list_page, parse_event_detail, _infer_tags,
)


# 一覧ページHTMLの最小再現（実データを参考）
# 注：実サイトでは相対パス "evt_detail.asp?n=NNN" を使っている。
# 一覧ページのURLが /htm/ssr/ にあるため、相対パスは /htm/ssr/ からの相対。
LIST_HTML = """
<html><body>
<dl>
<dt>26/03/30掲載
  <a href="evt_detail.asp?n=202">第45回せいせき桜まつり</a>
  日時：全日5日（日） 10：00〜17：00（小雨一部決行）</dt>
<dd>概要：オープニングセレモニー、キッズダンス、生演奏ペア葛藤他<br>
  →<a href="evt_detail.asp?n=202">[詳細はこちらをクリック]</a></dd>

<dt>26/03/03掲載
  <a href="evt_detail.asp?n=200">文化フォーラム2026 〜中央自動車道〜</a>
  日時：2026年4月4日(土) 13:30〜16:00 (開場13時)</dt>
<dd>→<a href="evt_detail.asp?n=200">[詳細はこちらをクリック]</a></dd>

<dt>26/01/19掲載
  <a href="evt_detail.asp?n=198">バフと桜が奏でるふれあいコンサート開催のご案内</a>
  日時：2026年2月22日（日）開場 12：30 開演 13：00 終演予定15：30</dt>
<dd>→<a href="evt_detail.asp?n=198">[詳細はこちらをクリック]</a></dd>
</dl>
</body></html>
"""


def test_list_parse():
    items = parse_event_list_page(LIST_HTML)
    print(f"  found {len(items)} items")
    for it in items:
        print(f"    n={it['id']}  url={it['url']}")
        print(f"      title_hint={it['title_hint']!r}")
    assert len(items) == 3
    ns = [i["id"] for i in items]
    assert "202" in ns and "200" in ns and "198" in ns


# 詳細ページHTMLの最小再現
DETAIL_SAKURA_HTML = """
<html>
<head><title>--第45回せいせき桜まつり-- せいせきショップ.com編集</title></head>
<body>
<header><a href="/">トップ</a></header>
<main>
<h4>第45回せいせき桜まつり</h4>
<img src="/images/event/evt_2022026sakura.png">
<p>本部：京王聖蹟桜ヶ丘駅周辺...</p>

<h5>日時：</h5>
全日5日（日） 10：00〜17：00（小雨一部決行）<br>
スタンプラリー ゴール表彰：12:30〜16:00

<h5>場所：</h5>
京王聖蹟桜ヶ丘駅周辺 → 関戸通り商店街
<br>
「桜まつり実行委員会」関戸公民館
<br>
多摩中央信用金庫八王子支店の風船展：7Fロビー周り

<h5>主催</h5>
第45回せいせき桜まつり実行委員会 / 関戸商店会 / 一ノ宮商店会
聖蹟桜ヶ丘大通り商店会

<h5>共催</h5>
京王聖蹟桜ヶ丘ショッピングセンター ヴィータモールせいせき
スクエアSC

<h5>後援</h5>
多摩市 多摩市商工会議所 多摩市観光協会
</main>
</body></html>
"""


def test_detail_sakura():
    ev = parse_event_detail(
        "https://seiseki-s.com/htm/ssr/evt_detail.asp?n=202",
        DETAIL_SAKURA_HTML,
    )
    print(f"  id        = {ev.id}")
    print(f"  source    = {ev.source}")
    print(f"  title     = {ev.title}")
    print(f"  date      = {ev.date_start} ~ {ev.date_end}")
    print(f"  venue     = {ev.venue}")
    print(f"  organizer = {ev.organizer}")
    print(f"  time      = {ev.time_label}")
    print(f"  tags      = {ev.tags}")
    print(f"  image     = {ev.image_url}")
    assert ev.source == "seiseki-s.com"
    assert ev.id == "sssc-202"
    assert ev.title == "第45回せいせき桜まつり"
    assert ev.venue and "聖蹟桜ヶ丘駅周辺" in ev.venue
    assert ev.organizer and "実行委員会" in ev.organizer
    assert ev.organizer.startswith("第45回")  # 主催が取れたので接頭辞なし
    assert ev.time_label and ("5日" in ev.time_label or "10：00" in ev.time_label)
    assert ev.image_url and "evt_2022026sakura.png" in ev.image_url

    # カテゴリ：本文に「京王聖蹟桜ヶ丘ショッピングセンター」あり、
    # かつ「桜まつり実行委員会」「商店会」などの商店会系キーワードあり
    # → SC + まちなか の両方が付くのが望ましい
    print(f"  inferred tags: {ev.tags}")
    assert "ショッピングセンター" in ev.tags  # 共催にSCが入っている
    assert "まちなか" in ev.tags              # 主催が商店会系


# SC専用イベントの想定
DETAIL_SC_HTML = """
<html><head><title>--ヴィータモールせいせき大感謝祭--</title></head>
<body>
<h4>ヴィータモールせいせき大感謝祭</h4>
<img src="/images/event/vita_thanks.png">
<h5>日時：</h5>
2025年11月22日（土）〜12月21日（日）

<h5>場所：</h5>
ヴィータモールせいせき 各店舗

<h5>主催</h5>
ヴィータモールせいせき
</body></html>
"""


def test_detail_sc():
    ev = parse_event_detail(
        "https://seiseki-s.com/htm/ssr/evt_detail.asp?n=196",
        DETAIL_SC_HTML,
    )
    print(f"  title = {ev.title}")
    print(f"  date  = {ev.date_start} ~ {ev.date_end}")
    print(f"  tags  = {ev.tags}")
    assert ev.title == "ヴィータモールせいせき大感謝祭"
    assert ev.date_start == "2025-11-22"
    assert ev.date_end == "2025-12-21"
    # ヴィータモール → SC タグ
    assert "ショッピングセンター" in ev.tags
    # まちなかタグはついてないはず（SC専用の文脈）
    assert "まちなか" not in ev.tags


def test_infer_tags():
    # カワマチ系
    tags = _infer_tags("test", "せいせきカワマチで開催！", "多摩川河川敷")
    assert "せいせきカワマチ" in tags

    # SC系
    tags = _infer_tags("ヴィータモール開催", "京王プラザの2階で", None)
    assert "ショッピングセンター" in tags

    # まちなか（どちらでもない）
    tags = _infer_tags("商店街イベント", "聖蹟桜ヶ丘の商店街で開催", "関戸通り")
    assert "まちなか" in tags

    # 両方該当：両方つく
    tags = _infer_tags("test", "京王プラザと多摩川河川敷で連携イベント", None)
    assert "せいせきカワマチ" in tags
    assert "ショッピングセンター" in tags

    print("  infer_tags OK")


if __name__ == "__main__":
    print("=== list parse ===")
    test_list_parse()
    print("=== detail (桜まつり) ===")
    test_detail_sakura()
    print("=== detail (ヴィータモール) ===")
    test_detail_sc()
    print("=== infer_tags ===")
    test_infer_tags()
    print("\nAll seiseki_s tests passed.")
