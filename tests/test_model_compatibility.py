import argparse
import base64
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import image_pipeline
import text_to_image


class ModelCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.args = argparse.Namespace(
            api_key=None, base_url=None, model=None, quality=None, output_format=None,
            size="auto", output_compression=None, request_timeout=120,
            max_retries=1, request_interval=0, filename_prefix="generated", prompt=["cat"],
        )
        self.environment = mock.patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def runtime(self, config=None):
        return image_pipeline.resolve_runtime_config(
            self.args, {"api_key": "sk-test", **(config or {})}
        )

    def job(self, runtime, fields=None, overrides=None, smoke_test=False):
        path = self.root / "job.json"
        path.write_text(json.dumps({
            "input_dir": str(self.root), "output_dir": str(self.root / "output"),
            "prompts": ["cat", "dog"], **(fields or {}),
        }))
        return image_pipeline.load_job_config(path, runtime, smoke_test, overrides)

    def response(self):
        response = mock.Mock(status_code=200)
        response.json.return_value = {
            "data": [{"b64_json": base64.b64encode(b"image-bytes").decode()}]
        }
        return response

    def test_unconfigured_generation_and_editing_use_image25_auto(self):
        runtime = self.runtime()
        self.assertEqual(runtime.model, "gpt-image-2.5-sunburst")
        self.assertEqual(runtime.quality, "auto")
        text_to_image.validate_args(self.args, runtime.api_key, runtime.model, runtime.quality, runtime.output_format)
        job = self.job(runtime)
        image_pipeline.validate(runtime, job)
        self.assertEqual((job.model, job.size, job.quality), (runtime.model, "auto", "auto"))

    def test_legacy_configuration_is_preserved(self):
        runtime = self.runtime({"default_model": "gpt-image-2", "default_quality": "high"})
        job = self.job(runtime, {"size": "3840x2160"})
        self.assertEqual((job.model, job.size, job.quality), ("gpt-image-2", "3840x2160", "high"))

    def test_cli_overrides_job_and_job_overrides_user_config(self):
        runtime = self.runtime({"default_model": "gpt-image-2", "default_quality": "high"})
        fields = {"model": "gpt-image-2.5-flare", "quality": "medium", "output_format": "jpeg"}
        job = self.job(runtime, fields)
        self.assertEqual((job.model, job.quality, job.output_format), ("gpt-image-2.5-flare", "medium", "jpeg"))
        self.args.model, self.args.quality, self.args.output_format = "gpt-image-2.5-sunburst", "auto", "webp"
        runtime = self.runtime({"default_model": "gpt-image-2", "default_quality": "high"})
        job = self.job(runtime, fields, overrides=self.args, smoke_test=True)
        self.assertEqual((job.model, job.quality, job.output_format), (self.args.model, "auto", "webp"))
        self.assertEqual(job.prompts, ["cat"])

    def test_configured_models_are_not_hardcoded(self):
        for model in ("gpt-image-2.5-sunburst", "gpt-image-2.5-flare", "gpt-image-2", "custom-image-model"):
            with self.subTest(model=model):
                text_to_image.validate_args(self.args, "sk-test", model, "auto", "png")

    def test_blank_models_are_rejected_before_api_calls(self):
        with self.assertRaisesRegex(ValueError, "non-empty model ID"):
            text_to_image.validate_args(self.args, "sk-test", "  ", "auto", "png")
        runtime = self.runtime()
        with self.assertRaisesRegex(ValueError, "non-empty model ID"):
            image_pipeline.validate(runtime, self.job(runtime, {"model": "  "}))

    def test_image25_generation_transmits_exact_model_and_explicit_parameters(self):
        for model in ("gpt-image-2.5-sunburst", "gpt-image-2.5-flare"):
            with self.subTest(model=model), mock.patch.object(text_to_image.requests, "post", return_value=self.response()) as post:
                raw = text_to_image.generate_one(
                    prompt="cat", api_key="sk-test", base_url="https://image.example/v1",
                    model=model, size="3840x2160", quality="high", output_format="png",
                    output_compression=None, request_timeout=120, max_retries=1,
                )
                self.assertEqual(raw, b"image-bytes")
                post.assert_called_once()
                self.assertEqual(post.call_args.args[0], "https://image.example/v1/images/generations")
                payload = post.call_args.kwargs["json"]
                self.assertEqual(payload["response_format"], "b64_json")
                self.assertEqual((payload["model"], payload["size"], payload["quality"]), (model, "3840x2160", "high"))

    def test_image25_editing_transmits_exact_model_and_parameters(self):
        source = self.root / "source.png"
        source.write_bytes(b"input-image")
        for model in ("gpt-image-2.5-sunburst", "gpt-image-2.5-flare"):
            for size, quality in (("auto", "auto"), ("3840x2160", "high")):
                with self.subTest(model=model, size=size), mock.patch.object(image_pipeline.requests, "post", return_value=self.response()) as post:
                    runtime = self.runtime({"base_url": "https://image.example/v1"})
                    job = self.job(runtime, {"model": model, "size": size, "quality": quality})
                    failures = []
                    raw = image_pipeline.edit_image(source, "cat", runtime, job, lambda _: None, failures)
                    self.assertEqual(raw, b"image-bytes")
                    self.assertEqual(failures, [])
                    post.assert_called_once()
                    self.assertEqual(post.call_args.args[0], "https://image.example/v1/images/edits")
                    payload = post.call_args.kwargs["data"]
                    self.assertEqual(payload["response_format"], "b64_json")
                    self.assertEqual((payload["model"], payload["size"], payload["quality"]), (model, size, quality))
                    self.assertIn("image[]", post.call_args.kwargs["files"])


if __name__ == "__main__":
    unittest.main()
