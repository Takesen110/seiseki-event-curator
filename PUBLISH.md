# GitHub Pages 公開手順書（武仙さん向け）

## 前提
- GitHubアカウント: [Takesen110](https://github.com/Takesen110/)
- リポジトリ名: `seiseki-event-curator`
- 公開URL: `https://takesen110.github.io/seiseki-event-curator/`

## ローカル準備

```powershell
cd C:\Users\takes\claude\event-curator\seiseki-curator

# 1. step7のzipを展開
Expand-Archive -Path seiseki-curator-step7.zip -DestinationPath . -Force

# 2. ファイル確認
ls
# 期待値:
# - .github/workflows/scrape.yml
# - data/events.json, data/recurring_jinja.json
# - scrapers/ (10ファイル)
# - index.html, curator.html
# - README.md, LICENSE, requirements.txt, .gitignore
# - run_all.py, check_events.py
# - test_*.py 多数

# 3. キャッシュ削除
Remove-Item -Recurse -Force scrapers\__pycache__ -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force __pycache__ -ErrorAction SilentlyContinue

# 4. 全ソース取得（公開前に最新状態にしておく）
python run_all.py
# → "Counter(...)" で全9ソースの件数を確認
```

## GitHub リポジトリ作成

ブラウザで以下を実行：

1. https://github.com/new にアクセス
2. リポジトリ設定：
   - **Repository name**: `seiseki-event-curator`
   - **Description**: `聖蹟桜ヶ丘エリアのイベント情報を1か所で見られるサイト`
   - **Public** を選択
   - **Add a README file**: チェック**しない**（既にあるため）
   - **Add .gitignore**: None
   - **Choose a license**: None（既にあるため）
3. 「Create repository」をクリック

## 初回push（コマンドプロンプト or PowerShell）

```powershell
cd C:\Users\takes\claude\event-curator\seiseki-curator

# Git 初期化（既に .git があれば不要）
git init
git branch -M main

# リモート登録
git remote add origin https://github.com/Takesen110/seiseki-event-curator.git

# 全ファイル追加（.gitignoreで data/images は除外される）
git add .
git status   # 追加内容を確認

# 初回コミット
git commit -m "initial commit: seiseki curator with 9 sources"

# push
git push -u origin main
```

## GitHub Pages 有効化

1. リポジトリページで **Settings** タブをクリック
2. 左メニュー **Pages** をクリック
3. **Build and deployment** セクション：
   - **Source**: `Deploy from a branch` を選択
   - **Branch**: `main` / `/ (root)` を選択
   - **Save** をクリック
4. 数分待つと、ページ上部に
   `Your site is live at https://takesen110.github.io/seiseki-event-curator/`
   と表示されます
5. URLにアクセスして、イベント一覧が表示されればOK

## GitHub Actions 動作確認

### Actions の権限設定

1. リポジトリの **Settings** → 左メニュー **Actions** → **General**
2. **Workflow permissions** セクション：
   - **Read and write permissions** を選択
   - **Save** をクリック

これをやらないと、Actionsが events.json を自動コミットできません。

### 初回手動実行

1. リポジトリの **Actions** タブをクリック
2. 左メニュー **Scrape and update events** をクリック
3. 右上の **Run workflow** ボタン → **Run workflow** で実行
4. 数分後、緑のチェックがついて、コミットが自動で増えます
5. これ以降は **月・水・土の朝6時JST** に自動実行されます

## 動作確認

- https://takesen110.github.io/seiseki-event-curator/ にブラウザでアクセス
- イベント一覧が出ているか確認
- フィルタ（場所カテゴリ、ソース等）が動くか確認
- 神社系イベント（例：関戸熊野神社 例大祭）に「※ 日程は変動します...」のバッジが出るか確認

## トラブルシューティング

### Pagesのページが「404」になる
- Settings → Pages で `main` / `/ (root)` が選択されているか確認
- 数分待つ（初回は10分くらいかかることも）
- index.html が main ブランチのルートにあるか確認

### Actions が失敗する
- Actions タブで失敗したジョブをクリック → エラー内容を確認
- 多くは「scraperの構造が変わった」「サーバーが一時的にダウン」など。手動で再実行で直ることが多い

### Actions が自動コミットできない
- Settings → Actions → General → **Read and write permissions** が選択されているか確認

### 一部のサイトが取れていない
- ローカルで `python run_all.py --sources <該当ソース>` を実行してエラー確認
- サイト構造が変わった場合は `scrapers/<該当>.py` を修正

## 運用Tips

### 神社の年中行事を更新したいとき
- `data/recurring_jinja.json` を直接編集
- `git commit && git push` で反映

### 新しいソースを追加したいとき
- `scrapers/` に新しいファイルを追加
- `run_all.py` の `SOURCES` に登録
- 単体テスト書いて確認 → push

### スケジュール変更したいとき
- `.github/workflows/scrape.yml` の `cron` を編集
  - `0 21 * * 0,2,5` = 月・水・土 06:00 JST
  - 例: 毎日にしたい → `0 21 * * *`
  - 例: 朝・夕にしたい → `0 21,9 * * *`
