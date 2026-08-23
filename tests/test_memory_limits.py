import io
import os
import tempfile
import unittest

from PIL import Image, ImageDraw

import pipeline


class FakeResponse:
    def __init__(self, content, include_length=True):
        self.status_code = 200
        self.headers = {"Content-Type": "image/jpeg"}
        if include_length:
            self.headers["Content-Length"] = str(len(content))
        self._content = content
        self.closed = False

    def iter_content(self, chunk_size):
        for offset in range(0, len(self._content), chunk_size):
            yield self._content[offset:offset + chunk_size]

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, response):
        self.response = response

    def get(self, *args, **kwargs):
        return self.response


def jpeg_bytes(size, checkerboard=False):
    with Image.new("RGB", size, "white") as image:
        if checkerboard:
            draw = ImageDraw.Draw(image)
            square = 80
            for y in range(0, size[1], square):
                for x in range(0, size[0], square):
                    if (x // square + y // square) % 2:
                        draw.rectangle((x, y, x + square - 1, y + square - 1), fill="black")
        output = io.BytesIO()
        image.save(output, "JPEG", quality=90)
        return output.getvalue()


class ProcessImageMemoryLimitTests(unittest.TestCase):
    def setUp(self):
        self.original_session = pipeline.session

    def tearDown(self):
        pipeline.session = self.original_session

    def test_rejects_response_over_byte_limit_without_content_length(self):
        response = FakeResponse(b"x" * (pipeline.MAX_DOWNLOAD_BYTES + 1), include_length=False)
        pipeline.session = FakeSession(response)

        result = pipeline.process_image("https://example.test/large.jpg", (700, 1000), set())

        self.assertIsNone(result)
        self.assertTrue(response.closed)

    def test_rejects_excessive_dimensions_before_decode(self):
        content = jpeg_bytes((4000, 2100))
        response = FakeResponse(content)
        pipeline.session = FakeSession(response)

        result = pipeline.process_image("https://example.test/huge.jpg", (700, 1000), set())

        self.assertIsNone(result)
        self.assertTrue(response.closed)

    def test_normal_image_is_resized_and_saved(self):
        content = jpeg_bytes((1600, 1200), checkerboard=True)
        response = FakeResponse(content)
        pipeline.session = FakeSession(response)

        with tempfile.TemporaryDirectory() as output_dir:
            result = pipeline.process_image(
                "https://example.test/normal.jpg",
                (700, 1000),
                set(),
                save_dir=output_dir,
            )

            self.assertIsNotNone(result)
            self.assertTrue(os.path.exists(result))
            with Image.open(result) as saved:
                self.assertEqual(saved.size, (700, 1000))
        self.assertTrue(response.closed)


if __name__ == "__main__":
    unittest.main()
