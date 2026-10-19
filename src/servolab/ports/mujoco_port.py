"""
mujoco_port.py - a whole simulated robot, for working without hardware.

    bus = servolab.connect("sim:so102")

gives you a bus with the motors of a robot model (here: the SO102 arm in
servolab/robots/so102/). Everything works like with the real robot: the same
registers, the same six port methods as feetech_port.py. A window shows the
robot moving.

How it works
------------
The robot itself (parts, masses, joints, gravity, the floor) is simulated by
MuJoCo, a physics engine. Each joint is driven by one simulated STS3215:

  1. its memory table (registers) - the same as in sim_port.py,
  2. a copy of what the motor's firmware does: read the goal from the
     registers, run the controller (position / velocity / PWM mode),
  3. a DC motor model that turns the controller output (PWM) into torque.
     Like a real motor it gets weaker the faster it turns, and at PWM 0 it
     brakes.

The joint torques go into MuJoCo, MuJoCo moves the robot, and the new joint
angles go back into the registers (present_position, ...).

Which motor drives which joint is written in the robot model:
    <custom> <numeric name="servo_id:shoulder_pan" data="1"/> ... </custom>

Time: like a real robot, the simulation keeps running in real time, also
while your program sleeps or you type in the console. A background thread
does that; a lock makes sure it never runs at the same moment as a bus call.

The numbers below (gains, motor data) are estimates. The simulated robot
behaves plausibly, not exactly like the real one.
"""

import math
import threading
import time
from pathlib import Path

from servolab import units
from servolab.errors import NoResponseError, ServoLabError, missing_extra
from servolab.ports.sim_port import SimMotor

ROBOTS_DIR = Path(__file__).resolve().parent.parent / "robots"

# --- STS3215 at 7.4 V (data sheet values and estimates) ---------------------
# The stall torque is taken from the robot model: ctrlrange of the <motor>.
NO_LOAD_SPEED = 4.7             # rad/s, 0.222 s per 60 degrees without load
STALL_CURRENT = 2.7             # A, current when the motor is blocked at full PWM

# --- Firmware controller (estimates, to be identified on the real motor) ----
POSITION_GAIN = 2.0             # raw PWM per step of error, per unit of p_coefficient
DAMPING_GAIN = 0.04             # raw PWM per step/s, per unit of d_coefficient
INTEGRAL_GAIN = 1.0             # raw PWM per step*s, per unit of i_coefficient
VELOCITY_GAIN = 1.0             # raw PWM per step/s of velocity error (velocity mode)
VELOCITY_INTEGRAL_GAIN = 5.0    # raw PWM per step of accumulated velocity error
MOVING_THRESHOLD = 20           # steps/s: above this speed the "moving" register is 1

STEPS_PER_RAD = units.STEPS_PER_REVOLUTION / (2 * math.pi)
MAX_SPEED_STEPS = NO_LOAD_SPEED * STEPS_PER_RAD
LONGEST_CATCH_UP = 0.1          # s, if the computer was busy longer, the simulation lags behind
BACKGROUND_PERIOD = 0.005       # s, how often the background thread moves the simulation on
FRAMES_PER_SECOND = 30          # how often the 3D view is updated


def find_robot_model(name):
    """'so102' -> .../robots/so102/scene.xml. A path to an .xml file is used as it is."""
    if name.endswith(".xml"):
        path = Path(name)
    else:
        path = ROBOTS_DIR / name / "scene.xml"
    if not path.is_file():
        known = sorted(p.name for p in ROBOTS_DIR.iterdir() if (p / "scene.xml").is_file())
        raise ServoLabError(f"No robot model '{name}'. Known robots: {', '.join(known)}")
    return path


class SimServo:
    """One simulated STS3215 that drives one joint of the robot model."""

    def __init__(self, motor_id, joint_name, model, mujoco):
        self.registers = SimMotor(motor_id)      # the memory table, see sim_port.py
        self.read_command()
        self.joint_name = joint_name

        # Where this joint lives in MuJoCo's arrays
        joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, joint_name)
        actuator = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, joint_name)
        if joint < 0 or actuator < 0:
            raise ServoLabError(f"The robot model needs a joint and a <motor> named '{joint_name}'.")
        self.qpos_index = model.jnt_qposadr[joint]
        self.qvel_index = model.jnt_dofadr[joint]
        self.actuator = actuator
        self.stall_torque = model.actuator_ctrlrange[actuator][1]   # N m

        # Controller state (inside the firmware)
        self.setpoint = None          # where the position controller wants to be now, in steps
        self.setpoint_velocity = 0.0  # steps/s, for speed / acceleration limited moves
        self.integral = 0.0           # accumulated position or velocity error
        self.last_mode = None
        self.pwm = 0.0                # controller output -1 ... 1

    def get(self, name):
        """Value of one of this servo's registers, by name."""
        return self.registers.get(name)

    def read_command(self):
        """Read the registers the firmware needs. They can only change between
        two bus calls, so this is done once per advance_time(), not every step."""
        names = ("torque_enable", "operating_mode", "goal_position", "homing_offset", "goal_velocity",
                 "acceleration", "goal_time", "torque_limit", "p_coefficient", "d_coefficient", "i_coefficient")
        self.command = {name: self.get(name) for name in names}

    def set(self, name, value):
        """Store a value in one of this servo's registers, by name."""
        self.registers.set(name, value)

    # -- the firmware --------------------------------------------------------

    def joint_torque(self, angle, velocity, dt):
        """What the motor does in one time step: registers in, torque (N m) out.

        angle in rad and velocity in rad/s come from the simulated joint.
        """
        steps = units.CENTER_STEPS + angle * STEPS_PER_RAD     # encoder position
        steps_per_s = velocity * STEPS_PER_RAD
        mode = self.command["operating_mode"]
        if mode != self.last_mode:
            self.integral = 0.0
            self.setpoint = None
            self.last_mode = mode

        if self.command["torque_enable"] == 0:
            # Motor switched off: no current, the joint turns freely
            # (only the gearbox friction of the model holds it back).
            self.pwm = 0.0
            self.setpoint = None
            self.integral = 0.0
            return 0.0

        if mode == 0:
            raw = self.position_controller(steps, steps_per_s, dt)
        elif mode == 1:
            raw = self.velocity_controller(steps_per_s, dt)
        elif mode == 2:
            # PWM mode: the PWM comes straight from the goal_time register.
            raw = units.raw_to_pwm(self.command["goal_time"]) * 1000
        else:
            raw = 0.0   # unknown mode: no output

        limit = self.command["torque_limit"]              # 0.1 %, 1000 = full power
        raw = max(-limit, min(limit, raw))
        self.pwm = raw / 1000
        return self.motor_torque(self.pwm, velocity)

    def position_controller(self, steps, steps_per_s, dt):
        """PID on the position error. Returns raw PWM (-1000 ... 1000)."""
        goal = self.command["goal_position"] + self.command["homing_offset"]   # in encoder steps
        if self.setpoint is None:
            self.setpoint = steps
            self.setpoint_velocity = 0.0
        self.move_setpoint(goal, dt)

        error = self.setpoint - steps
        error_rate = self.setpoint_velocity - steps_per_s
        self.integral += error * dt
        return (POSITION_GAIN * self.command["p_coefficient"] * error
                + DAMPING_GAIN * self.command["d_coefficient"] * error_rate
                + INTEGRAL_GAIN * self.command["i_coefficient"] * self.integral)

    def move_setpoint(self, goal, dt):
        """Move the setpoint towards the goal, limited by speed and acceleration.

        goal_velocity = 0 and acceleration = 0 mean "no limit": jump straight to the goal.
        """
        max_speed = self.command["goal_velocity"] or math.inf          # steps/s
        max_acceleration = self.command["acceleration"] * units.ACCELERATION_STEPS_PER_UNIT or math.inf
        remaining = goal - self.setpoint
        if math.isinf(max_speed) and math.isinf(max_acceleration):
            self.setpoint = goal
            self.setpoint_velocity = 0.0
            return

        # Fastest speed that still lets us brake in time before the goal
        braking_speed = math.sqrt(2 * max_acceleration * abs(remaining)) if not math.isinf(max_acceleration) else math.inf
        wanted = math.copysign(min(max_speed, braking_speed), remaining)
        change = max(-max_acceleration * dt, min(max_acceleration * dt, wanted - self.setpoint_velocity))
        self.setpoint_velocity += change
        step = self.setpoint_velocity * dt
        if abs(step) >= abs(remaining):     # arrived
            self.setpoint = goal
            self.setpoint_velocity = 0.0
        else:
            self.setpoint += step

    def velocity_controller(self, steps_per_s, dt):
        """PI on the velocity error, plus the PWM that this speed needs anyway."""
        goal = self.command["goal_velocity"]                     # steps/s, signed
        error = goal - steps_per_s
        self.integral += error * dt
        feed_forward = goal / MAX_SPEED_STEPS * 1000
        return feed_forward + VELOCITY_GAIN * error + VELOCITY_INTEGRAL_GAIN * self.integral

    def motor_torque(self, pwm, velocity):
        """DC motor: torque from PWM, minus the back-EMF of the turning motor."""
        return self.stall_torque * (pwm - velocity / NO_LOAD_SPEED)

    # -- registers that show the state --------------------------------------

    def update_present_values(self, angle, velocity):
        """Write the joint state (angle in rad, velocity in rad/s) into the read-only registers."""
        steps = units.CENTER_STEPS + angle * STEPS_PER_RAD
        present = round(steps)
        if self.get("operating_mode") == 0:     # like the real STS3215: offset only in position mode
            present -= self.get("homing_offset")
        self.set("present_position", present % units.STEPS_PER_REVOLUTION)
        steps_per_s = round(velocity * STEPS_PER_RAD)
        self.set("present_velocity", steps_per_s)
        self.set("present_load", round(max(-1.0, min(1.0, self.pwm)) * 1000))
        if self.command["torque_enable"]:
            amps = abs(self.pwm - velocity / NO_LOAD_SPEED) * STALL_CURRENT
        else:
            amps = 0.0
        self.set("present_current", min(round(amps / units.CURRENT_AMPS_PER_STEP), 500))   # 500 = 3.25 A, the most it measures
        self.set("moving", 1 if abs(steps_per_s) > MOVING_THRESHOLD else 0)


class MujocoPort:
    """A simulated robot. Same methods as FeetechPort and SimPort."""

    def __init__(self, robot="so102", show=True):
        try:
            import mujoco  # only needed here: pip install "servolab[sim]"
        except ImportError:
            raise missing_extra("mujoco", "sim") from None

        self.mujoco = mujoco
        self.model_path = find_robot_model(robot)
        self.name = f"sim:{robot}"
        self.model = mujoco.MjModel.from_xml_path(str(self.model_path))
        self.data = mujoco.MjData(self.model)
        mujoco.mj_forward(self.model, self.data)

        # Servo IDs are stored in the model: <numeric name="servo_id:<joint>" data="<id>"/>
        self.motors = {}
        for index in range(self.model.nnumeric):
            name = mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_NUMERIC, index)
            if not name.startswith("servo_id:"):
                continue
            motor_id = int(self.model.numeric_data[self.model.numeric_adr[index]])
            servo = SimServo(motor_id, name.split(":", 1)[1], self.model, mujoco)
            if motor_id in self.motors:
                raise ServoLabError(f"{self.model_path.name}: servo ID {motor_id} is given to two joints, "
                                    f"'{self.motors[motor_id].joint_name}' and '{servo.joint_name}'.")
            self.motors[motor_id] = servo
        if not self.motors:
            raise ServoLabError(f"{self.model_path.name} has no servo IDs (<numeric name=\"servo_id:...\">).")

        for servo in self.motors.values():
            self.update_registers(servo)
            # After power-on the real motor wants to stay where it is
            servo.set("goal_position", servo.get("present_position"))

        self.sim_time = 0.0
        self.unsimulated = 0.0        # s of real time that still has to be simulated
        self.view = RerunView(self.model, self.data, robot, mujoco) if show else None
        if self.view:
            self.view.update(self.sim_time)
        self.last_update = time.perf_counter()   # start the clock only now (the view takes a moment)

        self.lock = threading.Lock()
        self.running = True
        self.thread = threading.Thread(target=self.run_in_background, daemon=True)
        self.thread.start()

    def close(self):
        """Stop the background thread (the simulation stops)."""
        self.running = False
        self.thread.join()

    def run_in_background(self):
        """Keep the simulation going, even when nobody talks to the bus."""
        while self.running:
            with self.lock:
                self.advance_time()
            time.sleep(BACKGROUND_PERIOD)

    # -- the six port methods (what they do: see feetech_port.py) -----------

    def ping(self, motor_id, timeout_ms=None):
        with self.lock:
            self.advance_time()
            if motor_id in self.motors:
                return self.motors[motor_id].get("model_number")
            return None

    def read(self, motor_id, address, size):
        with self.lock:
            self.advance_time()
            servo = self.get_servo(motor_id)
            return servo.registers.memory[address:address + size]

    def write(self, motor_id, address, data):
        with self.lock:
            self.advance_time()
            servo = self.get_servo(motor_id)
            servo.registers.memory[address:address + len(data)] = data
            servo.read_command()             # the firmware sees the new value right away
            self.update_registers(servo)     # e.g. a new homing_offset changes present_position

            # If the ID register was changed, the motor now answers to its new ID.
            new_id = servo.get("id")
            if new_id != motor_id:
                del self.motors[motor_id]
                self.motors[new_id] = servo

    def sync_read(self, motor_ids, address, size):
        answers = {}
        for motor_id in motor_ids:
            answers[motor_id] = self.read(motor_id, address, size)
        return answers

    def sync_write(self, motor_ids, address, data_per_id):
        for motor_id in motor_ids:
            self.write(motor_id, address, data_per_id[motor_id])

    def factory_reset(self, motor_id):
        with self.lock:
            self.advance_time()
            servo = self.get_servo(motor_id)
            servo.registers.factory_reset()
            servo.read_command()
            self.update_registers(servo)

    def id_used_twice(self, motor_id):
        return False      # checked when the model is loaded: every joint has its own ID

    # -- extras of the simulation (use them as bus.sim.tcp() etc.) -----------

    def tcp(self):
        """Pose of the tool centre point (between the jaws) as a 4x4 matrix.

        The true pose in the simulation, in the base frame (x forward, y left,
        z up, in m). Use it to check your own forward kinematics.
        """
        return self.pose("tcp")

    def pose(self, name):
        """Pose of a site or body of the robot model as a 4x4 matrix (base frame, m)."""
        import numpy as np

        mujoco = self.mujoco
        with self.lock:
            site = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_SITE, name)
            body = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, name)
            pose = np.eye(4)
            if site >= 0:
                pose[:3, :3] = self.data.site_xmat[site].reshape(3, 3)
                pose[:3, 3] = self.data.site_xpos[site]
            elif body >= 0:
                pose[:3, :3] = self.data.xmat[body].reshape(3, 3)
                pose[:3, 3] = self.data.xpos[body]
            else:
                raise ServoLabError(f"The robot model has no site or body named '{name}'.")
        return pose

    def mark(self, name, position, color=(230, 120, 20)):
        """Show a point in the 3D view, e.g. where your kinematics thinks the TCP is.

        position: [x, y, z] in m (base frame), or a 4x4 pose (its position is used).
        Marking the same name again moves the point.
        """
        if self.view:
            self.view.mark(name, position, color)

    def mark_frame(self, name, pose, size=0.05):
        """Show a coordinate frame (x red, y green, z blue) for a 4x4 pose in the 3D view."""
        if self.view:
            self.view.mark_frame(name, pose, size)

    # -- helpers -----------------------------------------------------------

    def get_servo(self, motor_id):
        """The SimServo with this ID. Raises NoResponseError like a real bus if there is none."""
        if motor_id not in self.motors:
            raise NoResponseError(motor_id)
        return self.motors[motor_id]

    def update_registers(self, servo):
        """Copy the joint state from MuJoCo into the servo's registers."""
        angle = self.data.qpos[servo.qpos_index]
        velocity = self.data.qvel[servo.qvel_index]
        servo.update_present_values(angle, velocity)

    def advance_time(self):
        """Simulate the robot up to the current time. Call only while holding self.lock."""
        now = time.perf_counter()
        self.unsimulated += min(now - self.last_update, LONGEST_CATCH_UP)
        self.last_update = now
        dt = self.model.opt.timestep
        steps = int(self.unsimulated / dt)
        if steps == 0:
            return
        self.unsimulated -= steps * dt

        for servo in self.motors.values():
            servo.read_command()
        for _ in range(steps):
            # 1. every motor's firmware: registers + joint state -> torque
            for servo in self.motors.values():
                angle = self.data.qpos[servo.qpos_index]
                velocity = self.data.qvel[servo.qvel_index]
                self.data.ctrl[servo.actuator] = servo.joint_torque(angle, velocity, dt)
            # 2. MuJoCo moves the robot
            self.mujoco.mj_step(self.model, self.data)
            self.sim_time += dt
            if self.view:
                self.view.update(self.sim_time)
        # 3. new joint state -> registers
        for servo in self.motors.values():
            self.update_registers(servo)


class RerunView:
    """Shows the simulated robot in the Rerun viewer (the same window as LivePlot)."""

    def __init__(self, model, data, robot, mujoco):
        import numpy as np
        import rerun as rr

        from servolab.plotting import find_rerun_viewer

        self.rr = rr
        self.model = model
        self.data = data
        self.last_frame = -math.inf
        self.recording = rr.RecordingStream(f"servolab {robot}")
        rr.spawn(executable_path=find_rerun_viewer(), recording=self.recording)
        self.recording.log("robot", rr.ViewCoordinates.RIGHT_HAND_Z_UP, static=True)

        # Every visible mesh once, attached to its body. Later only the
        # positions of the bodies are sent.
        self.bodies = []
        for geom in range(model.ngeom):
            if model.geom_type[geom] != mujoco.mjtGeom.mjGEOM_MESH or model.geom_group[geom] != 2:
                continue
            body = model.geom_bodyid[geom]
            body_name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body)
            mesh = model.geom_dataid[geom]
            first, count = model.mesh_vertadr[mesh], model.mesh_vertnum[mesh]
            vertices = model.mesh_vert[first:first + count]
            first_face, face_count = model.mesh_faceadr[mesh], model.mesh_facenum[mesh]
            faces = model.mesh_face[first_face:first_face + face_count]
            rgba = model.mat_rgba[model.geom_matid[geom]] if model.geom_matid[geom] >= 0 else model.geom_rgba[geom]
            rotation = np.zeros(9)
            mujoco.mju_quat2Mat(rotation, model.geom_quat[geom])
            path = f"robot/{body_name}/geom{geom}"
            self.recording.log(path, rr.Transform3D(translation=model.geom_pos[geom],
                                                    mat3x3=rotation.reshape(3, 3)), static=True)
            self.recording.log(path, rr.Mesh3D(vertex_positions=vertices, triangle_indices=faces,
                                               vertex_normals=vertex_normals(vertices, faces),
                                               albedo_factor=rgba), static=True)
            if body not in [b for b, _ in self.bodies]:
                self.bodies.append((body, f"robot/{body_name}"))

    def mark(self, name, position, color):
        """Draw (or move) a point called `name`; see MujocoPort.mark()."""
        import numpy as np

        position = np.asarray(position, dtype=float)
        if position.shape == (4, 4):
            position = position[:3, 3]
        self.recording.log(f"marks/{name}", self.rr.Points3D([position], radii=0.006, colors=[color]), static=True)

    def mark_frame(self, name, pose, size):
        """Draw (or move) a coordinate frame called `name`; see MujocoPort.mark_frame()."""
        import numpy as np

        pose = np.asarray(pose, dtype=float)
        origin, rotation = pose[:3, 3], pose[:3, :3]
        self.recording.log(f"marks/{name}", self.rr.Arrows3D(
            origins=[origin] * 3, vectors=(rotation * size).T,
            colors=[(220, 50, 50), (50, 170, 50), (50, 90, 220)]), static=True)

    def update(self, sim_time):
        """Send the body positions, at most FRAMES_PER_SECOND times per simulated second."""
        if sim_time - self.last_frame < 1 / FRAMES_PER_SECOND:
            return
        self.last_frame = sim_time
        self.recording.set_time("sim_time", duration=sim_time)
        for body, path in self.bodies:
            self.recording.log(path, self.rr.Transform3D(translation=self.data.xpos[body],
                                                         mat3x3=self.data.xmat[body].reshape(3, 3)))


def vertex_normals(vertices, faces):
    """Smooth normals for nicer shading: average of the neighbouring face normals."""
    import numpy as np

    corners = vertices[faces]
    face_normals = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    normals = np.zeros_like(vertices)
    for k in range(3):
        np.add.at(normals, faces[:, k], face_normals)
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    return normals / np.maximum(lengths, 1e-12)
