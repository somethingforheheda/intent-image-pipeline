# Workflow Patterns

## Decision Table

| User intent | Job shape |
|---|---|
| "batch", "folder", "each image" | Use `input_dir`, one output subfolder per source image |
| "make N versions" | Create N prompts, one prompt per variant |
| "product must not change" | Add subject-preservation clauses to every prompt |
| "main image" | Use ecommerce main image recipe, usually `1024x1024` |
| "scene image" | Use ecommerce scene image recipe |
| "cover/poster" | Ask or infer aspect ratio; use social cover recipe |
| First-time user or large batch | Run `--smoke-test` before the full job |
| Smoke test fails | Stop, analyze `run.log`, explain the blocker, and wait for the user |
| Interrupted or partial AI job | Re-run the same job; existing outputs are skipped |

## Forbidden Fallbacks

Do not use any of these as an automatic replacement for AI generation:

- PIL, OpenCV, ImageMagick, canvas, CSS, or local filter effects
- Placeholder, mock, contact-sheet-only, or preview-only image creation
- Screenshot-based or browser-rendered substitutes
- A different image model, local model, or unrelated service unless the user explicitly approves the switch

If a fallback might help, first say exactly what it is and that it is not the requested AI generation. Continue only after the user clearly agrees.

## Defaults

- `base_url`: `https://api.qijixing.fun/v1`
- `model`: `gpt-image-2`
- `size`: `1024x1024`
- `quality`: `high`
- `output_format`: `png`
- `max_retries`: `2`
- `max_rounds`: `5`
- `recursive`: `false`

## Clarification Rules

Ask a short question only if the task cannot run safely:

- Missing input path
- Missing output location and no obvious nearby default
- The user requires exact platform dimensions but did not name a platform or ratio
- The user asks to use the image API but has not configured a dedicated image-generation key
- The requested AI API failed smoke testing and no approved fallback exists

Otherwise infer sensible defaults and explain them briefly before running.

## Job File Placement

Prefer placing generated job files in the output directory as `job.json`. If the output directory does not exist yet, create it through the runner or place the job in a nearby temporary work directory.
