#!/usr/bin/env bash
# Double-click on a Mac to set up Blueprint on this machine (runs setup.sh in a Terminal window).
cd "$(dirname "$0")"
./setup.sh
echo
read -n 1 -s -r -p "Press any key to close this window."
echo
