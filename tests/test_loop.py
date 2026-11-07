"""Mouse-mode fishing loop with human-like variation, against simulated audio/screen/input."""
import threading, random
from fakes import *

random.seed(7)
wf.HUMAN.update(reaction=(0.05, 0.25, 0.1), settle=(0.4, 0.6), loot_wait=(0.1, 0.3),
                miss_chance=0.15, misclick_chance=0.15, break_every=(4, 5), break_length=(0.5, 0.8),
                move_time=(0.02, 0.05))
state["no_splash_casts"] = {3}
threading.Timer(25.0, wf.stop_event.set).start()
wf.fish(args(timeout=1.0, max_misses=5))
dists = [((mx - 250 - bx) ** 2 + (my - 119 - by) ** 2) ** 0.5 for (mx, my), (bx, by) in state["clicks"]]
assert dists and all(d < 9 or d > 20 for d in dists), dists          # on the bobber, or a clear misclick
assert any(d < 9 for d in dists) and any(d > 20 for d in dists), dists
print(f"loop: ok ({len(dists)} clicks, distances {[round(d, 1) for d in dists]})")
