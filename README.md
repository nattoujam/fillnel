# fillnel

Gemini APIのWeb検索機能で毎朝記事を厳選収集し、Raindrop.ioの未整理フォルダに登録するパーソナル記事レコメンダー。

## セットアップ

```bash
# 依存パッケージのインストール
poetry install

# 環境変数の設定
cp .env.example .env
# .env を編集して GEMINI_API_KEY, RAINDROP_TOKEN を設定
```

## コマンド一覧

| コマンド | 説明 |
|---|---|
| `poetry run fillnel` | フルバッチ（毎日実行） |
| `poetry run fillnel-learn` | 学習ステップのみ |
| `poetry run fillnel-learn --force` | 全件タグ再推定（既存タグも上書き） |
| `poetry run fillnel-link-check` | リンク切れ検出 |
| `poetry run fillnel-profile` | 学習プロファイル確認 |

## バッチ詳細

### フルバッチ（毎日実行）

```bash
poetry run fillnel
```

以下のステップを順に実行します：

1. **learn** — お気に入りフォルダの記事にタグを付与し、好みプロファイルを更新
2. **cleanup** — 未整理フォルダの前回記事を全件削除
3. **collect** — Gemini + Google Search で新記事を5件収集
4. **register** — 収集した記事を未整理フォルダに登録

### 学習ステップのみ

```bash
poetry run fillnel-learn           # タグなし記事のみ処理
poetry run fillnel-learn --force   # 全件タグを再推定（既存タグも上書き）
```

お気に入りフォルダの記事を対象に以下を実行します：

- タグが未設定の記事にGeminiでタグを推定・付与（`--force` 時は全件再推定）
- 全記事のタグで好みプロファイル（`data/profile.json`）を更新

### リンク切れ検出

```bash
poetry run fillnel-link-check
```

全ブックマーク（未整理・リンク切れフォルダを除く）のURLを確認し、404/410を返した記事を「リンク切れ」フォルダに移動します。

### プロファイル確認

```bash
poetry run fillnel-profile
```

学習済みの興味プロファイルを表示します。タグを重み順にバー付きで一覧表示し、記事収集に使われる上位5タグをハイライトします。

## ユーザー操作

| 操作 | 説明 |
|---|---|
| 未整理フォルダの記事を読む | 毎朝届く推薦記事 |
| 気に入った記事をお気に入りフォルダへ移動 | 翌朝のバッチで学習される |
| 移動しなかった記事 | 翌朝のバッチで自動削除 |

## 環境変数

| 変数名 | 説明 |
|---|---|
| `GEMINI_API_KEY` | Gemini API キー |
| `RAINDROP_TOKEN` | Raindrop.io アクセストークン |
| `PROFILE_PATH` | プロファイルJSONのパス（デフォルト: `data/profile.json`） |
