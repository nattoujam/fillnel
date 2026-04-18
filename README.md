# fillnel

Gemini APIのGoogle Search groundingで毎朝記事を厳選収集し、Raindrop.ioの未整理フォルダに届けるパーソナル記事レコメンダー。

気に入った記事をRaindropアプリでお気に入りフォルダに移動するだけで好みが学習され、翌朝の収集に反映される。

## 仕組み

毎朝バッチが以下を順に実行する：

1. **learn** — お気に入りフォルダの記事にタグを付与し、好みプロファイル（`data/profile.json`）を更新
2. **cleanup** — 未整理フォルダの前回記事を全件削除
3. **collect** — Gemini + Google Search で新記事を収集
4. **register** — 収集した記事を未整理フォルダに登録

ユーザーは毎朝届く記事を読み、気に入ったものをお気に入りフォルダに移動するだけでよい。移動しなかった記事は翌朝自動で削除される。

## セットアップ

### 環境変数

```bash
cp .env.example .env
# .env を編集して各キーを設定
```

| 変数名 | 説明 |
|---|---|
| `GEMINI_API_KEY` | Gemini API キー |
| `RAINDROP_TOKEN` | Raindrop.io アクセストークン |
| `PROFILE_PATH` | プロファイルJSONのパス（デフォルト: `data/profile.json`） |

### Raindrop.io の準備

Raindrop.io に以下のコレクションを用意する（名前は変更可）：

| コレクション | 用途 |
|---|---|
| 未整理（デフォルト） | 毎朝の推薦記事が届く |
| お気に入り | 保存したい記事を移動する |
| リンク切れ | リンク切れ検出バッチが自動移動 |

お気に入りコレクション名は `fillnel/steps/__init__.py` の `FAVORITE_COLLECTION` で設定する。

## デプロイ（Docker + systemd）

### 初回セットアップ

```bash
# systemd タイマーをインストール（毎朝6時に自動実行）
./scripts/install-systemd.sh
```

### 手動実行

```bash
docker compose run --rm batch
```

### タイマーの確認・操作

```bash
# 次回実行予定を確認
systemctl list-timers article-recommender.timer

# 今すぐ実行
sudo systemctl start article-recommender.service

# タイマーを無効化
sudo systemctl disable --now article-recommender.timer
```

## ローカル開発

```bash
# 依存パッケージのインストール
poetry install

# フルバッチ
poetry run fillnel

# 学習ステップのみ
poetry run fillnel-learn
poetry run fillnel-learn --force   # 既存タグも含めて全件再推定

# リンク切れ検出
poetry run fillnel-link-check

# 好みプロファイルの確認
poetry run fillnel-profile
```

## 技術スタック

| 用途 | 技術 |
|---|---|
| 記事収集 | Gemini 2.5 Flash + Google Search grounding |
| タグ推定 | Gemini 2.5 Flash Lite |
| ブックマーク管理 | Raindrop.io API |
| スケジューラ | Docker + systemd timer |
