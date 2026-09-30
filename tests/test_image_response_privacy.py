import base64
import contextlib
import io
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


REMOTE_IMAGE_URL = "https://private-origin.invalid/images/secret.png"


class ImageResponsePrivacyTests(unittest.TestCase):
    def response(self, item):
        response = mock.Mock(status_code=200)
        response.json.return_value = {"data": [item]}
        return response

    def generate(self):
        return text_to_image.generate_one(
            prompt="cat", api_key="sk-test", base_url="https://configured-api.invalid/v1",
            model="gpt-image-2.5-sunburst", size="auto", quality="auto",
            output_format="png", output_compression=None, request_timeout=120, max_retries=1,
        )

    def edit(self, logs, failures):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            source.write_bytes(b"input")
            runtime = image_pipeline.RuntimeConfig("sk-test", "https://configured-api.invalid/v1", "gpt-image-2.5-sunburst", "auto", "png")
            job = image_pipeline.JobConfig(root, root, ["cat"], "auto", "auto", "png", runtime.model, 120, 1, 1, 0, False)
            return image_pipeline.edit_image(source, "cat", runtime, job, logs.append, failures)

    def test_mixed_response_returns_only_image_bytes_without_fetching_url(self):
        raw = b"image-bytes"
        response = self.response({"url": REMOTE_IMAGE_URL, "b64_json": base64.b64encode(raw).decode()})
        logs, failures = [], []
        with mock.patch.object(image_pipeline.requests, "post", return_value=response), mock.patch.object(image_pipeline.requests, "get") as get:
            self.assertEqual(self.generate(), raw)
            self.assertEqual(self.edit(logs, failures), raw)
        get.assert_not_called()
        self.assertEqual(failures, [])
        self.assertNotIn(REMOTE_IMAGE_URL, "\n".join(logs))

    def test_url_only_and_invalid_base64_fail_without_exposing_or_fetching_url(self):
        for encoded in (None, "", REMOTE_IMAGE_URL):
            with self.subTest(encoded=encoded):
                item = {"url": REMOTE_IMAGE_URL}
                if encoded is not None:
                    item["b64_json"] = encoded
                response = self.response(item)
                stderr = io.StringIO()
                logs, failures = [], []
                with mock.patch.object(image_pipeline.requests, "post", return_value=response), mock.patch.object(image_pipeline.requests, "get") as get, contextlib.redirect_stderr(stderr):
                    with self.assertRaises(RuntimeError) as caught:
                        self.generate()
                    self.assertIsNone(self.edit(logs, failures))
                get.assert_not_called()
                output = stderr.getvalue() + str(caught.exception) + str(logs) + str(failures)
                self.assertNotIn(REMOTE_IMAGE_URL, output)
                self.assertNotIn("private-origin.invalid", output)
                self.assertTrue(failures)

    def test_http_errors_preserve_status_without_leaking_addresses_or_body(self):
        response = self.response({"url": REMOTE_IMAGE_URL})
        response.status_code = 503
        response.raise_for_status.side_effect = image_pipeline.requests.HTTPError(
            "503 Server Error at " + REMOTE_IMAGE_URL, response=response,
        )
        stderr = io.StringIO()
        logs, failures = [], []
        with mock.patch.object(image_pipeline.requests, "post", return_value=response), contextlib.redirect_stderr(stderr):
            with self.assertRaises(RuntimeError) as caught:
                self.generate()
            self.assertIsNone(self.edit(logs, failures))
        output = stderr.getvalue() + str(caught.exception) + str(logs) + str(failures)
        self.assertIn("503", output)
        self.assertNotIn("https://", output)
        self.assertNotIn("private-origin.invalid", output)
        self.assertEqual(failures[0]["category"], "service")
        self.assertTrue(caught.exception.__suppress_context__)

    def test_transport_and_unexpected_errors_never_echo_raw_messages(self):
        for kind in (image_pipeline.requests.Timeout, image_pipeline.requests.ConnectionError, RuntimeError):
            with self.subTest(kind=kind):
                safe = image_pipeline.safe_request_error(kind("connection failed at " + REMOTE_IMAGE_URL))
                self.assertNotIn("https://", safe)
                self.assertNotIn("private-origin.invalid", safe)

    def test_dimension_mismatch_is_reported_without_modifying_image(self):
        raw = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jfCgAAAAASUVORK5CYII=")
        logs = []
        image_pipeline.report_image_size(raw, "1024x1024", logs.append)
        self.assertIn("actual_size=1x1", logs[0])
        self.assertIn("does not meet", logs[1])
        logs = []
        image_pipeline.report_image_size(raw, "1x1", logs.append)
        self.assertEqual(len(logs), 1)

    def test_cli_output_and_saved_logs_exclude_remote_urls(self):
        raw = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jfCgAAAAASUVORK5CYII=")
        response = self.response({"url": REMOTE_IMAGE_URL, "b64_json": base64.b64encode(raw).decode()})
        config = {"api_key": "sk-test", "base_url": "https://private-origin.invalid/v1"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_dir = root / "input"
            source_dir.mkdir()
            (source_dir / "source.png").write_bytes(raw)
            job_path = root / "job.json"
            job_path.write_text(json.dumps({"input_dir": str(source_dir), "output_dir": str(root / "edit"), "prompts": ["cat"], "max_retries": 1}))
            commands = (
                (text_to_image, ["text_to_image.py", "--prompt", "cat", "--output-dir", str(root / "text")]),
                (image_pipeline, ["image_pipeline.py", "--job", str(job_path)]),
            )
            for module, argv in commands:
                with self.subTest(script=argv[0]):
                    stdout = io.StringIO()
                    with mock.patch.object(sys, "argv", argv), mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(module, "load_user_config", return_value=config), mock.patch.object(image_pipeline.requests, "post", return_value=response), contextlib.redirect_stdout(stdout):
                        self.assertEqual(module.main(), 0)
                    self.assertNotIn("private-origin.invalid", stdout.getvalue())
                    self.assertNotIn("https://", stdout.getvalue())
            self.assertEqual((root / "text" / "generated_01.png").read_bytes(), raw)
            self.assertEqual((root / "edit" / "source" / "prompt_01.png").read_bytes(), raw)
            self.assertNotIn("private-origin.invalid", (root / "edit" / "run.log").read_text())


if __name__ == "__main__":
    unittest.main()
