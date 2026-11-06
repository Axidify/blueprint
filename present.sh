#!/usr/bin/env bash
# Present mock-ups and collect feedback, on macOS or Linux.
#   ./present.sh                   opens the page that lists every mock-up: pick a project there with a click
#   ./present.sh courier-booking   goes straight to one project
# (On a Mac you can also double-click present.command. On Windows, use present.cmd.)
# Add --lan to let others in the room comment from their own laptops: ./present.sh courier-booking --lan
# Show an earlier mock-up version: ./present.sh courier-booking --version 0.2
# A project folder can be given instead of a name: the "Open the mock-up" shortcut in a project folder does that.
cd "$(dirname "$0")"
python=".venv/bin/python"
if [ ! -x "$python" ]; then python="python3"; fi
project="${1:-}"
if [ -z "$project" ] || [ "${project#--}" != "$project" ]; then  # no project named (only options, or nothing)
  echo "Opening your mock-ups in the browser: pick a project there."
  echo "Keep this window open while you present; press Ctrl+C when you are done."
  exec "$python" -I tools/mockup.py serve "$@"
fi
shift
folder="projects/$project"
if [ -f "$project/spec/app.yaml" ]; then folder="$project"; fi
if [ ! -f "$folder/spec/app.yaml" ]; then
  echo "No mock-up spec found for \"$project\". Projects with a mock-up:"
  for p in projects/*/; do
    if [ -f "${p}spec/app.yaml" ]; then echo "  $(basename "$p")"; fi
  done
  exit 1
fi
echo
echo "Opening the mock-up. Press Feedback on the bar in the bottom-right corner to collect comments."
echo "Keep this window open during the session; press Ctrl+C when you are done."
exec "$python" -I tools/mockup.py serve "$folder" "$@"
