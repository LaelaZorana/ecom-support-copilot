---
title: SupportCopilot
emoji: 🛒
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# SupportCopilot on Hugging Face Spaces

This file is the Space front-matter. To deploy:

1. Create a new **Docker** Space.
2. Push this repository to it (or duplicate from GitHub).
3. The container reads `$PORT` (Spaces sets `7860`); no secrets are required — it runs the
   offline stub by default.
4. (Optional) add `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` under **Settings → Secrets** to use a
   real model.

The application code, full README, and tests live in the repository root.
