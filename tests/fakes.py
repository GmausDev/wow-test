"""Fake Windows-only modules so wow_fisher can run on Linux against a simulated game."""
import sys, types, time, random
import numpy as np

W, H = 700, 449                       # search region size
state = {"last_cast": None, "cast_n": 0, "focused": True, "bobber": None,
         "mouse": (900, 500), "clicks": [], "keys": [], "no_splash_casts": set()}

def water():
    img = np.zeros((H, W, 4), np.uint8)
    img[..., 0] = np.random.randint(110, 170, (H, W))   # B
    img[..., 1] = np.random.randint(70, 110, (H, W))    # G
    img[..., 2] = np.random.randint(20, 60, (H, W))     # R
    img[20:40, 20:60, :3] = (30, 30, 200)               # static red UI element (BGR)
    return img

def screen():
    img = water()
    lc = state["last_cast"]
    if lc and time.monotonic() - lc > 0.2 and state["bobber"]:
        x, y = state["bobber"]
        img[y - 4:y + 4, x - 3:x + 3, :3] = (40, 35, 210)   # red feather
        img[y + 4:y + 7, x - 4:x + 4, :3] = (230, 230, 230) # white body
    return img

# pydirectinput
pdi = types.ModuleType("pydirectinput")
class FailSafeException(Exception): pass
pdi.FailSafeException = FailSafeException
pdi.FAILSAFE = True; pdi.PAUSE = 0
def press(k):
    state["keys"].append(k)
    if k == "1":
        state["last_cast"] = time.monotonic(); state["cast_n"] += 1
        state["bobber"] = (random.randint(60, W - 60), random.randint(80, H - 60))
def moveTo(x, y, _pause=True): state["mouse"] = (x, y)
def rightClick(): state["clicks"].append((state["mouse"], state["bobber"]))
pdi.press, pdi.moveTo, pdi.rightClick = press, moveTo, rightClick
pdi.position = lambda: state["mouse"]
sys.modules["pydirectinput"] = pdi

# soundcard: splash SPLASH_AT seconds after each cast unless that cast is listed as silent
SPLASH_AT = [0.8, 1.0]
class Rec:
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def record(self, numframes):
        time.sleep(numframes / 48000)
        lc = state["last_cast"]
        loud = (lc and state["cast_n"] not in state["no_splash_casts"]
                and SPLASH_AT[0] <= time.monotonic() - lc <= SPLASH_AT[1])
        amp = 0.3 if loud else 0.01
        return np.random.uniform(-amp, amp, (numframes, 2)).astype("float32")
class Mic:
    def recorder(self, samplerate): return Rec()
sc = types.ModuleType("soundcard")
sc.default_speaker = lambda: types.SimpleNamespace(name="Speakers")
sc.get_microphone = lambda id, include_loopback: Mic()
sys.modules["soundcard"] = sc

# mss
mssmod = types.ModuleType("mss"); tools = types.ModuleType("mss.tools")
class Sct:
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def grab(self, region):
        assert region["width"] == W and region["height"] == H, region
        return screen()
mssmod.mss = lambda: Sct()
saved = {}
def to_png(data, size, output=None): saved["png"] = (len(data), size, output)
tools.to_png = to_png; mssmod.tools = tools
sys.modules["mss"] = mssmod; sys.modules["mss.tools"] = tools

# pynput
pynput = types.ModuleType("pynput"); kb = types.ModuleType("pynput.keyboard")
kb.Key = types.SimpleNamespace(f12="F12")
kb.KeyCode = types.SimpleNamespace(from_char=lambda c: c)
class Listener:
    def __init__(self, on_press): pass
    def start(self): pass
kb.Listener = Listener; pynput.keyboard = kb
sys.modules["pynput"] = pynput; sys.modules["pynput.keyboard"] = kb

import os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import wow_fisher as wf
wf.wow_focused = lambda: state["focused"]
# WoW window at (100, 50), 1000x692 -> search area 0.15..0.85 x 0.10..0.75 = 700x450 region
wf.wow_client_rect = lambda: (100, 50, 1000, 692)

def args(**kw):
    a = wf.build_parser().parse_args([])
    a.start_delay = 0
    for k, v in kw.items(): setattr(a, k, v)
    return a
