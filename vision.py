import os
import re
import base64
import logging
from pathlib import Path
from openai import OpenAI          # featherless uses the OpenAI-compatible API

logger = logging.getLogger(__name__)


# Default VLM available on Featherless that supports vision inputs.
# Swap for any other vision-capable model on the platform.
DEFAULT_VLM = "Qwen/Qwen2.5-VL-72B-Instruct"

SYSTEM_PROMPT = (
    "You are a vision assistant for a robotic arm. "
    "Your sole task is to identify a target object in the image and return its "
    "pixel location. Always respond in the exact format:\n"
    "COORDS: X=<integer> Y=<integer>\n"
    "Do not include any other text."
)

USER_PROMPT_TEMPLATE = (
    "Locate '{target}' in the image and return its centre pixel coordinates. "
    "Use the format: COORDS: X=<int> Y=<int>"
)


class RobotVision:
    """Uses the Featherless VLM API to detect objects in images."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_VLM,
        base_url: str = "https://api.featherless.ai/v1",
    ):
        self._api_key = api_key or os.environ["FEATHERLESS_API_KEY"]
        self._model = model
        self._client = OpenAI(api_key=self._api_key, base_url=base_url)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def detect_object(self, command: str, image_path: str) -> tuple[int, int]:
        """Detect *command* target in *image_path* and return (X, Y) pixel coords.

        Args:
            command:    Natural-language description of the target object,
                        e.g. 'the red block' or 'the blue cylinder on the left'.
            image_path: Absolute or relative path to a JPEG/PNG image file.

        Returns:
            (x, y) pixel coordinates of the object's centre.

        Raises:
            FileNotFoundError: If *image_path* does not exist.
            ValueError:        If the VLM response cannot be parsed.
        """
        image_b64 = self._encode_image(image_path)
        mime_type = self._mime_type(image_path)
        prompt = USER_PROMPT_TEMPLATE.format(target=command)

        logger.info("Querying VLM for %r in %s", command, image_path)
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_b64}"
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                },
            ],
            max_tokens=64,
            temperature=0.0,
        )

        raw = response.choices[0].message.content or ""
        logger.debug("VLM raw response: %r", raw)
        x, y = self._parse_coords(raw)
        logger.info("Detected %r at (%d, %d)", command, x, y)
        return x, y

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _encode_image(image_path: str) -> str:
        """Return the base-64-encoded contents of *image_path*."""
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")
        with open(path, "rb") as fh:
            return base64.b64encode(fh.read()).decode("utf-8")

    @staticmethod
    def _mime_type(image_path: str) -> str:
        suffix = Path(image_path).suffix.lower()
        return {"jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}.get(
            suffix, "image/jpeg"
        )

    @staticmethod
    def _parse_coords(text: str) -> tuple[int, int]:
        """Extract X and Y from a string like 'COORDS: X=320 Y=240'."""
        match = re.search(r"X\s*=\s*(\d+)\s+Y\s*=\s*(\d+)", text, re.IGNORECASE)
        if not match:
            raise ValueError(
                f"Could not parse coordinates from VLM response: {text!r}. "
                "Expected format: COORDS: X=<int> Y=<int>"
            )
        return int(match.group(1)), int(match.group(2))
