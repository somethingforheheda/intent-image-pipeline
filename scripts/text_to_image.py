#!/usr/bin/env python3
"""Generate images from one or more text prompts with the qijixing Images API."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from image_pipeline import (
    API_KEY_ENV_VAR,
    DEFAULT_FORMAT,
    DEFAULT_MODEL,
    DEFAULT_QUALITY,
    classify_failure,
    decode_image_response,
    human_advice,
    load_user_config,
    resolve_runtime_config,
    report_image_size,
    safe_request_error,
    user_config_path,
)


VALID_QUALITIES = {"auto", "low", "medium", "high"}
VALID_FORMATS = {"png", "jpeg", "webp"}
SIZE_RE = re.compile(r"^[1-9]\d*x[1-9]\d*$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prompt",
        action="append",
        required=True,
        help="Image description. Repeat this option to generate one image per prompt.",
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--user-config", type=Path, help="Override user config JSON path")
    parser.add_argument("--api-key", help="Override the dedicated image API key")
    parser.add_argument("--base-url", help="Override API base URL")
    parser.add_argument("--model", help=f"Image model (default: {DEFAULT_MODEL})")
    parser.add_argument("--size", default="auto", help="auto or WIDTHxHEIGHT")
    parser.add_argument("--quality", help="auto, low, medium, or high")
    parser.add_argument("--output-format", help="png, jpeg, or webp")
    parser.add_argument(
        "--output-compression",
        type=int,
        help="Compression from 0 to 100; valid only for jpeg/webp",
    )
    parser.add_argument("--request-timeout", type=int, default=120)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--request-interval", type=float, default=1.0)
    parser.add_argument(
        "--filename-prefix",
        default="generated",
        help="Output filename prefix (default: generated)",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Validate and print the request plan without calling the API",
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace, api_key: str, model: str, quality: str, output_format: str) -> None:
    if not api_key:
        raise ValueError(
            f"Missing image-generation API key. Create {user_config_path()} with an api_key field, "
            f"or set {API_KEY_ENV_VAR}."
        )
    if not model.strip():
        raise ValueError("model must be a non-empty model ID supported by the configured image API")
    if args.size != "auto" and not SIZE_RE.fullmatch(args.size):
        raise ValueError("size must be auto or WIDTHxHEIGHT, for example 1024x1024 or 800x600")
    if quality not in VALID_QUALITIES:
        raise ValueError("quality must be one of: auto, low, medium, high")
    if output_format not in VALID_FORMATS:
        raise ValueError("output_format must be one of: png, jpeg, webp")
    if args.output_compression is not None:
        if output_format == "png":
            raise ValueError("output_compression is valid only for jpeg or webp")
        if not 0 <= args.output_compression <= 100:
            raise ValueError("output_compression must be between 0 and 100")
    if args.request_timeout < 120:
        raise ValueError("request_timeout must be at least 120 seconds")
    if args.max_retries < 1:
        raise ValueError("max_retries must be at least 1")
    if args.request_interval < 0:
        raise ValueError("request_interval cannot be negative")
    if not args.filename_prefix.strip() or Path(args.filename_prefix).name != args.filename_prefix:
        raise ValueError("filename_prefix must be a non-empty filename component")
    if not all(prompt.strip() for prompt in args.prompt):
        raise ValueError("prompt cannot be empty")


def generate_one(
    *,
    prompt: str,
    api_key: str,
    base_url: str,
    model: str,
    size: str,
    quality: str,
    output_format: str,
    output_compression: Optional[int],
    request_timeout: int,
    max_retries: int,
) -> bytes:
    body: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": size,
        "quality": quality,
        "output_format": output_format,
        "response_format": "b64_json",
    }
    if output_compression is not None:
        body["output_compression"] = output_compression

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(
                f"{base_url.rstrip('/')}/images/generations",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=request_timeout,
            )
            response.raise_for_status()
            return decode_image_response(response)
        except Exception as exc:
            message = safe_request_error(exc)
            category = classify_failure(message)
            print(
                f"[failed {attempt}/{max_retries}] {category}: {human_advice(category)}",
                file=sys.stderr,
                flush=True,
            )
            if attempt == max_retries:
                raise RuntimeError(f"Image generation failed after {max_retries} attempt(s): {message}") from None
            time.sleep(2 ** (attempt - 1))
    raise AssertionError("unreachable")


def main() -> int:
    args = parse_args()
    user_config = load_user_config(args.user_config)
    runtime = resolve_runtime_config(args, user_config)
    quality = args.quality or runtime.quality or DEFAULT_QUALITY
    output_format = args.output_format or runtime.output_format or DEFAULT_FORMAT
    validate_args(args, runtime.api_key, runtime.model, quality, output_format)

    output_dir = args.output_dir.expanduser().resolve()
    plan = {
        "endpoint": "/images/generations",
        "model": runtime.model,
        "count": len(args.prompt),
        "size": args.size,
        "quality": quality,
        "output_format": output_format,
        "output_dir": str(output_dir),
    }
    print(json.dumps(plan, ensure_ascii=False, indent=2), flush=True)
    if args.plan_only:
        print("[mode] plan-only: no API calls were made", flush=True)
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = "jpg" if output_format == "jpeg" else output_format
    completed: List[Path] = []
    for index, prompt in enumerate(args.prompt, start=1):
        output_path = output_dir / f"{args.filename_prefix}_{index:02d}.{suffix}"
        if output_path.exists():
            print(f"[skip] already exists: {output_path}", flush=True)
            completed.append(output_path)
            continue
        image_bytes = generate_one(
            prompt=prompt.strip(),
            api_key=runtime.api_key,
            base_url=runtime.base_url,
            model=runtime.model,
            size=args.size,
            quality=quality,
            output_format=output_format,
            output_compression=args.output_compression,
            request_timeout=args.request_timeout,
            max_retries=args.max_retries,
        )
        output_path.write_bytes(image_bytes)
        report_image_size(image_bytes, args.size, lambda message: print(message, flush=True))
        completed.append(output_path)
        print(f"[ok] saved: {output_path}", flush=True)
        if index < len(args.prompt):
            time.sleep(args.request_interval)

    print(f"finished: {len(completed)}/{len(args.prompt)}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        raise SystemExit(1)
