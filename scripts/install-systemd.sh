#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SERVICES_DIR="$PROJECT_DIR/services"
SYSTEMD_DIR="/etc/systemd/system"
SERVICE_NAME="article-recommender"

echo "=== fillnel systemd セットアップ ==="
echo "プロジェクトディレクトリ: $PROJECT_DIR"
echo ""

# WorkingDirectory をインストール先の実際のパスに書き換える
sed "s|WorkingDirectory=.*|WorkingDirectory=$PROJECT_DIR|" \
    "$SERVICES_DIR/$SERVICE_NAME.service" \
    | sudo tee "$SYSTEMD_DIR/$SERVICE_NAME.service" > /dev/null

sudo cp "$SERVICES_DIR/$SERVICE_NAME.timer" "$SYSTEMD_DIR/$SERVICE_NAME.timer"

echo "ファイルをコピーしました:"
echo "  $SYSTEMD_DIR/$SERVICE_NAME.service"
echo "  $SYSTEMD_DIR/$SERVICE_NAME.timer"
echo ""

sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE_NAME.timer"

echo ""
echo "=== セットアップ完了 ==="
sudo systemctl status "$SERVICE_NAME.timer" --no-pager
echo ""
echo "次回実行予定:"
systemctl list-timers "$SERVICE_NAME.timer" --no-pager
