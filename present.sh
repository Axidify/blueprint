#!/usr/bin/env bash
# Present a project's mock-up and collect feedback, on macOS or Linux: ./present.sh courier-booking
# (On a Mac you can also double-click present.command. On Windows, use present.cmd.)
# Add --lan to let others in the room comment from their own laptops: ./present.sh courier-booking --lan
# Show an earlier mock-up version: ./present.sh courier-booking --version 0.2
cd "$(dirname "$0")"
python=".venv/bin/python"
if [ ! -x "$python" ]; then python="python3"; fi
project="${1:-}"
if [ -n "$project" ]; then
  shift
else
  echo "Projects with a mock-up:"
  for p in projects/*/; do
    if [ -f "${p}spec/app.yaml" ]; then echo "  $(basename "$p")"; fi
  done
  echo
  read -r -p "Type the project name and press Enter: " project
fi
if [ ! -f "projects/$project/spec/app.yaml" ]; then
  echo "No mock-up spec found for \"$project\"."
  exit 1
fi
echo
echo "Opening the mock-up. Press Feedback in the bottom-right corner to collect comments."
echo "Keep this window open during the session; press Ctrl+C when you are done."
exec "$python" -I tools/mockup.py serve "projects/$project" "$@"
