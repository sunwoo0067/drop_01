#!/bin/bash
# OwnerClan Ops 설치 스크립트 (Systemd 등록)
set -e

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
SYSTEMD_DIR="/etc/systemd/system"

echo "[INFO] Installing OwnerClan sync services from $PROJECT_ROOT"

# 1. 템플릿 파일 복사 및 경로 치환
install_template() {
    local src=$1
    local dest=$2
    echo "[INFO] Configuring $dest..."
    sed "s|/home/sunwoo/project/drop/drop_01/drop_01_dev|$PROJECT_ROOT|g" "$src" | \
    sed "s|User=sunwoo|User=$(whoami)|g" | \
    sed "s|Group=sunwoo|Group=$(id -gn)|g" > "/tmp/$(basename "$dest")"
    
    sudo mv "/tmp/$(basename "$dest")" "$dest"
}

install_template "deploy/systemd/sync@.service" "$SYSTEMD_DIR/sync@.service"
install_template "deploy/systemd/sync@.timer" "$SYSTEMD_DIR/sync@.timer"

# 2. 시스템디 리로드
sudo systemctl daemon-reload

# 3. 채널별 타이머 활성화 (예시 구성)
setup_channel() {
    local channel=$1
    local interval=$2
    echo "[INFO] Setting up channel: $channel (Interval: $interval)"
    
    # 타이머 파일 커스텀 (주기 조정이 필요한 경우 drop-in 사용 가능하지만 여기서는 간단히 설명)
    # 실제 운영에서는 서비스별로 타이머 주기를 다르게 설정하는 것이 좋음
    sudo systemctl enable --now "sync@${channel}.timer"
}

echo "----------------------------------------------------"
echo "설치가 완료되었습니다. 아래 명령어로 채널을 활성화하세요:"
echo "sudo systemctl enable --now sync@items.timer   (15분 권장)"
echo "sudo systemctl enable --now sync@orders.timer  (1분 권장)"
echo "sudo systemctl enable --now sync@qna.timer     (5분 권장)"
echo "----------------------------------------------------"
echo "상태 확인: systemctl list-timers 'sync*'"
echo "로그 확인: journalctl -u sync@items.service -f"
