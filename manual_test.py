"""
manual_test.py — Command-line manual control interface for the SO-101 arm.

Usage examples:
  python manual_test.py elevate
  python manual_test.py lower --step 8
  python manual_test.py spread
  python manual_test.py tighten
  python manual_test.py lift-hold
  python manual_test.py stop
  python manual_test.py --port COM3 --robot-id my_custom_arm elevate
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

# ---------------------------------------------------------------------------
# lerobot imports
# ---------------------------------------------------------------------------
try:
    from lerobot.common.robot_devices.motors.dynamixel import (
        DynamixelMotorsBus,
        TorqueMode,
    )
    from lerobot.common.robot_devices.robots.manipulator import ManipulatorRobot
    from lerobot.common.robot_devices.robots.factory import make_robot
    LEROBOT_AVAILABLE = True
except ImportError:
    LEROBOT_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
log = logging.getLogger("manual_test")

# ---------------------------------------------------------------------------
# Tuneable defaults  (override via CLI flags)
# ---------------------------------------------------------------------------

DEFAULT_ROBOT_ID = "my_awesome_follower_arm"
DEFAULT_PORT     = "/dev/ttyUSB0"     # Windows: "COM3", macOS: "/dev/tty.usbserial-*"
DEFAULT_BAUDRATE = 1_000_000

# Joint names in bus order (SO-101, 6-DOF)
MOTOR_NAMES = [
    "shoulder_pan",   # J1
    "shoulder_tilt",  # J2
    "elbow",          # J3
    "wrist_roll",     # J4
    "wrist_pitch",    # J5
    "gripper",        # J6
]

# Joint limits (degrees)
JOINT_LIMITS: dict[str, tuple[float, float]] = {
    "shoulder_pan":  (-135.0, 135.0),
    "shoulder_tilt": (-90.0,   90.0),
    "elbow":         (-135.0, 135.0),
    "wrist_roll":    (-90.0,   90.0),
    "wrist_pitch":   (-90.0,   90.0),
    "gripper":       (  0.0,  100.0),
}

# Gripper presets
GRIPPER_OPEN   = 100.0   # fully open
GRIPPER_CLOSED =  30.0   # safe closed (light grasp)

# Default angular step for elevate / lower commands (degrees)
DEFAULT_Z_STEP = 10.0

# P-gain written to every motor on connect to suppress oscillation
P_COEFFICIENT = 16


# ---------------------------------------------------------------------------
# Helper — clamp a value to joint limits
# ---------------------------------------------------------------------------

def _clamp(joint: str, value: float) -> float:
    lo, hi = JOINT_LIMITS[joint]
    clamped = max(lo, min(hi, value))
    if clamped != value:
        log.warning(
            "Joint %r clamped from %.1f to %.1f (limit: [%.1f, %.1f])",
            joint, value, clamped, lo, hi,
        )
    return clamped


# ---------------------------------------------------------------------------
# ManualArmTester
# ---------------------------------------------------------------------------

class ManualArmTester:
    """
    Manual CLI controller for the SO-101 arm.

    Connects directly to the Dynamixel motor bus, loads calibration from the
    lerobot cache for *robot_id*, and exposes discrete subcommands.
    """

    def __init__(
        self,
        port: str = DEFAULT_PORT,
        baudrate: int = DEFAULT_BAUDRATE,
        robot_id: str = DEFAULT_ROBOT_ID,
    ) -> None:
        if not LEROBOT_AVAILABLE:
            log.error(
                "lerobot is not installed. Run: pip install lerobot"
            )
            sys.exit(1)

        self.robot_id = robot_id
        self._port    = port
        self._bus: DynamixelMotorsBus | None = None
        self._connect(port, baudrate)

    # ------------------------------------------------------------------
    # Connection & setup
    # ------------------------------------------------------------------

    def _connect(self, port: str, baudrate: int) -> None:
        """Open the motor bus, load calibration, and tune P-gains."""
        log.info("Connecting to SO-101 on %s @ %d baud…", port, baudrate)

        motors = {name: (idx + 1, "x_series") for idx, name in enumerate(MOTOR_NAMES)}

        self._bus = DynamixelMotorsBus(
            port=port,
            motors=motors,
        )
        self._bus.connect()

        # Load calibration written by `lerobot calibrate` for this robot ID
        self._bus.set_calibration(self._load_calibration())

        # Enable torque on all motors
        self._bus.write("Torque_Enable", [TorqueMode.ENABLED.value] * len(MOTOR_NAMES))

        # Set P-coefficient on every motor to damp oscillation / shakiness
        for motor_name in MOTOR_NAMES:
            self._bus.write("P_Coefficient", motor_name, P_COEFFICIENT)

        log.info("Connected. P_Coefficient set to %d on all joints.", P_COEFFICIENT)

    def _load_calibration(self) -> dict:
        """
        Load the calibration saved by `lerobot calibrate` for *self.robot_id*.

        lerobot stores calibration as a JSON file at:
            ~/.cache/huggingface/lerobot/calibration/robots/<robot_id>.json

        Returns the calibration dict expected by DynamixelMotorsBus.set_calibration().
        """
        import json
        from pathlib import Path

        cache_path = (
            Path.home()
            / ".cache" / "huggingface" / "lerobot"
            / "calibration" / "robots"
            / f"{self.robot_id}.json"
        )

        if not cache_path.exists():
            log.warning(
                "Calibration file not found at %s — proceeding without calibration.\n"
                "Run `python -m lerobot.scripts.calibrate --robot-id %s` first.",
                cache_path, self.robot_id,
            )
            return {}

        with open(cache_path) as fh:
            calibration = json.load(fh)

        log.info("Loaded calibration from %s", cache_path)
        return calibration

    # ------------------------------------------------------------------
    # Read current joint positions
    # ------------------------------------------------------------------

    def _read_positions(self) -> dict[str, float]:
        """Return {motor_name: current_angle_deg} for all joints."""
        raw = self._bus.read("Present_Position", MOTOR_NAMES)
        return {name: float(val) for name, val in zip(MOTOR_NAMES, raw)}

    # ------------------------------------------------------------------
    # Write a single joint or a full pose
    # ------------------------------------------------------------------

    def _write_joint(self, joint: str, value: float) -> None:
        value = _clamp(joint, value)
        self._bus.write("Goal_Position", joint, value)
        log.info("  %s -> %.1f deg", joint, value)

    def _write_pose(self, pose: dict[str, float], label: str = "") -> None:
        """Write a complete joint pose, excluding any keys set to None."""
        if label:
            log.info("[%s]", label.upper())
        for joint, value in pose.items():
            if value is not None:
                self._write_joint(joint, value)
        time.sleep(0.8)   # allow motion to settle

    # ------------------------------------------------------------------
    # Subcommands
    # ------------------------------------------------------------------

    def lower(self, step: float = DEFAULT_Z_STEP) -> None:
        """
        Lower the arm by *step* degrees on shoulder_tilt and elbow,
        keeping the wrist_pitch compensated so the end-effector stays flat.

        A positive *step* moves the arm downward (toward the table).
        """
        log.info("CMD lower (step=%.1f deg)", step)
        pos = self._read_positions()

        new_tilt  = pos["shoulder_tilt"] + step          # tilt down
        new_elbow = pos["elbow"]         - step * 0.6    # partial elbow flex
        # Compensate wrist to keep orientation flat
        new_wrist = -(new_tilt - new_elbow)

        self._write_pose(
            {
                "shoulder_tilt": new_tilt,
                "elbow":         new_elbow,
                "wrist_pitch":   new_wrist,
            },
            label="lower",
        )

    def elevate(self, step: float = DEFAULT_Z_STEP) -> None:
        """
        Raise the arm by *step* degrees on shoulder_tilt and elbow,
        keeping the wrist_pitch compensated so the end-effector stays flat.
        """
        log.info("CMD elevate (step=%.1f deg)", step)
        pos = self._read_positions()

        new_tilt  = pos["shoulder_tilt"] - step          # tilt up
        new_elbow = pos["elbow"]         + step * 0.6    # partial elbow extend
        new_wrist = -(new_tilt - new_elbow)

        self._write_pose(
            {
                "shoulder_tilt": new_tilt,
                "elbow":         new_elbow,
                "wrist_pitch":   new_wrist,
            },
            label="elevate",
        )

    def spread(self) -> None:
        """Set gripper (J6) to fully open position (value: 100)."""
        log.info("CMD spread — opening gripper to %.0f", GRIPPER_OPEN)
        self._write_joint("gripper", GRIPPER_OPEN)
        time.sleep(0.4)

    def tighten(self) -> None:
        """Set gripper (J6) to safe closed position (value: 30)."""
        log.info("CMD tighten — closing gripper to %.0f", GRIPPER_CLOSED)
        self._write_joint("gripper", GRIPPER_CLOSED)
        time.sleep(0.4)

    def lift_hold(self, step: float = DEFAULT_Z_STEP) -> None:
        """
        Read the current gripper position, then raise the arm by *step*
        degrees WITHOUT sending any new command to the gripper joint.

        This preserves whatever grasp force the gripper already has,
        avoiding re-squeezing or releasing when lifting an object.
        """
        log.info("CMD lift-hold (step=%.1f deg)", step)
        pos = self._read_positions()

        gripper_now = pos["gripper"]
        log.info("  Gripper position retained at %.1f (no new command sent)", gripper_now)

        new_tilt  = pos["shoulder_tilt"] - step
        new_elbow = pos["elbow"]         + step * 0.6
        new_wrist = -(new_tilt - new_elbow)

        # Explicitly omit "gripper" from the write — no key, no command
        self._write_pose(
            {
                "shoulder_tilt": new_tilt,
                "elbow":         new_elbow,
                "wrist_pitch":   new_wrist,
            },
            label="lift-hold",
        )

    def stop(self) -> None:
        """
        Emergency stop — disable torque on all motors immediately.

        The arm will become compliant (back-drivable). Support the arm
        by hand before issuing this command if it is holding a load.
        """
        log.warning("CMD stop — disabling torque on ALL motors NOW")
        self._bus.write(
            "Torque_Enable",
            [TorqueMode.DISABLED.value] * len(MOTOR_NAMES),
        )
        log.warning("Torque disabled. Arm is now compliant.")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def disconnect(self) -> None:
        if self._bus is not None:
            try:
                self._bus.disconnect()
                log.info("Disconnected from motor bus.")
            except Exception as exc:
                log.debug("Disconnect error (ignored): %s", exc)
            finally:
                self._bus = None

    def __enter__(self) -> "ManualArmTester":
        return self

    def __exit__(self, *_) -> None:
        self.disconnect()

    def __del__(self) -> None:
        self.disconnect()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="manual_test.py",
        description="Manual CLI control for the SO-101 robotic arm.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
subcommands:
  lower      Lower the arm by decreasing shoulder/elbow angles (gripper stays flat)
  elevate    Raise the arm by increasing shoulder/elbow angles (gripper stays flat)
  spread     Open the gripper fully (J6 = 100)
  tighten    Close the gripper to a safe position (J6 = 30)
  lift-hold  Raise the arm WITHOUT re-commanding the gripper (preserves grasp)
  stop       Disable torque on all motors immediately (emergency stop)

examples:
  python manual_test.py elevate
  python manual_test.py lower --step 15
  python manual_test.py lift-hold --step 5
  python manual_test.py --port COM4 --robot-id my_awesome_follower_arm spread
  python manual_test.py stop
        """,
    )

    # -- Global options --
    parser.add_argument(
        "--port",
        default=DEFAULT_PORT,
        help=f"Serial port for the SO-101 (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--baudrate",
        type=int,
        default=DEFAULT_BAUDRATE,
        help=f"Serial baud rate (default: {DEFAULT_BAUDRATE})",
    )
    parser.add_argument(
        "--robot-id",
        default=DEFAULT_ROBOT_ID,
        metavar="ID",
        help=f"Robot ID used to locate the lerobot calibration cache (default: {DEFAULT_ROBOT_ID})",
    )
    parser.add_argument(
        "--step",
        type=float,
        default=DEFAULT_Z_STEP,
        metavar="DEG",
        help=f"Angular step in degrees for elevate / lower / lift-hold (default: {DEFAULT_Z_STEP})",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable DEBUG-level logging",
    )

    # -- Subcommands --
    sub = parser.add_subparsers(dest="command", metavar="subcommand")
    sub.required = True

    sub.add_parser("lower",     help="Lower the arm (decrease Z height)")
    sub.add_parser("elevate",   help="Raise the arm (increase Z height)")
    sub.add_parser("spread",    help="Open gripper fully (J6 = 100)")
    sub.add_parser("tighten",   help="Close gripper safely (J6 = 30)")
    sub.add_parser("lift-hold", help="Raise arm without re-commanding gripper")
    sub.add_parser("stop",      help="Disable all motor torque immediately")

    return parser


def main() -> None:
    parser = build_parser()
    args   = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    with ManualArmTester(
        port=args.port,
        baudrate=args.baudrate,
        robot_id=args.robot_id,
    ) as tester:
        cmd = args.command

        if cmd == "lower":
            tester.lower(step=args.step)
        elif cmd == "elevate":
            tester.elevate(step=args.step)
        elif cmd == "spread":
            tester.spread()
        elif cmd == "tighten":
            tester.tighten()
        elif cmd == "lift-hold":
            tester.lift_hold(step=args.step)
        elif cmd == "stop":
            tester.stop()
        else:
            parser.error(f"Unknown subcommand: {cmd!r}")


if __name__ == "__main__":
    main()
