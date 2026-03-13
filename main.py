"""
main.py — Robotic Arm Voice-Controlled Pick-and-Place Orchestrator

Pipeline per iteration:
  1. Listen  : capture voice command via Smallest.ai STT
  2. Capture : take a snapshot with the wrist camera
  3. Detect  : locate the target object via Featherless VLM
  4. Execute : move the SO-101 arm and grab the object
  5. Skill   : log the pickup / check inventory via Toolhouse + Scrapegraph AI
"""

import os
import logging
import time
import sys
from datetime import datetime
from pathlib import Path

import cv2                         # OpenCV for camera capture
from anthropic import Anthropic    # used by Toolhouse internally (skill runner)
from toolhouse import Toolhouse, Provider

from listener import AudioInterface
from vision import RobotVision
from arm_control import ArmController

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger("main")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CAMERA_INDEX = 0                  # OpenCV camera index (0 = default USB cam)
IMAGE_SNAPSHOT_PATH = "snapshot.jpg"

TOOLHOUSE_API_KEY   = os.environ.get("TOOLHOUSE_API_KEY", "")
ANTHROPIC_API_KEY   = os.environ.get("ANTHROPIC_API_KEY", "")
SPREADSHEET_ID      = os.environ.get("PICKUP_SPREADSHEET_ID", "")
INVENTORY_URL       = os.environ.get("INVENTORY_URL", "")

WAKE_WORD = "pick up"             # must appear in command to trigger pickup
QUIT_WORDS = {"quit", "exit", "stop", "shutdown"}

# ---------------------------------------------------------------------------
# Toolhouse skill helpers
# ---------------------------------------------------------------------------

def _build_toolhouse_client() -> Toolhouse | None:
    if not TOOLHOUSE_API_KEY:
        logger.warning("TOOLHOUSE_API_KEY not set — Toolhouse skills disabled.")
        return None
    return Toolhouse(api_key=TOOLHOUSE_API_KEY, provider=Provider.ANTHROPIC)


def log_pickup_to_spreadsheet(
    th: Toolhouse,
    anthropic: Anthropic,
    command: str,
    x: int,
    y: int,
) -> None:
    """Use a Toolhouse skill to append a row to a Google Sheet."""
    timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    prompt = (
        f"Append a row to spreadsheet ID '{SPREADSHEET_ID}' with these columns: "
        f"timestamp={timestamp!r}, command={command!r}, pixel_x={x}, pixel_y={y}. "
        "Use the google_sheets_append tool."
    )
    _run_toolhouse_skill(th, anthropic, prompt)


def check_inventory(th: Toolhouse, anthropic: Anthropic, item: str) -> str:
    """Use Toolhouse + Scrapegraph AI to verify inventory for *item*."""
    if not INVENTORY_URL:
        return "Inventory URL not configured."
    prompt = (
        f"Use scrapegraph to fetch the inventory page at {INVENTORY_URL!r} "
        f"and check whether '{item}' is listed as available. "
        "Return a brief yes/no answer with the current stock count if shown."
    )
    return _run_toolhouse_skill(th, anthropic, prompt)


def _run_toolhouse_skill(
    th: Toolhouse,
    anthropic: Anthropic,
    prompt: str,
    model: str = "claude-sonnet-4-6",
) -> str:
    """Invoke Toolhouse tool-use loop and return the final assistant text."""
    messages = [{"role": "user", "content": prompt}]

    # First call: Claude decides which tool to use
    response = anthropic.messages.create(
        model=model,
        max_tokens=512,
        tools=th.get_tools(),
        messages=messages,
    )

    # Toolhouse runs the tool(s) and injects results
    messages = th.run_tools(response, messages=messages)

    # Second call: Claude summarises the tool output
    final = anthropic.messages.create(
        model=model,
        max_tokens=256,
        tools=th.get_tools(),
        messages=messages,
    )
    return final.content[0].text if final.content else ""


# ---------------------------------------------------------------------------
# Camera helper
# ---------------------------------------------------------------------------

def capture_image(path: str = IMAGE_SNAPSHOT_PATH) -> str:
    """Capture a single frame from the wrist camera and save to *path*."""
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera index {CAMERA_INDEX}")
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        raise RuntimeError("Failed to capture frame from camera.")
    cv2.imwrite(path, frame)
    logger.info("Snapshot saved → %s", path)
    return path


# ---------------------------------------------------------------------------
# Main orchestration loop
# ---------------------------------------------------------------------------

def main() -> None:
    logger.info("=== Robotic Arm Voice Controller starting up ===")

    # -- Initialise subsystems --
    audio   = AudioInterface()
    vision  = RobotVision()
    arm     = ArmController()

    th         = _build_toolhouse_client()
    anthropic  = Anthropic(api_key=ANTHROPIC_API_KEY) if th else None

    # -- Calibrate arm on startup --
    arm.calibrate()
    audio.speak("System ready. Say 'pick up' followed by the object name.")

    # -- Main loop --
    try:
        while True:
            # 1. Listen for a voice command
            try:
                command = audio.listen()
            except Exception as exc:
                logger.error("STT error: %s", exc)
                time.sleep(1)
                continue

            if not command:
                continue

            # Quit command
            if any(qw in command.lower() for qw in QUIT_WORDS):
                audio.speak("Shutting down. Goodbye.")
                break

            # Must contain wake word
            if WAKE_WORD not in command.lower():
                logger.info("No wake word detected in: %r", command)
                continue

            # Extract the target description (everything after "pick up")
            target = command.lower().split(WAKE_WORD, 1)[-1].strip()
            if not target:
                audio.speak("I didn't catch what to pick up. Please try again.")
                continue

            logger.info("Target: %r", target)

            # [Optional] Check inventory before attempting pickup
            if th and INVENTORY_URL:
                audio.speak(f"Checking inventory for {target}.")
                inventory_result = check_inventory(th, anthropic, target)
                logger.info("Inventory check: %s", inventory_result)
                audio.speak(inventory_result)
                if "no" in inventory_result.lower() or "unavailable" in inventory_result.lower():
                    audio.speak(f"{target} is not available in inventory. Skipping.")
                    continue

            audio.speak(f"Looking for {target}.")

            # 2. Capture a camera image
            try:
                image_path = capture_image()
            except Exception as exc:
                logger.error("Camera error: %s", exc)
                audio.speak("Camera error. Please check the connection.")
                continue

            # 3. Detect the object via VLM
            try:
                x, y = vision.detect_object(target, image_path)
                logger.info("Object detected at pixel (%d, %d)", x, y)
            except ValueError as exc:
                logger.warning("Detection failed: %s", exc)
                audio.speak(f"I could not locate {target} in the image. Please try again.")
                continue
            except Exception as exc:
                logger.error("VLM error: %s", exc)
                audio.speak("Vision system error.")
                continue

            # 4. Execute pickup
            audio.speak(f"Picking up {target}.")
            try:
                arm.pickup_at_coords(x, y)
                audio.speak("Done! Object picked up successfully.")
            except Exception as exc:
                logger.error("Arm error: %s", exc)
                audio.speak("Arm error during pickup. Please check the arm.")
                continue

            # 5. Log the pickup via Toolhouse skill
            if th and SPREADSHEET_ID:
                try:
                    log_pickup_to_spreadsheet(th, anthropic, target, x, y)
                    logger.info("Pickup logged to spreadsheet.")
                except Exception as exc:
                    logger.warning("Toolhouse logging failed: %s", exc)

    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
        audio.speak("Interrupted. Goodbye.")
    finally:
        arm.disconnect()
        logger.info("=== Shutdown complete ===")


if __name__ == "__main__":
    main()
