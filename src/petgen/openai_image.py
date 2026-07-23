from __future__ import annotations

import base64
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path

import requests

from petgen.openai_common import format_http_error


class ImageGenerationError(RuntimeError):
    """Raised when the image API request or response is not usable."""


@dataclass(frozen=True)
class ImageRequestConfig:
    api_key: str
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-image-2"
    size: str = "1536x1024"
    quality: str = "high"
    timeout_seconds: int = 180

    @classmethod
    def from_env(
        cls,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        size: str | None = None,
        quality: str | None = None,
    ) -> "ImageRequestConfig":
        resolved_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not resolved_key:
            raise ImageGenerationError(
                "OPENAI_API_KEY is required. Set it in the environment or pass --api-key."
            )
        return cls(
            api_key=resolved_key,
            base_url=(base_url or os.environ.get("OPENAI_BASE_URL") or cls.base_url).rstrip("/"),
            model=model or os.environ.get("OPENAI_IMAGE_MODEL") or cls.model,
            size=size or os.environ.get("OPENAI_IMAGE_SIZE") or cls.size,
            quality=quality or os.environ.get("OPENAI_IMAGE_QUALITY") or cls.quality,
        )


class OpenAIImageClient:
    """Small OpenAI-compatible Image API client.

    Text-only requests call /images/generations. Requests with reference images call
    /images/edits using multipart image[] fields, matching the current Image API docs.
    """

    def __init__(self, config: ImageRequestConfig, session: requests.Session | None = None) -> None:
        self.config = config
        self.session = session or requests.Session()

    def generate(self, prompt: str, reference_images: list[Path] | None = None) -> bytes:
        refs = reference_images or []
        if refs:
            return self._edit_with_references(prompt, refs)
        return self._generate_from_text(prompt)

    def _generate_from_text(self, prompt: str) -> bytes:
        response = self.session.post(
            f"{self.config.base_url}/images/generations",
            headers=self._json_headers(),
            json={
                "model": self.config.model,
                "prompt": prompt,
                "size": self.config.size,
                "quality": self.config.quality,
                "output_format": "png",
            },
            timeout=self.config.timeout_seconds,
        )
        return self._extract_image_bytes(response)

    def _edit_with_references(self, prompt: str, reference_images: list[Path]) -> bytes:
        opened_files = []
        try:
            files = []
            for image_path in reference_images:
                if not image_path.exists():
                    raise ImageGenerationError(f"reference image does not exist: {image_path}")
                mime = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
                handle = image_path.open("rb")
                opened_files.append(handle)
                files.append(("image[]", (image_path.name, handle, mime)))

            response = self.session.post(
                f"{self.config.base_url}/images/edits",
                headers=self._auth_headers(),
                data={
                    "model": self.config.model,
                    "prompt": prompt,
                    "size": self.config.size,
                    "quality": self.config.quality,
                },
                files=files,
                timeout=self.config.timeout_seconds,
            )
            return self._extract_image_bytes(response)
        finally:
            for handle in opened_files:
                handle.close()

    def _json_headers(self) -> dict[str, str]:
        headers = self._auth_headers()
        headers["Content-Type"] = "application/json"
        return headers

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.config.api_key}"}

    def _extract_image_bytes(self, response: requests.Response) -> bytes:
        if response.status_code < 200 or response.status_code >= 300:
            raise ImageGenerationError(format_http_error(response, label="image"))

        try:
            payload = response.json()
        except ValueError as exc:
            raise ImageGenerationError("image API returned non-JSON response") from exc

        data = payload.get("data")
        if not isinstance(data, list) or not data:
            raise ImageGenerationError("image API response did not contain data[0]")

        first = data[0]
        if not isinstance(first, dict):
            raise ImageGenerationError("image API response data[0] is not an object")

        b64 = first.get("b64_json")
        if isinstance(b64, str) and b64:
            try:
                return base64.b64decode(b64, validate=False)
            except ValueError as exc:
                raise ImageGenerationError("image API returned invalid base64 image data") from exc

        url = first.get("url")
        if isinstance(url, str) and url:
            download = self.session.get(url, timeout=self.config.timeout_seconds)
            if download.status_code < 200 or download.status_code >= 300:
                raise ImageGenerationError(format_http_error(download, label="image"))
            return download.content

        raise ImageGenerationError("image API response did not include b64_json or url")
