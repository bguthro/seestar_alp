#!/bin/bash -e
src_home=$(cd $(dirname $0)/.. && pwd)
source ${src_home}/raspberry_pi/setup.sh

function usage() {
  cat <<__EOF
usage: $0 [options]
  options:
    -f | --force     Force an update, even if up-to-date
    -l | --latest    Use latest source code in tree, instead of the latest tag
__EOF
}

function update() {
  validate_access

  OPTIONS=$(getopt -o frl --long "force,relaunch,latest" -n "$0" -- "$@")
  eval set -- "$OPTIONS"

  while true; do
    case "$1" in
      -f | --force )
        FORCE=true
        shift
        ;;
      -r | --relaunch )
        # Internal only
        FORCE=true
        RELAUNCH=true
        shift
        ;;
      -l | --latest )
        LATEST=true
        shift
        ;;
      -- )
          shift
          break
          ;;
      * )
        usage
        exit 1
    esac
  done

  # check if update is required
  cd "${src_home}"
  git fetch --tags

  if [ "${LATEST}" = "true" ]; then
    rev_to_check="@{u}"
  else
    rev_to_check=$(git tag | grep -v "\-g" | tail -1)
  fi

  if [ $(git rev-parse HEAD) = $(git rev-parse ${rev_to_check}) ] && [ "${FORCE}" != "true" ]; then
      echo "Nothing to do, you're already up-to-date!"
      exit 0
  fi

  if ! git diff --quiet; then
    echo "Working tree is dirty, aborting update"
    exit 1
  fi

  git reset --hard ${rev_to_check}
  exit 1

  cd ${src_home}

  # Update script needs to relaunch itsself, to pick up source changes
  if [ -z "${RELAUNCH}" ]; then
    echo "Re-launching update script with new source"
    exec ${src_home}/raspberry_pi/update.sh --relaunch
  fi

  if $(systemctl is-active --quiet seestar); then
    sudo systemctl stop seestar
  fi

  if $(systemctl is-active --quiet INDI); then
    sudo systemctl stop INDI
  fi

  # Perform any update operations here, that need to change
  # prior behavior on the system
  user=$(whoami)
  group=$(id -gn)
  if [ -d ./logs ]; then
      sudo chown ${user}:${group} ./logs/* || true
  else
      mkdir logs
  fi

  config_toml_setup
  install_apt_packages
  python_virtualenv_setup
  network_config
  systemd_service_setup
  print_banner "update"
}

#
# run update if not sourced from another file
#
(return 0 2>/dev/null) && sourced=1 || sourced=0
if [ ${sourced} = 0 ]; then
    update $@
fi
