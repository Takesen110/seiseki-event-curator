# seiseki curator

聖蹟桜ヶ丘エリアのイベント情報を1か所で見られるサイト。

> 多摩市・聖蹟桜ヶ丘エリアで開催されるイベント情報を、複数のウェブサイトから自動収集し、
> ひとつのページで横断的に閲覧できるツールです。地域の友人たちと情報を共有するための個人プロジェクトとして公開しています。

**サイト**: https://takesen110.github.io/seiseki-event-curator/

## 特徴

- 聖蹟桜ヶ丘エリアの主要情報源（**8 サイト + 神社年中行事**）から自動取得
- 期間中・予定のイベントのみ表示するフィルタ
- カテゴリ（カワマチ／まちなか／ショッピングセンター）、ジャンル（family / culture など）、ソース別の絞り込み
- 採用判定機能（採用 / 後で / 不採用）はブラウザのローカル保存（共有されません）
- SNS投稿テキストの下書き生成機能つき
- 月・水・土の朝6時JSTに自動更新

## 取得元

| ソース | 内容 |
|---|---|
| [聖蹟桜ヶ丘エリアマネジメント (seiseki.org)](https://seiseki.org/) | せいせきカワマチ・まちなかイベント全般 |
| [京王聖蹟桜ヶ丘ショッピングセンター (keio-sc.jp)](https://www.keio-sc.jp/seiseki/) | SCのイベント |
| [京王百貨店 聖蹟桜ヶ丘店 (keionet.com)](https://www.keionet.com/info/seiseki/) | 催事情報 |
| [聖蹟桜ヶ丘ショップドットコム (seiseki-s.com)](http://seiseki-s.com/) | 商店会連合会のイベント |
| [せいせき観光まちづくり会議 (seiseki.tokyo)](https://seiseki.tokyo/) | 地域の文化イベント |
| [ザ・スクエア聖蹟桜ヶ丘 (square-sc.com)](https://square-sc.com/) | SCのショップニュース |
| [ヴィータモールせいせき (vitamallseiseki.jp)](https://vitamallseiseki.jp/) | SCのイベント |
| [多摩ポン (tamapon.com)](https://tamapon.com/) | 地域メディア（聖蹟桜ヶ丘エリアに絞り込み） |
| 神社の年中行事（手動メンテ） | 小野神社、関戸熊野神社、金比羅宮、九頭龍神社、連光寺白山神社 |

## 権利・利用について

- 各イベント情報の権利は元サイト・主催者に帰属します
- 画像は元サイトの画像URLを直接参照する形式で表示しています（このリポジトリには画像を保存していません）
- 神社の年中行事は推定日程です。実施日時は各神社の公式サイトでご確認ください
- もし掲載に不快に思われた場合や、「うちの情報は載せないでほしい」というご希望があれば、
  [GitHub Issues](https://github.com/Takesen110/seiseki-event-curator/issues) でご一報ください。速やかに対応します

## 他のまちで使う

スクレイパーは MIT ライセンスです。fork して別の地域で使っていただけます。
基本的な改造手順：

1. `scrapers/` 配下の各スクレイパーを、対象地域の情報源に合わせて修正
2. `scrapers/jinja_recurring.py` のデータ（`data/recurring_jinja.json`）も置き換え
3. `run_all.py` の `SOURCES` を更新
4. `.github/workflows/scrape.yml` の cron を好きな頻度に
5. `index.html` 内のフッター、`README.md` を地域名に書き換え

## 技術構成

- スクレイピング: Python 3.11 + `requests` + `beautifulsoup4`
- 自動更新: GitHub Actions（月・水・土 06:00 JST）
- フロントエンド: 単一HTML（外部依存なし）
- ホスティング: GitHub Pages

## ローカルで実行

```bash
# 依存インストール
pip install -r requirements.txt

# 全ソース取得
python run_all.py

# 特定ソースだけ
python run_all.py --sources seiseki.org keio-sc.jp

# データ確認
python check_events.py

# ブラウザで確認（要HTTPサーバー、ファイルfetch のため）
python -m http.server 8000
# → http://localhost:8000/index.html
```

## ライセンス

MIT License - [LICENSE](LICENSE) を参照

---

Made by [Takesen](https://github.com/Takesen110/) — 聖蹟桜ヶ丘在住、地域の友人たちと使うために
