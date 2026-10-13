#!/usr/bin/env bash
# ArduPilot SITL(가상 기체) 기동 — 하드웨어 없이 비행 로직을 검증한다.
#
# 최초 1회 설치
#     git clone --recurse-submodules https://github.com/ArduPilot/ardupilot.git ~/ardupilot
#     cd ~/ardupilot && Tools/environment_install/install-prereqs-mac.sh -y   # Linux 는 install-prereqs-ubuntu.sh
#     . ~/.profile
#
# 사용법
#     ./scripts/run_sitl.sh                 # 기본 위치(연세대 신촌)에서 기동
#     ./scripts/run_sitl.sh --console --map
#
# 기동되면 다른 터미널에서:
#     python -m flight.sitl_demo
set -euo pipefail

ARDUPILOT_DIR="${ARDUPILOT_DIR:-$HOME/ardupilot}"
# 연세대 신촌캠퍼스 (위도,경도,고도,기수)
HOME_LOCATION="${HOME_LOCATION:-37.5665,126.9388,30,0}"

if [[ ! -d "$ARDUPILOT_DIR" ]]; then
  cat <<MSG
ArduPilot 소스를 찾을 수 없습니다: $ARDUPILOT_DIR

설치:
    git clone --recurse-submodules https://github.com/ArduPilot/ardupilot.git ~/ardupilot
    cd ~/ardupilot && Tools/environment_install/install-prereqs-mac.sh -y
    . ~/.profile

다른 경로에 있다면:  ARDUPILOT_DIR=/path/to/ardupilot ./scripts/run_sitl.sh
MSG
  exit 1
fi

echo "▶ SITL 기동 — ArduCopter @ $HOME_LOCATION"
echo "  MAVLink 출력: udp:127.0.0.1:14550"
echo

cd "$ARDUPILOT_DIR"
exec Tools/autotest/sim_vehicle.py \
  -v ArduCopter \
  --custom-location="$HOME_LOCATION" \
  --out=udp:127.0.0.1:14550 \
  "$@"
