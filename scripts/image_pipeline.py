#!/usr/bin/env python3
"""Run retryable image-to-image batch jobs from a JSON config."""

from __future__ import annotations

import argparse
import base64
import json
import os
import platform
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests


DEFAULT_BASE_URL = "https://api.qijixing.fun/v1"
DEFAULT_MODEL = "gpt-image-2"
DEFAULT_SIZE = "1024x1024"
DEFAULT_QUALITY = "high"
DEFAULT_FORMAT = "png"
CONFIG_ENV_VAR = "QIJIXING_IMAGE_CONFIG"
API_KEY_ENV_VAR = "QIJIXING_IMAGE_API_KEY"
BASE_URL_ENV_VAR = "QIJIXING_IMAGE_BASE_URL"
SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


@dataclass(frozen=True)
class RuntimeConfig:
    api_key: str
    base_url: str
    model: str
    quality: str
    output_format: str


@dataclass(frozen=True)
class JobConfig:
    input_dir: Path
    output_dir: Path
    prompts: List[str]
    size: str
    quality: str
    output_format: str
    model: str
    request_timeout: int
    max_retries: int
    max_rounds: int
    request_interval: float
    recursive: bool


Task = Tuple[Path, str, int, Path]
Failure = Dict[str, str]


def user_config_path() -> Path:
    override = os.environ.get(CONFIG_ENV_VAR)
    if override:
        return Path(os.path.expandvars(os.path.expanduser(override)))
    if platform.system().lower().startswith("win"):
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "qijixing-image" / "config.json"
        return Path.home() / "AppData" / "Roaming" / "qijixing-image" / "config.json"
    return Path.home() / ".config" / "qijixing-image" / "config.json"


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return data


def load_user_config(path: Optional[Path]) -> Dict[str, Any]:
    config_path = path or user_config_path()
    if not config_path.exists():
        return {}
    return load_json(config_path)


def resolve_runtime_config(args: argparse.Namespace, user_config: Dict[str, Any]) -> RuntimeConfig:
    api_key = (
        args.api_key
        or os.environ.get(API_KEY_ENV_VAR)
        or user_config.get("api_key")
        or ""
    )
    base_url = (
        args.base_url
        or os.environ.get(BASE_URL_ENV_VAR)
        or user_config.get("base_url")
        or DEFAULT_BASE_URL
    )
    model = args.model or user_config.get("default_model") or DEFAULT_MODEL
    quality = args.quality or user_config.get("default_quality") or DEFAULT_QUALITY
    output_format = args.output_format or user_config.get("default_format") or DEFAULT_FORMAT

    return RuntimeConfig(
        api_key=str(api_key),
        base_url=str(base_url).rstrip("/"),
        model=str(model),
        quality=str(quality),
        output_format=str(output_format),
    )


def resolve_path(value: str, base_dir: Path) -> Path:
    path = Path(os.path.expandvars(os.path.expanduser(value)))
    if not path.is_absolute():
        path = base_dir / path
    return path


def load_job_config(path: Path, runtime: RuntimeConfig, smoke_test: bool) -> JobConfig:
    raw = load_json(path)
    base_dir = path.parent

    prompts = raw.get("prompts")
    if not isinstance(prompts, list) or not all(isinstance(p, str) and p.strip() for p in prompts):
        raise ValueError("job.prompts must be a non-empty list of strings")

    input_dir_raw = raw.get("input_dir")
    output_dir_raw = raw.get("output_dir")
    if not isinstance(input_dir_raw, str) or not input_dir_raw.strip():
        raise ValueError("job.input_dir must be a non-empty string")
    if not isinstance(output_dir_raw, str) or not output_dir_raw.strip():
        raise ValueError("job.output_dir must be a non-empty string")

    job = JobConfig(
        input_dir=resolve_path(input_dir_raw, base_dir),
        output_dir=resolve_path(output_dir_raw, base_dir),
        prompts=[p.strip() for p in prompts],
        size=str(raw.get("size") or DEFAULT_SIZE),
        quality=str(raw.get("quality") or runtime.quality),
        output_format=str(raw.get("output_format") or runtime.output_format),
        model=str(raw.get("model") or runtime.model),
            request_timeout=int(raw.get("request_timeout") or 300),
        max_retries=int(raw.get("max_retries") or 2),
        max_rounds=int(raw.get("max_rounds") or 5),
        request_interval=float(raw.get("request_interval") or 1),
        recursive=bool(raw.get("recursive") or False),
    )

    if smoke_test:
        return JobConfig(
            input_dir=job.input_dir,
            output_dir=job.output_dir,
            prompts=job.prompts[:1],
            size=job.size,
            quality=job.quality,
            output_format=job.output_format,
            model=job.model,
            request_timeout=job.request_timeout,
            max_retries=job.max_retries,
            max_rounds=1,
            request_interval=job.request_interval,
            recursive=job.recursive,
        )
    return job


def make_logger(output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "run.log"

    def log(msg: str) -> None:
        print(msg, flush=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(msg + "\n")

    return log, log_path


def collect_images(directory: Path, recursive: bool) -> List[Path]:
    if recursive:
        candidates: Iterable[Path] = directory.rglob("*")
    else:
        candidates = directory.iterdir()
    return sorted(p for p in candidates if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS)


def output_subdir_name(input_dir: Path, image_path: Path, recursive: bool) -> str:
    if not recursive:
        return image_path.stem
    rel = image_path.relative_to(input_dir).with_suffix("")
    return "__".join(rel.parts)


def build_all_tasks(job: JobConfig, image_paths: List[Path]) -> List[Task]:
    tasks: List[Task] = []
    for img_path in image_paths:
        img_out_dir = job.output_dir / output_subdir_name(job.input_dir, img_path, job.recursive)
        img_out_dir.mkdir(parents=True, exist_ok=True)
        for p_idx, prompt in enumerate(job.prompts, start=1):
            out_path = img_out_dir / f"prompt_{p_idx:02d}.{job.output_format}"
            tasks.append((img_path, prompt, p_idx, out_path))
    return tasks


def filter_pending(tasks: List[Task]) -> List[Task]:
    return [task for task in tasks if not task[3].exists()]


def mime_for_path(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".png":
        return "image/png"
    if ext == ".webp":
        return "image/webp"
    return "image/jpeg"


def classify_failure(message: str) -> str:
    text = message.lower()
    if "401" in text or "unauthorized" in text or "invalid api key" in text:
        return "api_key"
    if "429" in text or "rate limit" in text or "too many requests" in text:
        return "rate_limit"
    if "timeout" in text or "timed out" in text or "read timed out" in text:
        return "timeout"
    if "500" in text or "502" in text or "503" in text or "504" in text:
        return "upstream"
    if "no supported images" in text or "input directory" in text:
        return "input_path"
    if "connection" in text or "network" in text or "dns" in text:
        return "network"
    return "unknown"


def human_advice(category: str) -> str:
    advice = {
        "api_key": f"Image API key looks invalid or missing. Check the dedicated config file or {API_KEY_ENV_VAR}.",
        "rate_limit": "The upstream service is rate-limiting requests. Increase request_interval or retry later.",
        "timeout": "The request timed out. Increase request_timeout and rerun the same job.",
        "upstream": "The upstream image service returned a temporary server error. Rerun the same job; existing outputs will be skipped.",
        "input_path": "The input path or image files look wrong. Check the input directory and supported extensions.",
        "network": "The machine may not be able to reach the API service. Check network connectivity or base_url.",
        "unknown": "The failure needs log inspection. Review the raw error lines near failed requests.",
    }
    return advice.get(category, advice["unknown"])


def edit_image(
    image_path: Path,
    prompt: str,
    runtime: RuntimeConfig,
    job: JobConfig,
    log,
    failures: List[Failure],
) -> Optional[bytes]:
    headers = {"Authorization": f"Bearer {runtime.api_key}"}
    for attempt in range(1, job.max_retries + 1):
        try:
            log(f"    [request] timeout={job.request_timeout}s")
            with image_path.open("rb") as img_file:
                response = requests.post(
                    f"{runtime.base_url}/images/edits",
                    headers=headers,
                    files={"image[]": (image_path.name, img_file, mime_for_path(image_path))},
                    data={
                        "model": job.model,
                        "prompt": prompt,
                        "size": job.size,
                        "quality": job.quality,
                        "output_format": job.output_format,
                    },
                    timeout=job.request_timeout,
                )
            log(f"    [response] HTTP {response.status_code}")
            response.raise_for_status()
            result = response.json()
            b64_json = result["data"][0]["b64_json"]
            return base64.b64decode(b64_json)
        except Exception as exc:
            message = str(exc)
            category = classify_failure(message)
            failures.append(
                {
                    "image": str(image_path),
                    "category": category,
                    "error": message[:500],
                }
            )
            wait = 2 ** (attempt - 1)
            log(f"    [failed {attempt}/{job.max_retries}] {message}")
            log(f"    [diagnosis] {category}: {human_advice(category)}")
            if attempt < job.max_retries:
                log(f"    waiting {wait}s before retry")
                time.sleep(wait)
    return None


def run_tasks(
    pending: List[Task],
    round_num: int,
    runtime: RuntimeConfig,
    job: JobConfig,
    log,
    failures: List[Failure],
) -> Tuple[int, int]:
    done = 0
    failed = 0
    for i, (img_path, prompt, p_idx, out_path) in enumerate(pending, start=1):
        preview = prompt[:70] + ("..." if len(prompt) > 70 else "")
        log(f"[round {round_num}] [{i}/{len(pending)}] {img_path.name} prompt_{p_idx:02d}: {preview}")
        img_bytes = edit_image(img_path, prompt, runtime, job, log, failures)
        if img_bytes:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(img_bytes)
            done += 1
            log(f"  [ok] saved: {out_path}")
        else:
            failed += 1
            log("  [fail] will retry in a later round if available")

        if i < len(pending):
            time.sleep(job.request_interval)
    return done, failed


def validate(runtime: RuntimeConfig, job: JobConfig) -> None:
    if not runtime.api_key:
        raise ValueError(
            f"Missing image-generation API key. Create {user_config_path()} with an api_key field, "
            f"or set {API_KEY_ENV_VAR}. Do not use a general Codex/OpenAI chat key for this workflow."
        )
    if not job.input_dir.is_dir():
        raise ValueError(f"Input directory does not exist: {job.input_dir}")
    if not job.prompts:
        raise ValueError("No prompts configured")
    if job.output_format not in {"png", "jpeg", "webp"}:
        raise ValueError("output_format must be one of: png, jpeg, webp")


def summarize_failures(failures: List[Failure], log) -> None:
    if not failures:
        return

    counts: Dict[str, int] = {}
    examples: Dict[str, str] = {}
    for failure in failures:
        category = failure["category"]
        counts[category] = counts.get(category, 0) + 1
        examples.setdefault(category, failure["error"])

    log("failure_summary:")
    for category, count in sorted(counts.items(), key=lambda item: item[1], reverse=True):
        log(f"  - {category}: {count} occurrence(s)")
        log(f"    likely_cause: {human_advice(category)}")
        log(f"    example_error: {examples[category]}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", required=True, type=Path, help="Path to job JSON")
    parser.add_argument("--user-config", type=Path, help="Override user config JSON path")
    parser.add_argument("--api-key", help="Override API key")
    parser.add_argument("--base-url", help="Override base URL")
    parser.add_argument("--model", help="Override model")
    parser.add_argument("--quality", help="Override quality")
    parser.add_argument("--output-format", help="Override output format")
    parser.add_argument("--smoke-test", action="store_true", help="Run only the first image and first prompt")
    parser.add_argument("--plan-only", action="store_true", help="Validate config and print the task plan without API calls")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    user_config = load_user_config(args.user_config)
    runtime = resolve_runtime_config(args, user_config)
    job = load_job_config(args.job, runtime, args.smoke_test)
    validate(runtime, job)
    log, log_path = make_logger(job.output_dir)

    images = collect_images(job.input_dir, job.recursive)
    if args.smoke_test:
        images = images[:1]
        log("[mode] smoke-test: first image and first prompt only")
    if not images:
        raise ValueError(f"No supported images found in: {job.input_dir}")

    all_tasks = build_all_tasks(job, images)
    failures: List[Failure] = []
    total = len(all_tasks)
    completed = total - len(filter_pending(all_tasks))
    log(f"input images: {len(images)}, prompts: {len(job.prompts)}, target outputs: {total}")
    log(f"base_url: {runtime.base_url}")
    log(f"output_dir: {job.output_dir}")
    log(f"log_path: {log_path}")
    if args.plan_only:
        log("[mode] plan-only: no API calls will be made")
        for img_path, _, p_idx, out_path in all_tasks[:20]:
            log(f"  - {img_path.name} prompt_{p_idx:02d} -> {out_path}")
        if len(all_tasks) > 20:
            log(f"  ... {len(all_tasks) - 20} more tasks")
        return 0
    if completed:
        log(f"resume: {completed} outputs already exist")

    for round_num in range(1, job.max_rounds + 1):
        pending = filter_pending(all_tasks)
        if not pending:
            break
        log("=" * 60)
        log(f"round {round_num}/{job.max_rounds}, pending: {len(pending)}, done: {total - len(pending)}/{total}")
        log("=" * 60)
        done, failed = run_tasks(pending, round_num, runtime, job, log, failures)
        completed = total - len(filter_pending(all_tasks))
        log(f"round finished: success {done}, failed {failed}, completed {completed}/{total}")
        if failed > 0 and round_num < job.max_rounds:
            wait = min(10 * round_num, 60)
            log(f"waiting {wait}s before next round")
            time.sleep(wait)

    missing = filter_pending(all_tasks)
    final_done = total - len(missing)
    log("=" * 60)
    log(f"finished: {final_done}/{total}")
    if missing:
        log(f"missing outputs after {job.max_rounds} rounds:")
        for img_path, prompt, p_idx, _ in missing:
            log(f"  - {img_path.name} prompt_{p_idx:02d}: {prompt[:80]}")
        summarize_failures(failures, log)
        return 1
    summarize_failures(failures, log)
    log("all outputs generated")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        raise SystemExit(1)
