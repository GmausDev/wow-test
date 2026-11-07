"""Interact mode with --no-humanize."""
import threading
from fakes import *
import fakes

fakes.SPLASH_AT[:] = [3.0, 3.2]  # after the fixed 2.5 s settle
threading.Timer(9.0, wf.stop_event.set).start()
wf.fish(args(mode="interact", no_humanize=True, timeout=2.0))
assert state["keys"] == ["1", "f", "1", "f"], state["keys"]
assert not state["clicks"]
print("interact: ok")
