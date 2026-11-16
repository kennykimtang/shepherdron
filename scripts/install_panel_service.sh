#!/usr/bin/env bash
# 기체 제어판을 부팅할 때 자동으로 띄운다. 라즈베리파이에서 한 번만 실행.
#
#   bash scripts/install_panel_service.sh
#
# SSH 창을 닫아도, 전원을 뺐다 넣어도 계속 돈다. 죽으면 3 초 뒤 되살아난다.
# 시연 당일 전원만 넣으면 영상이 바로 나오게 하려는 것이다.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME="$(id -un)"
ARGS="${PANEL_ARGS:-}"

sudo tee /etc/systemd/system/shepherdron-panel.service >/dev/null <<SERVICE
[Unit]
Description=Shepherdron 기체 제어판 (카메라 · 전개 구동부 · FC 링크)
After=network-online.target
Wants=network-online.target

[Service]
User=${USER_NAME}
WorkingDirectory=${REPO}
ExecStart=/usr/bin/python3 ${REPO}/scripts/panel.py ${ARGS}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable --now shepherdron-panel
sleep 2
systemctl --no-pager --lines=5 status shepherdron-panel || true

cat <<MSG

─────────────────────────────────────────────
  http://$(hostname).local:8080        비전 데모 (기체 카메라 포함)
  http://$(hostname).local:8080/panel  카메라 · 구동부 · FC 링크

  멈추기   sudo systemctl stop shepherdron-panel
  다시     sudo systemctl start shepherdron-panel
  로그     journalctl -u shepherdron-panel -f
  자동시작 끄기  sudo systemctl disable shepherdron-panel

  루프백 시험처럼 /dev/ttyAMA0 을 직접 쓸 때는 먼저 멈추세요.
─────────────────────────────────────────────
MSG
