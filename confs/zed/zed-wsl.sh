#!/bin/sh
exec "/mnt/c/Users/rannd/AppData/Local/Programs/Zed/bin/Zed.exe" \
  --wsl "$(id -un)@$WSL_DISTRO_NAME" "$@"
