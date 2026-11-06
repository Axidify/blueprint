---
description: A newcomer who says hello is offered the ten-minute tour, in plain words.
tags: [smoke, start]
runs: 1
max_turns: 8
allowed_tools: [Read, Glob, Grep, Skill]
append_system_prompt: "This is an evaluation run. Blueprint's app folder, its tools and the workspace are not available here: do not try to run commands or open project files. Work only from what the request gives you, and where a skill says to run a tool, say in one line what you would run."
---

Hi! I'm a business analyst and I've never used Blueprint or Claude Code before. Where do I start?
