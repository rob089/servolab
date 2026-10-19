"""
plotting.py - record values in your loop and look at them.

    rec = servolab.Recorder()        # records; you plot after the loop
    live = servolab.LivePlot()       # records AND shows the values live

In your loop, both work the same way:

    rec.add(time=fb.time, position=fb.position[0], goal=goal)

After the loop:

    rec.plot()                       # one diagram with all values over time
    rec.save("run1.csv")             # save for later (Excel, numpy, pandas ...)
    rec["position"]                  # the recorded values as a numpy array

Why not draw with matplotlib inside the loop? Drawing takes 20-50 ms. Your
loop would slow down from e.g. 200 Hz to 20 Hz, and your controller would
behave differently just because you are looking at it.
"""

import csv
import os
import sys
from pathlib import Path

import numpy as np

from servolab.errors import ServoLabError, missing_extra


class Recorder:
    """Collects values in a loop. Look at them after the loop."""

    def __init__(self):
        # name -> list of values, e.g. {"time": [0.0, 0.01], "position": [0.5, 0.52]}
        self.values = {}

    def add(self, time, **values):
        """Store the values of one moment.

        Example:  rec.add(time=fb.time, position=0.5, goal=1.0)

        You can choose the names yourself ("**values" means: any names you
        like). Use the same names every time.
        """
        self.values.setdefault("time", []).append(time)
        for name, value in values.items():
            self.values.setdefault(name, []).append(value)

    def __getitem__(self, name):
        """rec["position"] gives all recorded positions as a numpy array."""
        if name not in self.values:
            raise ServoLabError(f"Nothing called '{name}' was recorded. Recorded: {list(self.values)}")
        return np.array(self.values[name])

    def __len__(self):
        """len(rec) = how many moments were recorded."""
        return len(self.values.get("time", []))

    def plot(self, *names):
        """Draw the recorded values over time, all in one diagram.

        rec.plot()                    -> everything
        rec.plot("position", "goal")  -> only these
        """
        if len(self) == 0:
            raise ServoLabError("Nothing recorded yet. Call rec.add(...) in your loop first.")
        if not names:
            names = [name for name in self.values if name != "time"]
        try:
            import matplotlib.pyplot as plt    # only needed here: servolab[plot]
        except ImportError:
            raise missing_extra("matplotlib", "plot") from None

        plt.figure()
        for name in names:
            values = self[name]
            if len(values) != len(self):
                raise ServoLabError(f"'{name}' was recorded {len(values)} times, time {len(self)} times. "
                                    "Use the same names in every rec.add().")
            plt.plot(self["time"], values, label=name)
        plt.xlabel("time [s]")
        plt.legend()
        plt.grid(True)
        plt.show()

    def save(self, filename):
        """Save everything as a CSV file: one column per name, one row per moment."""
        names = list(self.values)
        with open(filename, "w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(names)
            for row in zip(*(self.values[name] for name in names)):
                writer.writerow(row)


class LivePlot(Recorder):
    """Like Recorder, but also shows the values live in a separate window.

    "LivePlot(Recorder)" means: a LivePlot can do everything a Recorder can
    (add, plot, save ...), plus showing the values live.

    The window is the Rerun viewer, a separate program. Sending a value to it
    takes only microseconds, so your control loop does not get slower.
    If you close the window, your loop keeps running and recording.
    """

    def __init__(self, name="servolab"):
        super().__init__()                     # set up the Recorder part
        # Rerun prints a lot of technical messages; we only want the plot.
        os.environ.setdefault("RUST_LOG", "off")
        try:
            import rerun as rr                 # the live plotting library: servolab[plot]
        except ImportError:
            raise missing_extra("rerun-sdk", "plot") from None
        self.rr = rr
        # Every LivePlot gets its own connection to the viewer. Then a new
        # LivePlot still works after you closed the viewer window of an old one.
        self.recording = rr.RecordingStream(name)
        rr.spawn(executable_path=find_rerun_viewer(), recording=self.recording)   # open the viewer window
        # The viewer remembers its layout from the last run, including plots
        # for names you do not use anymore. So we tell it the layout ourselves:
        # one diagram with all values, like rec.plot().
        import rerun.blueprint as rrb
        self.recording.send_blueprint(rrb.Blueprint(rrb.TimeSeriesView(origin="/")))

    def add(self, time, **values):
        """Store the values of one moment, like Recorder.add(), and show them in the window.

        Example:  live.add(time=fb.time, position=fb.position[0], goal=goal)
        """
        super().add(time, **values)                          # record, like Recorder
        self.recording.set_time("time", duration=time)       # "these values belong to this moment"
        for name, value in values.items():
            self.recording.log(name, self.rr.Scalars(value))  # send one value to the viewer


def find_rerun_viewer():
    """Path of the Rerun viewer that was installed together with servolab.

    Rerun normally searches for its viewer in the PATH. Positron's console
    does not always include the project's .venv folder there, so we point
    Rerun to the viewer next to the Python that runs this program.
    """
    scripts = Path(sys.executable).parent
    for candidate in (scripts / "rerun", scripts / "rerun.exe"):
        if candidate.exists():
            return str(candidate)
    return None   # not found next to Python: let Rerun search the PATH
