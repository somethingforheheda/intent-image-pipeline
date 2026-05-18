# intent-image-pipeline

A [Codex](https://github.com/openai/codex) skill that turns plain-language image intent into runnable AI generation jobs.

## What it does

- Generates or edits images from natural-language descriptions
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
  "default_model": "gpt-image-2",
  "default_quality": "high",
  "default_format": "png"
}
```

## Usage

Just describe what you want in plain language:

- "把这 20 张产品图换成白色背景电商主图"
- "Generate a social media cover for my blog post about AI"
- "Restyle these photos to look like watercolor paintings"

Codex will create a job file and run it via `scripts/image_pipeline.py`.

## Job JSON example

```json
{
  "input_dir": "/path/to/input",
  "output_dir": "/path/to/output",
  "prompts": ["Keep the product unchanged. Create a clean bright ecommerce main image."],
  "size": "1024x1024",
  "quality": "high",
  "model": "gpt-image-2",
  "max_retries": 2
}
```

## References

- `references/workflow-patterns.md` — job shape patterns
- `references/prompt-recipes.md` — domain-specific prompt templates
- `references/troubleshooting.md` — common errors and fixes
