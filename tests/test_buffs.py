"""Buff keys (lure, food) are pressed before the first cast and refreshed on time."""
import threading, random
from fakes import *

random.seed(3)
wf.HUMAN.update(reaction=(0.05, 0.25, 0.1), settle=(0.4, 0.6), loot_wait=(0.1, 0.3),
                miss_chance=0, misclick_chance=0, break_every=(500, 600), move_time=(0.02, 0.05),
                buff_early=(0.2, 0.5), buff_extra=(0.05, 0.1))
try:
    wf.build_parser().parse_args(["--buff", "2"])
    raise AssertionError("bad --buff accepted")
except SystemExit:
    pass
a = wf.build_parser().parse_args(["--buff", "2:0.1:0.3", "--buff", "3:10"])   # lure lasts 6 s; food 10 min
a.start_delay, a.timeout, a.max_misses = 0, 1.0, 5
assert a.buff[1].busy == 6.0                             # default apply time
a.buff[1].busy = 0.3
threading.Timer(15.0, wf.stop_event.set).start()
wf.fish(a)
keys = state["keys"]
assert keys[:3] == ["2", "3", "1"], keys[:6]            # both applied before the first cast
assert keys.count("3") == 1, keys                        # long buff not repeated
assert 2 <= keys.count("2") <= 4, keys                   # refreshed about every 5.5-5.8 s over 15 s
assert state["clicks"], "never reeled in"
print(f"buffs: ok (keys {''.join(keys)})")
