import argparse
import base64
import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import text_to_image  # noqa: E402


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class TextToImageTests(unittest.TestCase):
    def test_decode_image_response(self):
        raw = b"fake-image-bytes"
        response = FakeResponse({"data": [{"b64_json": base64.b64encode(raw).decode()}]})
        self.assertEqual(text_to_image.decode_image_response(response), raw)

    def test_generate_one_posts_expected_payload(self):
        raw = b"image"
        response = FakeResponse({"data": [{"b64_json": base64.b64encode(raw).decode()}]})
        with mock.patch.object(text_to_image.requests, "post", return_value=response) as post:
            result = text_to_image.generate_one(
                prompt="水彩猫",
                api_key="sk-test",
                base_url="https://api.example.test/v1",
                model="gpt-image-2",
                size="1024x1024",
                quality="high",
                output_format="webp",
                output_compression=80,
                request_timeout=120,
                max_retries=1,
            )

        self.assertEqual(result, raw)
        post.assert_called_once_with(
            "https://api.example.test/v1/images/generations",
            headers={
                "Authorization": "Bearer sk-test",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-image-2",
                "prompt": "水彩猫",
                "n": 1,
                "size": "1024x1024",
                "quality": "high",
                "output_format": "webp",
                "output_compression": 80,
            },
            timeout=120,
        )

    def test_validation_accepts_custom_size(self):
        args = argparse.Namespace(
            size="800x600",
            output_compression=None,
            request_timeout=120,
            max_retries=2,
            request_interval=0,
            filename_prefix="generated",
            prompt=["test"],
        )
        text_to_image.validate_args(args, "sk-test", "gpt-image-2", "high", "png")

    def test_validation_rejects_png_compression(self):
        args = argparse.Namespace(
            size="auto",
            output_compression=80,
            request_timeout=120,
            max_retries=2,
            request_interval=0,
            filename_prefix="generated",
            prompt=["test"],
        )
        with self.assertRaisesRegex(ValueError, "jpeg or webp"):
            text_to_image.validate_args(args, "sk-test", "gpt-image-2", "high", "png")


if __name__ == "__main__":
    unittest.main()
