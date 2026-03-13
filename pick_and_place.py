"""
SO-101 Intelligent Pick-and-Place
==================================
Integrations:
  - Hardware  : Cyberwave SO-101 via lerobot
  - Intelligence : Featherless.ai (serverless LLM) — object fragility classification
  - Feedback  : ElevenLabs TTS — "Handling with care" before fragile picks
  - Actions   : Toolhouse — log successful place to a spreadsheet
"""

from __future__ import annotations

import os
import time
import datetime
import tempfile
import logging
from dataclasses import dataclass
from typing import Literal

# ── Third-party ──────────────────────────────────────────────────────────────
import openai                        # Featherless.ai uses an OpenAI-compatible API
from elevenlabs.client import ElevenLabs
from elevenlabs import play, save
from toolhouse import Toolhouse       # pip install toolhouse
import anthropic                      # Toolhouse pairs with an LLM; we use Claude here

# ── lerobot SO-101 ────────────────────────────────────────────────────────────
# lerobot exposes robot classes through its device registry.
# Adjust the import path if your lerobot version differs.
from lerobot.common.robot_devices.robots.factory import make_robot
from lerobot.common.robot_devices.utils import RobotDeviceNotConnectedError

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION  — set via environment variables or edit directly below
# ─────────────────────────────────────────────────────────────────────────────

FEATHERLESS_API_KEY  = os.environ.get("FEATHERLESS_API_KEY",  "YOUR_FEATHERLESS_API_KEY")
ELEVENLABS_API_KEY   = os.environ.get("ELEVENLABS_API_KEY",   "YOUR_ELEVENLABS_API_KEY")
TOOLHOUSE_API_KEY    = os.environ.get("TOOLHOUSE_API_KEY",    "YOUR_TOOLHOUSE_API_KEY")
ANTHROPIC_API_KEY    = os.environ.get("ANTHROPIC_API_KEY",    "YOUR_ANTHROPIC_API_KEY")

# Featherless.ai model — choose any model hosted on their platform
FEATHERLESS_MODEL    = "meta-llama/Llama-3.1-8B-Instruct"

# ElevenLabs voice — "Aria" (or any voice_id from your ElevenLabs account)
ELEVENLABS_VOICE_ID  = "9BWtsMINqrJLrRacOk9x"   # Aria — calm, gentle voice

# Torque limits (0–100 scale used by lerobot / Dynamixel percent of max torque)
TORQUE_FRAGILE = 20   # gentle grip
TORQUE_ROBUST  = 60   # firm grip

# Robot config name registered with lerobot (adjust to match your setup)
ROBOT_CONFIG_NAME = "so101"

# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# DATA
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ObjectInfo:
    name: str
    description: str
    fragility: Literal["Fragile", "Robust"] = "Robust"


# Pre-defined waypoints for the SO-101 (joint angles in degrees).
# Record your own with `lerobot record` or the teleoperation GUI.
WAYPOINTS = {
    "home":       [  0.0,  -30.0,   90.0,  -60.0,    0.0,   0.0],
    "pre_pick":   [ 45.0,   20.0,   60.0,  -45.0,   10.0,   0.0],
    "pick":       [ 45.0,   35.0,   70.0,  -50.0,   10.0,   0.0],
    "lift":       [ 45.0,   10.0,   55.0,  -40.0,   10.0,   0.0],
    "pre_place":  [-45.0,   20.0,   60.0,  -45.0,  -10.0,   0.0],
    "place":      [-45.0,   35.0,   70.0,  -50.0,  -10.0,   0.0],
}


# ─────────────────────────────────────────────────────────────────────────────
# 1.  INTELLIGENCE — Featherless.ai: classify object fragility
# ─────────────────────────────────────────────────────────────────────────────

def classify_object(obj: ObjectInfo) -> Literal["Fragile", "Robust"]:
    """
    Calls a serverless LLM on Featherless.ai to decide whether the object
    is Fragile or Robust based on its text description.
    Returns 'Fragile' or 'Robust'.
    """
    log.info("Querying Featherless.ai to classify '%s'…", obj.name)

    client = openai.OpenAI(
        api_key=FEATHERLESS_API_KEY,
        base_url="https://api.featherless.ai/v1",
    )

    system_prompt = (
        "You are a robotic pick-and-place assistant. "
        "Given a description of an object, classify it as exactly one of: "
        "'Fragile' or 'Robust'. "
        "Respond with a single word only — either 'Fragile' or 'Robust'. "
        "No punctuation, no explanation."
    )

    user_prompt = (
        f"Object name: {obj.name}\n"
        f"Description: {obj.description}\n\n"
        "Classification:"
    )

    response = client.chat.completions.create(
        model=FEATHERLESS_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        max_tokens=5,
        temperature=0.0,
    )

    raw = response.choices[0].message.content.strip()
    fragility: Literal["Fragile", "Robust"] = "Fragile" if "fragile" in raw.lower() else "Robust"
    log.info("  → Classification: %s  (raw LLM output: '%s')", fragility, raw)
    return fragility


# ─────────────────────────────────────────────────────────────────────────────
# 2.  FEEDBACK — ElevenLabs: speak "Handling with care"
# ─────────────────────────────────────────────────────────────────────────────

def speak_handling_with_care() -> None:
    """
    Uses ElevenLabs to synthesise and play 'Handling with care'
    in a calm, gentle voice before picking a fragile object.
    """
    log.info("Generating ElevenLabs TTS: 'Handling with care'…")

    el_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

    audio = el_client.text_to_speech.convert(
        voice_id=ELEVENLABS_VOICE_ID,
        text="Handling with care.",
        model_id="eleven_turbo_v2_5",          # low-latency model
        voice_settings={
            "stability": 0.85,                 # calm, steady delivery
            "similarity_boost": 0.75,
            "style": 0.2,                      # gentle/understated
            "use_speaker_boost": False,
        },
    )

    # Save to a temp file then play via the elevenlabs helper
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = tmp.name

    save(audio, tmp_path)
    play(audio)   # plays through the system's default audio device
    log.info("  → Audio played.")


# ─────────────────────────────────────────────────────────────────────────────
# 3.  ACTIONS — Toolhouse: log successful place to spreadsheet
# ─────────────────────────────────────────────────────────────────────────────

def log_to_spreadsheet(obj: ObjectInfo, timestamp: str) -> None:
    """
    Uses a Toolhouse tool named 'Log to Spreadsheet' to record
    the successful place action with a timestamp.
    """
    log.info("Logging to spreadsheet via Toolhouse…")

    th = Toolhouse(api_key=TOOLHOUSE_API_KEY, provider="anthropic")

    # Build the initial user message describing what to log
    messages = [
        {
            "role": "user",
            "content": (
                f"Use the 'Log to Spreadsheet' tool to record the following:\n"
                f"- Object: {obj.name}\n"
                f"- Fragility: {obj.fragility}\n"
                f"- Action: Place completed successfully\n"
                f"- Timestamp: {timestamp}\n"
            ),
        }
    ]

    # First call: let Claude request the tool
    claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        tools=th.get_tools(),
        messages=messages,
    )

    # Run any tool calls Toolhouse needs, then get the final reply
    messages += th.run_tools(response)

    if response.stop_reason == "tool_use":
        final = claude.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=128,
            tools=th.get_tools(),
            messages=messages,
        )
        log.info("  → Toolhouse response: %s", final.content[0].text if final.content else "ok")
    else:
        log.info("  → Toolhouse response: %s", response.content[0].text if response.content else "ok")


# ─────────────────────────────────────────────────────────────────────────────
# 4.  HARDWARE — SO-101 robot helpers
# ─────────────────────────────────────────────────────────────────────────────

def set_max_torque(robot, torque_percent: int) -> None:
    """
    Apply a max-torque percentage to all joints on the SO-101.
    lerobot exposes motor bus objects; we write directly to the 'torque_enable'
    and 'goal_current' (or equivalent) registers.

    NOTE: Register names depend on your firmware version.
    Common Dynamixel register for torque limiting: 'torque_limit' (0–1023 for MX)
    or 'goal_current' for XM/XH series.  Adjust as needed.
    """
    torque_value = int(torque_percent / 100 * 1023)   # map percent → raw register value
    log.info("Setting max torque → %d%% (raw: %d)", torque_percent, torque_value)

    for bus in robot.motor_buses.values():
        try:
            bus.write("Torque_Limit", [torque_value] * len(bus.motor_names))
        except Exception as exc:
            # Some firmware uses a different register name
            log.warning("  torque_limit write failed (%s); trying Goal_Current…", exc)
            try:
                bus.write("Goal_Current", [torque_value] * len(bus.motor_names))
            except Exception as exc2:
                log.error("  Could not set torque: %s", exc2)


def move_to_waypoint(robot, name: str, move_duration: float = 2.0) -> None:
    """
    Interpolates the arm to a named joint-angle waypoint.
    lerobot's send_action() accepts a dict mapping motor name → goal position.
    """
    target_angles = WAYPOINTS[name]
    motor_names   = list(robot.motor_names)           # ordered list from the robot config
    action        = dict(zip(motor_names, target_angles))

    log.info("Moving to waypoint '%s': %s", name, action)
    robot.send_action(action)
    time.sleep(move_duration)   # wait for the motion to complete


def open_gripper(robot) -> None:
    """Open the end-effector gripper."""
    gripper_motor = robot.motor_names[-1]   # gripper is the last motor on SO-101
    robot.send_action({gripper_motor: 0.0})
    time.sleep(0.5)


def close_gripper(robot, torque_percent: int) -> None:
    """Close the gripper with torque already limited to torque_percent."""
    gripper_motor = robot.motor_names[-1]
    close_pos = 50.0 if torque_percent <= TORQUE_FRAGILE else 80.0
    robot.send_action({gripper_motor: close_pos})
    time.sleep(0.5)


# ─────────────────────────────────────────────────────────────────────────────
# 5.  MAIN PICK-AND-PLACE TASK
# ─────────────────────────────────────────────────────────────────────────────

def pick_and_place(obj: ObjectInfo) -> None:
    """
    Full pipeline:
      1. Classify fragility via Featherless.ai LLM
      2. If Fragile → speak via ElevenLabs
      3. Set hardware torque (Cyberwave SO-101)
      4. Execute pick-and-place motion
      5. Log success to spreadsheet via Toolhouse
    """
    log.info("=" * 60)
    log.info("Starting pick-and-place for object: '%s'", obj.name)
    log.info("Description: %s", obj.description)

    # ── Step 1: Classify ────────────────────────────────────────────────────
    obj.fragility = classify_object(obj)

    # ── Step 2: ElevenLabs feedback if fragile ───────────────────────────────
    if obj.fragility == "Fragile":
        speak_handling_with_care()

    # ── Step 3: Connect to robot & configure torque ──────────────────────────
    log.info("Connecting to SO-101 robot…")
    robot = make_robot(ROBOT_CONFIG_NAME)

    try:
        robot.connect()
        log.info("Robot connected.")

        torque = TORQUE_FRAGILE if obj.fragility == "Fragile" else TORQUE_ROBUST
        log.info(
            "Hardware torque set to %d%% (%s object)",
            torque, obj.fragility
        )
        set_max_torque(robot, torque)

        # ── Step 4: Motion sequence ──────────────────────────────────────────
        log.info("--- PICK SEQUENCE ---")
        move_to_waypoint(robot, "home")
        open_gripper(robot)
        move_to_waypoint(robot, "pre_pick")
        move_to_waypoint(robot, "pick", move_duration=1.5)
        close_gripper(robot, torque)
        move_to_waypoint(robot, "lift")

        log.info("--- PLACE SEQUENCE ---")
        move_to_waypoint(robot, "pre_place")
        move_to_waypoint(robot, "place", move_duration=1.5)
        open_gripper(robot)
        move_to_waypoint(robot, "home")

        place_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        log.info("Place complete at %s", place_timestamp)

        # ── Step 5: Log via Toolhouse ────────────────────────────────────────
        log_to_spreadsheet(obj, place_timestamp)

    except RobotDeviceNotConnectedError:
        log.error(
            "Robot not found. Check USB/serial connection and that "
            "the SO-101 is powered on."
        )
    except Exception as exc:
        log.exception("Unexpected error during pick-and-place: %s", exc)
    finally:
        try:
            robot.disconnect()
            log.info("Robot disconnected.")
        except Exception:
            pass

    log.info("Task complete for '%s'.", obj.name)
    log.info("=" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT — demo with two objects
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    demo_objects = [
        ObjectInfo(
            name="Crystal Wine Glass",
            description=(
                "A thin-walled hand-blown crystal glass, highly susceptible "
                "to cracking under pressure or vibration."
            ),
        ),
        ObjectInfo(
            name="Steel Hex Bolt",
            description=(
                "A solid M8 zinc-plated steel hex bolt, 50 mm long, "
                "rugged and completely unaffected by normal handling forces."
            ),
        ),
    ]

    for item in demo_objects:
        pick_and_place(item)
