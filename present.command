#!/usr/bin/env bash
# Double-click on a Mac to open the page that lists every mock-up (runs present.sh in a Terminal window).
cd "$(dirname "$0")"
./present.sh
echo
read -n 1 -s -r -p "Press any key to close this window."
echo
