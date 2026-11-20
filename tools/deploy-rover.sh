#!/usr/bin/env bash
#
# deploy-rover.sh - build + test the ROS 2 workspace (ros_ws), push it to the
# Rover's Raspberry Pi, build + test it there, make it the active version and
# reboot the Pi, so rover.service starts the new stack.
#
#   tools/deploy-rover.sh                 full run: local -> Pi -> activate -> reboot
#   tools/deploy-rover.sh --build-only    stop after the Pi build/test (nothing changes on the Rover)
#   tools/deploy-rover.sh --no-reboot     activate and restart rover.service instead of rebooting
#   tools/deploy-rover.sh --rollback      go back to the previous version, reboot
#   tools/deploy-rover.sh --status        what is installed / running on the Pi
#
# Options: --skip-local (no local build/test), --lint (style tests must pass too),
#          --host user@host (default $ROVER_SSH or cbm@rover101.local)
#
# On the Pi (nothing in ~/rover is touched):
#   ~/rover_ws/releases/<time>-<git sha>/   src, build, install, DEPLOY_INFO per version
#   ~/rover_ws/current  -> the version rover.service runs
#   ~/rover_ws/previous -> the one before (for --rollback)
# A version only becomes "current" after it built and passed its tests ON the Pi.
# The steps that need sudo (install rover.service, reboot) ask for the Pi's
# sudo password once.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WS="$ROOT/ros_ws"
HOST="${ROVER_SSH:-cbm@rover101.local}"
KEEP_RELEASES=5
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=5 -o ServerAliveInterval=5 -o ServerAliveCountMax=3)

MODE=deploy        # deploy | build-only | rollback | status
REBOOT=1
LOCAL=1
LINT=0

usage() { sed -n '3,25p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --build-only) MODE=build-only ;;
    --rollback)   MODE=rollback ;;
    --status)     MODE=status ;;
    --no-reboot)  REBOOT=0 ;;
    --skip-local) LOCAL=0 ;;
    --lint)       LINT=1 ;;
    --host)       HOST="${2:?--host needs user@host}"; shift ;;
    -h|--help)    usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

# ------------------------------------------------------------------ output
if [[ -t 1 ]]; then B=$'\e[1m'; G=$'\e[32m'; Y=$'\e[33m'; R=$'\e[31m'; N=$'\e[0m'; else B= G= Y= R= N=; fi
step() { echo; echo "${B}==> $*${N}"; }
ok()   { echo "${G}ok${N}  $*"; }
warn() { echo "${Y}warning:${N} $*"; }
die()  { echo "${R}error:${N} $*" >&2; exit 1; }

rsh()  { ssh "${SSH_OPTS[@]}" "$HOST" "$@"; }     # non-interactive
rsh_t(){ ssh -t -o ConnectTimeout=5 "$HOST" "$@"; } # interactive (sudo password)

# Runs on the Pi with ROS sourced, the same environment rover.service uses.
REMOTE_ENV='source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_DISCOVERY_SERVER=127.0.0.1:11811'

# ------------------------------------------------------------------ helpers
# colcon test, functional tests only (ament style checks are marked "linter").
# Fails if any test failed. With --lint the style checks have to pass as well.
# Used locally and (as text) on the Pi.
TEST_FN='
run_tests() {
  local lint="$1"; shift
  colcon test-result --delete-yes >/dev/null 2>&1 || true
  colcon test "$@" --event-handlers console_direct- \
       --pytest-args -m "not linter" --ctest-args -LE linter >/dev/null 2>&1 || true
  local out rc
  echo "  functional tests:"
  out="$(colcon test-result --verbose 2>&1)"; rc=$?
  printf "%s\n" "$out" | tail -25 | sed "s/^/    /"
  [ "$rc" = 0 ] || return 1
  colcon test-result --delete-yes >/dev/null 2>&1 || true
  colcon test "$@" --event-handlers console_direct- \
       --pytest-args -m linter --ctest-args -L linter >/dev/null 2>&1 || true
  out="$(colcon test-result 2>&1)"; rc=$?
  if [ "$rc" = 0 ]; then
    echo "  style checks (lint): all passed"
  elif [ "$lint" = 1 ]; then
    echo "  style checks (lint): FAILED (--lint)"; printf "%s\n" "$out" | tail -10 | sed "s/^/    /"; return 1
  else
    echo "  style checks (lint): some fail (not blocking, use --lint to enforce):"
    printf "%s\n" "$out" | grep -vE " 0 errors, 0 failures|^$" | tail -10 | sed "s/^/    /"
  fi
}'
eval "$TEST_FN"

version_lt() { [[ "$1" != "$2" && "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -1)" == "$1" ]]; }

# Packages that need a newer OpenCV than this machine has (charuco_detector
# needs 4.7, Ubuntu 24.04 has 4.6). They are still built and tested on the Pi.
local_skips() {
  local have req pkg
  have="$(pkg-config --modversion opencv4 2>/dev/null || echo 0)"
  for cm in "$WS"/src/*/CMakeLists.txt; do
    req="$(sed -n 's/^[[:space:]]*find_package(OpenCV[[:space:]]\+\([0-9][0-9.]*\).*/\1/p' "$cm" | head -1)"
    pkg="$(basename "$(dirname "$cm")")"
    if [[ -n "$req" ]] && version_lt "$have" "$req"; then echo "$pkg"; fi
  done
}

show_status() {
  rsh "$REMOTE_ENV"'
    cd ~/rover_ws 2>/dev/null || { echo "  nothing deployed yet (~/rover_ws missing)"; exit 0; }
    for l in current previous; do
      if [ -L $l ]; then printf "  %-9s %s\n" "$l:" "$(basename "$(readlink $l)")"; fi
    done
    echo "  releases:  $(ls releases 2>/dev/null | wc -l) kept in ~/rover_ws/releases"
    printf "  rover.service: %s / %s\n" "$(systemctl is-enabled rover 2>/dev/null || echo not-installed)" "$(systemctl is-active rover 2>/dev/null)"
    [ -f current/DEPLOY_INFO ] && sed "s/^/  /" current/DEPLOY_INFO
    true'
}

# ------------------------------------------------------------------ status
step "Rover: $HOST"
rsh true 2>/dev/null || die "cannot reach $HOST over ssh (Pi off? mDNS name? try --host cbm@<ip>)"
ok "ssh to $HOST works"

if [[ "$MODE" == status ]]; then
  show_status
  exit 0
fi

# ------------------------------------------------------------------ rollback
activate_and_restart() {   # installs/updates rover.service, then reboots or restarts it
  local unit_tmp
  unit_tmp="$(mktemp)"
  local ruser rhome
  ruser="$(rsh 'id -un')"; rhome="$(rsh 'echo $HOME')"
  sed -e "s|@USER@|$ruser|g" -e "s|@HOME@|$rhome|g" "$ROOT/tools/rover.service" > "$unit_tmp"
  rsh 'mkdir -p ~/rover_ws && cat > ~/rover_ws/rover.service' < "$unit_tmp"
  rm -f "$unit_tmp"

  local boot_before
  boot_before="$(rsh 'cat /proc/sys/kernel/random/boot_id')"
  local final="systemctl restart rover"
  [[ "$REBOOT" == 1 ]] && final="systemctl reboot"
  step "Install rover.service and $([[ "$REBOOT" == 1 ]] && echo reboot || echo restart) (sudo on the Pi)"
  # One sudo session: the password is asked once
  rsh_t "sudo sh -c '
    set -e
    if ! cmp -s $rhome/rover_ws/rover.service /etc/systemd/system/rover.service 2>/dev/null; then
      cp $rhome/rover_ws/rover.service /etc/systemd/system/rover.service
      systemctl daemon-reload
      echo \"rover.service installed/updated\"
    fi
    systemctl enable rover >/dev/null 2>&1
    # rover.launch.py includes stm32_link: the stand-alone service would fight over the port
    if systemctl is-enabled stm32_link >/dev/null 2>&1; then
      systemctl disable --now stm32_link && echo \"stm32_link.service disabled (now part of rover.service)\"
    fi
    $final
  '" || {
    rc=$?
    # 255 = connection closed, expected when the Pi reboots under us
    [[ "$REBOOT" == 1 && "$rc" == 255 ]] || die "sudo step failed on the Pi (exit $rc) - wrong password?"
  }

  if [[ "$REBOOT" == 1 ]]; then
    step "Waiting for the Pi to reboot"
    local deadline=$((SECONDS + 180)) boot_now=""
    while (( SECONDS < deadline )); do
      boot_now="$(rsh 'cat /proc/sys/kernel/random/boot_id' 2>/dev/null || true)"
      [[ -n "$boot_now" && "$boot_now" != "$boot_before" ]] && break
      sleep 3
    done
    [[ -n "$boot_now" && "$boot_now" != "$boot_before" ]] || die "the Pi did not come back rebooted within 3 minutes"
    ok "Pi rebooted and is back"
  fi

  step "Checking rover.service"
  local i state=""
  for i in $(seq 1 30); do
    state="$(rsh 'systemctl is-active rover' 2>/dev/null || true)"
    [[ "$state" == active ]] && break
    sleep 2
  done
  [[ "$state" == active ]] || { rsh 'journalctl -u rover -b --no-pager | tail -30' || true; die "rover.service is '$state'"; }
  sleep 8   # let the nodes start and the STM32 link do its first INFO
  ok "rover.service is running"
  show_status
  echo "  last log lines:"
  rsh 'journalctl -u rover -b --no-pager -o cat | tail -12 | sed "s/^/    /"' || true
  echo "  nodes:"
  rsh "$REMOTE_ENV"'
    export ROS_SUPER_CLIENT=TRUE
    timeout 25 ros2 node list --no-daemon --spin-time 8 2>/dev/null | sed "s/^/    /"
    echo "  STM32:"
    timeout 15 ros2 topic echo --once /stm32_link/firmware_info 2>/dev/null \
      | grep -E "^(state|running|running_version|confirmed):" | sed "s/^/    /" || echo "    (no firmware_info yet)"' || true
  echo
  ok "done - from the PC: rover-on, then ros2 topic list"
}

if [[ "$MODE" == rollback ]]; then
  step "Rollback to the previous version"
  rsh 'cd ~/rover_ws 2>/dev/null && [ -L previous ] && [ -d "$(readlink previous)" ]' \
    || die "no previous version on the Pi to go back to"
  rsh 'cd ~/rover_ws && cur=$(readlink current) && prev=$(readlink previous) &&
       ln -sfn "$prev" current && ln -sfn "$cur" previous &&
       echo "  current : $(basename "$prev")" && echo "  previous: $(basename "$cur")"'
  activate_and_restart
  exit 0
fi

# ------------------------------------------------------------------ 1. local
cd "$WS"
set +u; source /opt/ros/jazzy/setup.bash; set -u
SHA="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo nogit)"
DIRTY=""
[[ -n "$(git -C "$ROOT" status --porcelain -- ros_ws/src tools 2>/dev/null)" ]] && DIRTY="-dirty"
RELEASE="$(date +%Y%m%d-%H%M%S)-$SHA$DIRTY"

if [[ "$LOCAL" == 1 ]]; then
  step "1/4 Local build ($WS)"
  mapfile -t SKIP < <(local_skips)
  SKIP_ARGS=()
  if (( ${#SKIP[@]} )); then
    SKIP_ARGS=(--packages-skip "${SKIP[@]}")
    warn "skipped here, needs a newer OpenCV than $(pkg-config --modversion opencv4): ${SKIP[*]} (built on the Pi)"
  fi
  mkdir -p "$WS/log"
  if ! colcon build "${SKIP_ARGS[@]}" --event-handlers console_cohesion- console_direct- > "$WS/log/deploy_build.out" 2>&1; then
    tail -30 "$WS/log/deploy_build.out"; die "local build failed (ros_ws/log/latest_build)"
  fi
  tail -2 "$WS/log/deploy_build.out" | sed 's/^/  /'
  ok "built"

  step "2/4 Local tests"
  run_tests "$LINT" "${SKIP_ARGS[@]}" || die "local tests failed"
  set +u; source install/setup.bash; set -u
  ros2 launch rover_bringup rover.launch.py --show-args >/dev/null || die "rover.launch.py does not load"
  ok "tests passed, rover.launch.py loads"
else
  warn "--skip-local: no local build/test"
fi

# ------------------------------------------------------------------ 2. Pi
step "3/4 Pi: upload, build and test $RELEASE"
REL="rover_ws/releases/$RELEASE"
{
  printf 'version : %s\n' "$RELEASE"
  printf 'branch  : %s\n' "$(git -C "$ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo -)"
  printf 'commit  : %s\n' "$(git -C "$ROOT" log -1 --format='%h %s' 2>/dev/null || echo -)"
  printf 'deployed: %s from %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$(hostname)"
  if [[ -n "$DIRTY" ]]; then
    echo "uncommitted changes:"
    git -C "$ROOT" status --porcelain -- ros_ws/src tools | sed 's/^/  /'
  fi
} > "$WS/.deploy_info.tmp"

tar -C "$WS" -czf - --exclude=__pycache__ --exclude=.pytest_cache --exclude='*.pyc' src \
  | rsh "mkdir -p ~/$REL && tar -xzf - -C ~/$REL"
rsh "cat > ~/$REL/DEPLOY_INFO" < "$WS/.deploy_info.tmp"
rm -f "$WS/.deploy_info.tmp"
ok "uploaded to ~/$REL"

echo "  building on the Pi (first build of a release takes a few minutes) ..."
if ! rsh "$REMOTE_ENV
$TEST_FN"'
  set -e
  cd ~/'"$REL"'
  if ! colcon build --event-handlers console_cohesion- console_direct- > build.out 2>&1; then
    tail -40 build.out; echo "BUILD FAILED"; exit 1
  fi
  tail -3 build.out | sed "s/^/  /"
  run_tests '"$LINT"' || { echo "TESTS FAILED"; exit 1; }
  source install/setup.bash
  ros2 launch rover_bringup rover.launch.py --show-args >/dev/null || { echo "rover.launch.py does not load"; exit 1; }
  echo "  rover.launch.py loads"
'; then
  die "the new version failed on the Pi - nothing was changed (left in ~/$REL for a look)"
fi
ok "built and tested on the Pi"

if [[ "$MODE" == build-only ]]; then
  echo
  ok "--build-only: ~/$REL is ready but NOT active (the Rover runs what it ran before)"
  exit 0
fi

# ------------------------------------------------------------------ 3. activate
step "4/4 Activate $RELEASE"
rsh 'cd ~/rover_ws &&
  if [ -L current ]; then ln -sfn "$(readlink current)" previous; fi &&
  ln -sfn "releases/'"$RELEASE"'" current &&
  # keep the newest '"$KEEP_RELEASES"' releases, never current/previous
  keep="$(readlink current) $(readlink previous 2>/dev/null)" &&
  ls -1d releases/* | sort -r | tail -n +'"$((KEEP_RELEASES + 1))"' | while read -r d; do
    case " $keep " in *" $d "*) ;; *) rm -rf "$d"; echo "  removed old $d";; esac
  done'
ok "current -> releases/$RELEASE"

activate_and_restart
