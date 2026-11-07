"""Bobber detection on simulated screenshots."""
from fakes import *

a = args()
ok = 0
for i in range(50):
    state["last_cast"] = None; before = screen()
    press("1"); state["last_cast"] -= 1; after = screen()
    f = wf.find_bobber(before, after, a)
    bx, by = state["bobber"]
    ok += bool(f and ((f[0] - bx) ** 2 + (f[1] - by) ** 2) ** 0.5 < 6)
state["bobber"] = None
assert ok == 50, f"found {ok}/50"
assert wf.find_bobber(screen(), screen(), a) is None
print("vision: ok (50/50 bobbers found within 6 px, nothing found when there's no bobber)")
