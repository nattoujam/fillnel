# fillnel

RSSフィードから記事を収集し、Gemini Embeddingでプロファイルとの類似度をスコアリングして毎朝厳選。Raindrop.ioの未整理フォルダに届けるパーソナル記事レコメンダー。

気に入った記事をRaindropアプリでお気に入りフォルダに移動するだけで好みが学習され、翌朝の収集に反映される。

## 仕組み

毎朝バッチが以下を順に実行する：

1. **enrich** — お気に入りフォルダの記事に要約・タグを付与（Gemini呼び出し）
2. **rebuild_profile** — お気に入り全件からプロファイル（`data/profile.json`）を再構築し、Embeddingキャッシュを更新
3. **cleanup** — 未整理フォルダの前回記事を全件削除
4. **collect** — RSSフィードから記事を収集 → Embeddingスコアリング → Geminiフィルタリング
5. **register** — 収集した記事を未整理フォルダに登録

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

### RSSフィードの設定

`config/feeds.yml` に収集対象のRSSフィードURLを列挙する。

```yaml
feeds:
  # 技術メディア
  - https://zenn.dev/feed
  - https://qiita.com/popular-items/feed

  # Qiitaタグ別RSS
  - https://qiita.com/tags/rust/feed
```

CLIで管理することもできる：

```bash
# 一覧表示
uv run fillnel-feeds list

# 追加
uv run fillnel-feeds add https://example.com/feed

# 削除（URL or 番号）
uv run fillnel-feeds remove https://example.com/feed
uv run fillnel-feeds remove 3
```

### Raindrop.io の準備

Raindrop.io に以下のコレクションを用意する（名前は変更可）：

| コレクション | 用途 |
|---|---|
| 未整理（デフォルト） | 毎朝の推薦記事が届く |
| お気に入り | 保存したい記事を移動する |
| リンク切れ | リンク切れ検出バッチが自動移動 |

コレクション名は `fillnel/steps/__init__.py` の定数で設定する。

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
uv sync

# フルバッチ
uv run fillnel

# エンリッチ（要約・タグ付与）+ プロファイル再構築
uv run fillnel-enrich
uv run fillnel-enrich --force   # 既存タグも含めて全件再推定

# プロファイル再構築（Embeddingキャッシュも更新）
uv run fillnel-rebuild-profile

# RSSフィード管理
uv run fillnel-feeds list
uv run fillnel-feeds add <url>
uv run fillnel-feeds remove <url|index>

# リンク切れ検出
uv run fillnel-check-links

# 好みプロファイルの確認
uv run fillnel-profile

# テスト
uv run pytest
```

## 技術スタック

| 用途 | 技術 |
|---|---|
| RSS収集 | feedparser |
| Embeddingスコアリング | Gemini gemini-embedding-001 + numpy |
| 記事フィルタリング・タグ推定・要約生成 | Gemini 3.1 Flash Lite |
| ブックマーク管理 | Raindrop.io API |
| スケジューラ | Docker + systemd timer |
