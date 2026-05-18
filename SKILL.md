---
name: intent-image-pipeline
description: Natural-language image generation and image-editing workflow automation. Use when users ask Codex to create, edit, restyle, batch-generate, or transform images from plain-language intent, especially product photos, ecommerce main images, scene images, social covers, avatars, background replacement, batch image-to-image jobs, prompt expansion, retryable generation pipelines, or image workflow configuration.
---

# Intent Image Pipeline

## Overview

Turn a user's plain-language image intent into a runnable generation job. Prefer the bundled `scripts/image_pipeline.py` runner for batch image-to-image work because it handles cross-platform config discovery, retries, logs, missing-output checks, and resume behavior.

## Hard Stop Rules

- The `size` field (width and height) must each be a multiple of 16. If the user specifies a resolution that does not satisfy this (e.g. `1000x1000`, `1920x1080`), do not proceed — tell the user the exact values are invalid and suggest the nearest valid alternatives (e.g. `1008x1008`, `1920x1072` or `1024x1088`). Never silently round or adjust the resolution yourself.
- If the AI image API cannot run because of a missing/invalid API key, unreachable base URL, quota/rate limit, network failure, timeout, or upstream service error, stop the workflow after analyzing the log.
- Never silently replace an AI image-generation or image-editing job with local PIL/OpenCV filters, screenshots, placeholder images, mock outputs, non-AI image processing, or any approximate substitute.
- Offer a non-AI fallback only after explicitly telling the user it is not AI generation and receiving clear permission from the user.
- When blocked, explain the blocker, the exact next action, and whether the same job can be safely rerun. Do not create alternate images to "make progress."

## Workflow

1. Clarify only blocking details: input path, desired output style/use case, output count per source image, and whether the subject must remain unchanged. Make conservative defaults when the user intent is clear enough.
2. Read `references/workflow-patterns.md` to choose a job shape when the request is broad or ambiguous.
3. Read `references/prompt-recipes.md` when prompt wording needs domain-specific guardrails, style variants, or subject-preservation language.
4. Create a job JSON file near the user's working files or in a temporary working directory. Do not put API keys in job files.
5. For first runs or risky batches, run a smoke test before the full batch:

```bash
python3 /path/to/intent-image-pipeline/scripts/image_pipeline.py --job /path/to/job.json --smoke-test
```

6. If the smoke test succeeds, run the full job. If the smoke test fails, stop and explain the diagnosis; do not switch tools or generation methods.

```bash
python3 /path/to/intent-image-pipeline/scripts/image_pipeline.py --job /path/to/job.json
```

7. Report the output directory, total target count, completed count, and any failed/missing tasks.
8. If the runner fails or produces fewer outputs than expected, read `run.log` yourself and translate the likely cause into plain language. Do not ask beginner users to inspect logs manually.

## User Config

The runner reads credentials from a dedicated image-generation config file or dedicated image-generation environment variables. Never read or reuse a general Codex/OpenAI chat key such as `OPENAI_API_KEY` for this workflow. Never hard-code a key into the skill, job JSON, or scripts.

Default config paths:

- macOS/Linux: `~/.config/qijixing-image/config.json`
- Windows: `%APPDATA%\qijixing-image\config.json`

Optional config path override:

- `QIJIXING_IMAGE_CONFIG`

Supported config keys:

```json
{
  "api_key": "sk-...",
  "base_url": "https://api.qijixing.fun/v1",
  "default_model": "gpt-image-2",
  "default_quality": "high",
  "default_format": "png"
}
```

Resolution order:

1. CLI overrides
2. Dedicated environment variables: `QIJIXING_IMAGE_API_KEY`, `QIJIXING_IMAGE_BASE_URL`
3. User config file
4. Defaults, with `base_url` defaulting to `https://api.qijixing.fun/v1`

If no config file exists, tell the user where to create it. If the user pastes a key into chat and asks for setup, immediately write it to the dedicated config file, then warn that the key was exposed in the conversation and recommend rotating it and replacing the file value.

## Job JSON

Use this shape for generated jobs:

```json
{
  "input_dir": "/absolute/path/to/input-images",
  "output_dir": "/absolute/path/to/output-images",
  "prompts": [
    "Keep the product unchanged. Create a clean bright ecommerce main image."
  ],
  "size": "1024x1024",
  "quality": "high",
  "output_format": "png",
  "model": "gpt-image-2",
  "request_timeout": 300,
  "max_retries": 2,
  "max_rounds": 5,
  "request_interval": 1,
  "recursive": false
}
```

Use absolute paths when possible. `prompts` may be generated from the user intent; include one prompt per requested output variant.

## Output Rules

- Preserve original source files.
- Put outputs under `output_dir/<source-file-stem>/prompt_XX.<format>` for image-to-image batches.
- Let the runner resume by skipping existing output files.
- When failures occur, inspect `run.log`, use the runner's `failure_summary`, and read `references/troubleshooting.md` for common fixes.
- Summarize results in user language; include the most likely cause and next action. Avoid exposing raw API errors unless they help the user act.
