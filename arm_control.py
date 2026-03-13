import logging
import math
import time

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# lerobot / SO-101 imports
# ---------------------------------------------------------------------------
try:
    from lerobot.common.robot_devices.robots.factory import make_robot
    from lerobot.common.robot_devices.robots.utils import Robot
    from lerobot.common.robot_devices.motors.dynamixel import TorqueMode
    LEROBOT_AVAILABLE = True
except ImportError:
    LEROBOT_AVAILABLE = False
    logger.warning(
        "lerobot not installed — ArmController will run in simulation mode."
    )


# ---------------------------------------------------------------------------
# SO-101 physical constants (adjust to your setup)
# ---------------------------------------------------------------------------

# Camera intrinsics / mounting
IMAGE_WIDTH_PX = 640
IMAGE_HEIGHT_PX = 480
CAMERA_FOV_X_DEG = 60.0          # horizontal field-of-view of the wrist cam
CAMERA_FOV_Y_DEG = 45.0          # vertical field-of-view

# Arm workspace (metres)
ARM_REACH_M = 0.30               # max reach from base centre
ARM_HEIGHT_PICKUP_M = 0.05       # fixed Z height for pickup plane
ARM_HEIGHT_LIFT_M = 0.20         # lift height after grabbing

# Joint limits (degrees) — SO-101 has 6 joints
JOINT_LIMITS = {
    "shoulder_pan":  (-135, 135),
    "shoulder_tilt": (-90,  90),
    "elbow":         (-135, 135),
    "wrist_roll":    (-90,  90),
    "wrist_pitch":   (-90,  90),
    "gripper":       (0,    100),  # 0 = fully open, 100 = fully closed
}

HOME_ANGLES = {
    "shoulder_pan":  0.0,
    "shoulder_tilt": 0.0,
    "elbow":         90.0,
    "wrist_roll":    0.0,
    "wrist_pitch":   -45.0,
    "gripper":       0.0,
}


class ArmController:
    """Controls the SO-101 robotic arm via lerobot."""

    def __init__(self, robot_config: dict | None = None, sim: bool = False):
        """
        Args:
            robot_config: lerobot robot config dict (passed to ``make_robot``).
                          If *None*, a default SO-101 USB config is used.
            sim:          Force simulation mode even if lerobot is available.
        """
        self._sim = sim or not LEROBOT_AVAILABLE
        self._robot: "Robot | None" = None

        if not self._sim:
            cfg = robot_config or self._default_config()
            self._robot = make_robot(cfg)
            self._robot.connect()
            logger.info("Connected to SO-101 arm.")
        else:
            logger.info("ArmController running in SIMULATION mode.")

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def calibrate(self) -> None:
        """Run the home-zeroing (calibration) sequence."""
        logger.info("Calibrating arm — moving to home position…")
        self._open_gripper()
        self._move_to_angles(HOME_ANGLES, speed=30)
        logger.info("Calibration complete.")

    def pickup_at_coords(self, x: int, y: int) -> None:
        """Pick up the object whose camera-pixel centre is at (x, y).

        Steps:
            1. Convert pixel → Cartesian workspace coordinates.
            2. Compute joint angles via analytic IK.
            3. Open gripper → move above target → descend → close → lift.

        Args:
            x: Pixel column of the target object centre.
            y: Pixel row    of the target object centre.
        """
        logger.info("Pickup requested at pixel (%d, %d)", x, y)

        wx, wy = self._pixel_to_workspace(x, y)
        logger.info("Workspace target: (%.3f m, %.3f m)", wx, wy)

        angles_above = self._ik(wx, wy, ARM_HEIGHT_LIFT_M)
        angles_pickup = self._ik(wx, wy, ARM_HEIGHT_PICKUP_M)

        # --- Grasp sequence ---
        self._open_gripper()
        self._move_to_angles(angles_above, speed=50)
        self._move_to_angles(angles_pickup, speed=30)
        self._close_gripper()
        time.sleep(0.3)                          # let gripper settle
        self._move_to_angles(angles_above, speed=30)
        logger.info("Pickup complete — object lifted.")

    # ------------------------------------------------------------------
    # Private — coordinate transforms
    # ------------------------------------------------------------------

    def _pixel_to_workspace(self, px: int, py: int) -> tuple[float, float]:
        """Map image pixel (px, py) → arm workspace (X, Y) in metres.

        Uses a simple pin-hole / flat-plane projection assuming the camera
        looks straight down at the pickup plane.
        """
        norm_x = (px - IMAGE_WIDTH_PX / 2.0) / (IMAGE_WIDTH_PX / 2.0)
        norm_y = (py - IMAGE_HEIGHT_PX / 2.0) / (IMAGE_HEIGHT_PX / 2.0)

        half_fov_x = math.radians(CAMERA_FOV_X_DEG / 2.0)
        half_fov_y = math.radians(CAMERA_FOV_Y_DEG / 2.0)

        wx = norm_x * ARM_REACH_M * math.tan(half_fov_x)
        wy = norm_y * ARM_REACH_M * math.tan(half_fov_y)
        return wx, wy

    # ------------------------------------------------------------------
    # Private — analytic IK (2-link planar + wrist)
    # ------------------------------------------------------------------

    def _ik(self, wx: float, wy: float, wz: float) -> dict[str, float]:
        """Analytic inverse-kinematics for the SO-101 (simplified 2-link).

        Returns a dict of joint angles in degrees.
        """
        L1 = 0.175   # upper arm link length (m)
        L2 = 0.135   # forearm link length (m)

        # Pan in the horizontal plane
        shoulder_pan = math.degrees(math.atan2(wy, wx))

        # Reach distance in the sagittal plane
        r = math.sqrt(wx**2 + wy**2)
        # Vertical drop from shoulder pivot to pickup plane
        h = ARM_HEIGHT_LIFT_M - wz   # positive = arm must reach down

        dist = math.sqrt(r**2 + h**2)
        dist = min(dist, L1 + L2 - 1e-4)   # clamp to reachable workspace

        # Law of cosines
        cos_elbow = (L1**2 + L2**2 - dist**2) / (2 * L1 * L2)
        cos_elbow = max(-1.0, min(1.0, cos_elbow))
        elbow = math.degrees(math.acos(cos_elbow))

        alpha = math.atan2(h, r)
        cos_alpha2 = (L1**2 + dist**2 - L2**2) / (2 * L1 * dist)
        cos_alpha2 = max(-1.0, min(1.0, cos_alpha2))
        alpha2 = math.acos(cos_alpha2)
        shoulder_tilt = math.degrees(alpha + alpha2)

        wrist_pitch = -(shoulder_tilt - elbow)   # keep end-effector level

        angles = {
            "shoulder_pan":  shoulder_pan,
            "shoulder_tilt": shoulder_tilt,
            "elbow":         elbow,
            "wrist_roll":    0.0,
            "wrist_pitch":   wrist_pitch,
            "gripper":       HOME_ANGLES["gripper"],
        }
        return self._clamp_angles(angles)

    @staticmethod
    def _clamp_angles(angles: dict[str, float]) -> dict[str, float]:
        """Clamp all joint angles to their hardware limits."""
        return {
            joint: max(lo, min(hi, val))
            for joint, (lo, hi), val in (
                (j, JOINT_LIMITS[j], angles[j]) for j in angles
            )
        }

    # ------------------------------------------------------------------
    # Private — motor commands
    # ------------------------------------------------------------------

    def _move_to_angles(self, angles: dict[str, float], speed: int = 50) -> None:
        if self._sim:
            logger.debug("SIM move_to_angles: %s", angles)
            time.sleep(0.5)
            return

        # lerobot Robot exposes a .send_action() or similar interface.
        # Adjust the key names to match your motor IDs.
        import torch
        action = torch.tensor(
            [angles[j] for j in sorted(angles)], dtype=torch.float32
        )
        self._robot.send_action(action)
        time.sleep(1.0)  # wait for motion to complete

    def _open_gripper(self) -> None:
        self._set_gripper(0.0)

    def _close_gripper(self) -> None:
        self._set_gripper(80.0)   # ~80 % closed for a positive grip

    def _set_gripper(self, value: float) -> None:
        if self._sim:
            logger.debug("SIM gripper → %.1f", value)
            time.sleep(0.2)
            return
        import torch
        # Assumes the last DOF in the action vector is the gripper
        current = {**HOME_ANGLES, "gripper": value}
        self._move_to_angles(current)

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    @staticmethod
    def _default_config() -> dict:
        return {
            "robot_type": "so101",
            "port": "/dev/ttyUSB0",
            "baudrate": 1000000,
        }

    def disconnect(self) -> None:
        if self._robot is not None:
            self._robot.disconnect()
            logger.info("Disconnected from arm.")

    def __del__(self):
        try:
            self.disconnect()
        except Exception:
            pass
