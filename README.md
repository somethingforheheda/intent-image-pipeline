# intent-image-pipeline

A [Codex](https://github.com/openai/codex) skill that turns plain-language image intent into runnable AI generation jobs.

## What it does

- Generates images directly from one or more natural-language prompts
- Edits images from natural-language instructions
- Supports batch image-to-image workflows
- Handles retries, resume, and logging automatically
- Works with any OpenAI-compatible image API (defaults to `api.qijixing.fun/v1`)

## Install

```bash
npx codex skills install https://github.com/somethingforheheda/intent-image-pipeline
```

## Setup

Create a config file at `~/.config/qijixing-image/config.json`:

```json
{
  "api_key": "sk-...",
  "base_url": "https://api.qijixing.fun/v1",
  "default_model": "gpt-image-2.5-sunburst",
  "default_quality": "auto",
  "default_format": "png"
}
```

## Image models

The default is `gpt-image-2.5-sunburst`. Select
`gpt-image-2.5-sunburst`, `gpt-image-2.5-flare`, or `gpt-image-2`; both generation
and editing pass the selected model ID through unchanged. Use the exact ID:
`image2.5` and `gpt-image-2.5` are not aliases supplied by this skill.

Select a model with `--model`, a job's `model`, or config `default_model`.
Precedence is CLI > job (editing only) > config > built-in default. Other model
IDs are also accepted when your configured OpenAI-compatible image API supports
them. Existing configurations that explicitly select `gpt-image-2` keep using it.

Size and quality default to `auto`. Explicit sizes and quality settings are
preserved. `auto` does not guarantee a particular resolution or maximum quality;
verify exact dimensions from the output image.

## Usage

Just describe what you want in plain language:

- "把这 20 张产品图换成白色背景电商主图"
- "Generate a social media cover for my blog post about AI"
- "Restyle these photos to look like watercolor paintings"

Codex will create a job file and run it via `scripts/image_pipeline.py`.

For direct text-to-image generation, Codex runs:

```bash
python3 scripts/text_to_image.py \
  --prompt "赛博朋克风格的城市夜景" \
  --output-dir /path/to/output \
  --model gpt-image-2.5-sunburst \
  --size auto \
  --quality auto
```

The script calls `POST /images/generations` with `response_format=b64_json`, waits at least 120 seconds per
request, retries transient failures, and decodes `data[0].b64_json` to an image.
Both scripts ignore response `url` fields and save only decoded image data to
local files. URL-only responses fail without returning or downloading the link.
Errors and logs omit remote addresses and raw response bodies.

## Job JSON example

```json
{
  "input_dir": "/path/to/input",
  "output_dir": "/path/to/output",
  "prompts": ["Keep the product unchanged. Create a clean bright ecommerce main image."],
  "size": "auto",
  "quality": "auto",
  "model": "gpt-image-2.5-sunburst",
  "max_retries": 2
}
```

## References

- `references/workflow-patterns.md` — job shape patterns
- `references/prompt-recipes.md` — domain-specific prompt templates
- `references/troubleshooting.md` — common errors and fixes
