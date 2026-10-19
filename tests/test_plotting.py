import csv

import matplotlib
import pytest

import servolab
from servolab import plotting

matplotlib.use("Agg")   # draw without opening windows


def test_recorder_collects_values():
    rec = servolab.Recorder()
    for i in range(5):
        rec.add(time=i * 0.1, position=i, goal=2)
    assert len(rec) == 5
    assert list(rec["position"]) == [0, 1, 2, 3, 4]
    assert rec["time"][-1] == pytest.approx(0.4)


def test_recorder_unknown_name_gives_helpful_error():
    rec = servolab.Recorder()
    rec.add(time=0.0, position=1.0)
    with pytest.raises(servolab.ServoLabError, match="Recorded"):
        rec["velocity"]


def test_recorder_plot_and_save(tmp_path):
    rec = servolab.Recorder()
    for i in range(3):
        rec.add(time=i * 0.1, position=i * 0.5)
    rec.plot()
    rec.plot("position")
    path = tmp_path / "run.csv"
    rec.save(path)
    rows = list(csv.reader(open(path)))
    assert rows[0] == ["time", "position"]
    assert len(rows) == 4


def test_recorder_plot_mismatched_names():
    rec = servolab.Recorder()
    rec.add(time=0.0, position=1.0, goal=1.0)
    rec.add(time=0.1, position=1.1)            # goal forgotten
    with pytest.raises(servolab.ServoLabError, match="same names"):
        rec.plot()


def test_liveplot_records_and_sends(monkeypatch):
    import rerun as rr

    import rerun.sinks

    # Only the very last step - starting the viewer program - is replaced, so that
    # the real rr.spawn(...) call (and its arguments) is still checked.
    started = []
    monkeypatch.setattr(rerun.sinks, "_spawn_viewer", lambda **kwargs: started.append(kwargs))
    sent = []
    monkeypatch.setattr(rr.RecordingStream, "log", lambda self, name, value: sent.append(name))
    layouts = []
    monkeypatch.setattr(rr.RecordingStream, "send_blueprint", lambda self, blueprint: layouts.append(blueprint))
    live = servolab.LivePlot("servolab_test")
    live.add(time=0.0, position=0.1, goal=0.5)
    live.add(time=0.01, position=0.2, goal=0.5)
    assert len(live) == 2
    assert sent == ["position", "goal", "position", "goal"]
    # a fresh layout is sent, so old plots from earlier runs do not show up
    assert len(layouts) == 1
    assert started and "rerun" in started[0]["executable_path"]


def test_rerun_viewer_is_found_next_to_python():
    path = plotting.find_rerun_viewer()
    assert path is not None and "rerun" in path
