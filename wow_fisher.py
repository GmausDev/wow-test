"""
wow_fisher.py - sound-triggered auto-fisher for World of Warcraft Classic (Windows).

How it works (default "mouse" mode)
  1. Takes a screenshot of the water, then presses your Fishing key to cast.
  2. Once the bobber lands, takes a second screenshot and finds the bobber by
     the new red feather that appeared.
  3. Listens to your PC's audio output for the splash of a bite.
  4. Right-clicks the bobber (Auto Loot takes the catch) and casts again.

It's deliberately imperfect: reaction times vary, the mouse glides rather than
jumps, clicks land a few pixels off, it now and then lets a fish go or clicks
next to the bobber, and it takes breaks. See HUMAN below, or --no-humanize.

"interact" mode (--mode interact) skips the screen reading and presses the
Interact Key instead. In Classic the Interact Key only reaches a short
distance, so that only works when your bobbers land close. Mouse mode works
at any cast distance.

It only reads the screen and system audio, and sends ordinary key presses and
clicks. It doesn't touch the game's memory or files, and it only acts while
WoW is the focused window.

Stop it any time with:  F12  |  mouse slammed into the top-left screen corner  |  Ctrl+C in the console

------------------------------------------------------------------------------
One-time in-game setup
  * Put Fishing on an action bar slot with a keybind (default here: 1).
  * Turn on Auto Loot in the options, or type:  /console autoLootDefault 1
  * Sound: Sound Effects ON; Music, Ambience and Dialog OFF.
  * Mute everything else on your PC (Discord, music, browser tabs). The script
    hears every sound your speakers play.
  * Mouse mode: run WoW on your MAIN monitor (fullscreen or windowed). Zoom the
    camera all the way into first-person and look out over open water, so the
    water fills the middle of the screen and your character isn't in view.
    Pick a quiet spot without other players running through.

Step 1 - calibrate the sound
  python wow_fisher.py --calibrate
  Fish by hand a few times. Note the idle level and the peak when the bobber
  splashes, then pick a threshold roughly halfway between.

Step 2 - check it can see the bobber
  python wow_fisher.py --test-bobber
  Casts once, looks for the bobber, puts the mouse on it and saves
  bobber_debug.png (magenta = new red pixels, green cross = where it would
  click). Reel that one in yourself.

Step 3 - fish
  python wow_fisher.py --threshold 0.08
  You get 5 seconds to click into WoW.
------------------------------------------------------------------------------
"""

import argparse
import ctypes
import math
import random
import sys
import threading
import time
from collections import deque

import mss
import mss.tools
import numpy as np
import pydirectinput
import soundcard as sc
from pynput import keyboard as pkb

SAMPLE_RATE = 48000
CHUNK_SEC = 0.05  # each audio read covers 50 ms
CHUNK_FRAMES = int(SAMPLE_RATE * CHUNK_SEC)
BLOCK = 8         # pixel block size used when looking for the bobber

pydirectinput.FAILSAFE = True  # mouse to top-left corner aborts
pydirectinput.PAUSE = 0.05

stop_event = threading.Event()

# --------------------------------------------------------------------------- human-like variation
# The script is deliberately imperfect: timings vary, the mouse glides instead of
# teleporting, clicks land a few pixels off, it sometimes "doesn't notice" a bite,
# now and then clicks next to the bobber, and it takes breaks.
# Tweak these to taste, or turn it all off with --no-humanize.
HUMAN = {
    "reaction": (0.35, 1.4, 0.6),    # seconds from splash to click: triangular(min, max, most likely)
    "settle": (2.3, 3.2),            # seconds after casting before looking for the bobber
    "loot_wait": (1.2, 3.2),         # seconds between reeling in and the next cast
    "jitter_px": 3,                  # typical click offset from the bobber centre (capped at 2x), in pixels
    "miss_chance": 0.04,             # chance to ignore a bite and let the fish get away
    "misclick_chance": 0.02,         # chance to click clearly next to the bobber
    "misclick_px": (22, 45),         # how far off a misclick lands, in pixels
    "move_time": (0.12, 0.35),       # seconds the mouse takes to glide to the bobber
    "break_every": (35, 90),         # casts between breaks (random in this range)
    "break_length": (20, 150),       # break length in seconds
}


class Human:
    """Adds the variation above. With enabled=False everything is fixed and exact."""

    def __init__(self, enabled, args):
        self.enabled = enabled
        self.args = args
        self.casts_until_break = self._next_break()

    def _next_break(self):
        return random.randint(*HUMAN["break_every"]) if self.enabled else -1

    def reaction(self):
        return random.triangular(*HUMAN["reaction"]) if self.enabled else self.args.reaction

    def settle(self):
        return random.uniform(*HUMAN["settle"]) if self.enabled else self.args.settle

    def loot_wait(self):
        return random.uniform(*HUMAN["loot_wait"]) if self.enabled else self.args.loot_wait

    def ignore_bite(self):
        return self.enabled and random.random() < HUMAN["miss_chance"]

    def click_offset(self):
        """(dx, dy, is_misclick)"""
        if not self.enabled:
            return 0, 0, False
        if random.random() < HUMAN["misclick_chance"]:
            angle = random.uniform(0, 2 * math.pi)
            dist = random.uniform(*HUMAN["misclick_px"])
            return int(dist * math.cos(angle)), int(dist * math.sin(angle)), True
        j = HUMAN["jitter_px"]
        clamp = lambda v: int(max(-2 * j, min(2 * j, v)))  # stay on the bobber
        return clamp(random.gauss(0, j)), clamp(random.gauss(0, j)), False

    def break_due(self):
        """Call once per cast. Returns a break length in seconds when one is due, else 0."""
        if not self.enabled:
            return 0
        self.casts_until_break -= 1
        if self.casts_until_break > 0:
            return 0
        self.casts_until_break = self._next_break()
        return random.uniform(*HUMAN["break_length"])


# --------------------------------------------------------------------------- windows / input

def make_dpi_aware():
    """So screenshot pixels and mouse coordinates line up on scaled displays."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def start_stop_key_listener(key_name):
    """Set stop_event when the stop key is pressed anywhere (global hook)."""
    target = getattr(pkb.Key, key_name.lower(), None) or pkb.KeyCode.from_char(key_name.lower())

    def on_press(key):
        if key == target:
            stop_event.set()
            return False  # ends the listener

    listener = pkb.Listener(on_press=on_press)
    listener.start()
    return listener


def wow_focused():
    """True if the foreground window is the WoW client."""
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value.strip().startswith("World of Warcraft")


def wow_client_rect():
    """(left, top, width, height) of the focused WoW window's game area, in screen pixels."""
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    origin = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    return origin.x, origin.y, rect.right, rect.bottom


def press(key):
    """Press a key, but only if WoW has focus. Returns True if pressed."""
    if not wow_focused():
        return False
    pydirectinput.press(key)
    return True


def glide_to(x, y, human):
    """Move the mouse along a slightly curved, eased path instead of jumping."""
    if not human.enabled:
        pydirectinput.moveTo(x, y)
        return
    sx, sy = pydirectinput.position()
    dx, dy = x - sx, y - sy
    bend = random.uniform(-0.25, 0.25)
    cx, cy = sx + dx / 2 - dy * bend, sy + dy / 2 + dx * bend  # control point off to one side
    steps = random.randint(8, 16)
    pause = random.uniform(*HUMAN["move_time"]) / steps
    for i in range(1, steps + 1):
        t = i / steps
        t = t * t * (3 - 2 * t)  # ease in and out
        px = (1 - t) ** 2 * sx + 2 * (1 - t) * t * cx + t ** 2 * x
        py = (1 - t) ** 2 * sy + 2 * (1 - t) * t * cy + t ** 2 * y
        pydirectinput.moveTo(int(px), int(py), _pause=False)
        time.sleep(pause)


def reel_in(args, target, human):
    """Right-click the bobber (mouse mode) or press Interact. Only if WoW has focus.
    Returns None if WoW wasn't focused, otherwise True for a normal click, False for a misclick."""
    if not wow_focused():
        return None
    if target is None:
        pydirectinput.press(args.interact_key)
        return True
    ox, oy, misclick = human.click_offset()
    glide_to(target[0] + ox, target[1] + oy, human)
    time.sleep(random.uniform(0.05, 0.15) if human.enabled else 0.1)
    pydirectinput.rightClick()
    return not misclick


def status(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def countdown(seconds):
    for i in range(seconds, 0, -1):
        print(f"Click into WoW... starting in {i} ", end="\r", flush=True)
        time.sleep(1)
    print()


# --------------------------------------------------------------------------- audio

def open_loopback():
    """Recorder that captures whatever the default speakers are playing."""
    speaker = sc.default_speaker()
    mic = sc.get_microphone(id=str(speaker.name), include_loopback=True)
    return mic.recorder(samplerate=SAMPLE_RATE)


def levels(rec):
    """Endless stream of RMS loudness values, one per 50 ms chunk."""
    while True:
        data = rec.record(numframes=CHUNK_FRAMES)
        yield float(np.sqrt(np.mean(np.square(data)))) if data.size else 0.0


def wait(rec, seconds):
    """Wait by reading (and discarding) audio, so old sound never piles up in
    the buffer and gets mistaken for a fresh splash later."""
    end = time.monotonic() + seconds
    for _ in levels(rec):
        if stop_event.is_set() or time.monotonic() >= end:
            return


def listen_for_bite(rec, args):
    """True if the audio level crosses the threshold before the timeout."""
    until = time.monotonic() + args.timeout
    for rms in levels(rec):
        if stop_event.is_set() or time.monotonic() >= until:
            return False
        if rms >= args.threshold:
            return True


# --------------------------------------------------------------------------- vision

def search_region(args):
    """The part of the WoW window to look for the bobber in, as an mss region."""
    left, top, width, height = wow_client_rect()
    x0, y0, x1, y1 = args.search_area
    return {"left": left + int(width * x0), "top": top + int(height * y0),
            "width": max(int(width * (x1 - x0)), BLOCK), "height": max(int(height * (y1 - y0)), BLOCK)}


def grab(sct, region):
    """Screenshot of the region as an (h, w, 3) BGR array."""
    return np.array(sct.grab(region))[..., :3]


def red_mask(img, args):
    b, g, r = (img[..., i].astype(np.int16) for i in range(3))
    return (r >= args.red_min) & (r - np.maximum(g, b) >= args.red_margin)


def dilate(mask, radius):
    out = mask.copy()
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            out |= np.roll(np.roll(mask, dy, axis=0), dx, axis=1)
    return out


def new_red(before, after, args):
    """Red pixels in `after` that weren't (near) red in `before` - i.e. the new bobber,
    not red things that were already on screen like UI or nameplates."""
    return red_mask(after, args) & ~dilate(red_mask(before, args), 3)


def find_bobber(before, after, args):
    """(x, y, strength) of the bobber inside the region, or None if not found."""
    new = new_red(before, after, args)
    h, w = new.shape
    hh, ww = h - h % BLOCK, w - w % BLOCK
    if hh == 0 or ww == 0:
        return None
    counts = new[:hh, :ww].reshape(hh // BLOCK, BLOCK, ww // BLOCK, BLOCK).sum(axis=(1, 3))
    padded = np.pad(counts, 1)
    gh, gw = counts.shape
    score = sum(padded[dy:dy + gh, dx:dx + gw] for dy in range(3) for dx in range(3))
    by, bx = np.unravel_index(np.argmax(score), score.shape)
    if score[by, bx] < args.min_pixels:
        return None
    y0, x0 = max(by - 1, 0) * BLOCK, max(bx - 1, 0) * BLOCK
    y1, x1 = (by + 2) * BLOCK, (bx + 2) * BLOCK
    ys, xs = np.nonzero(new[y0:y1, x0:x1])
    return int(x0 + xs.mean()), int(y0 + ys.mean()), int(score[by, bx])


def save_debug(before, after, args, found, path):
    img = after[..., ::-1].copy()  # BGR -> RGB
    img[new_red(before, after, args)] = (255, 0, 255)
    if found:
        x, y, _ = found
        img[max(y - 20, 0):y + 21, x] = (0, 255, 0)
        img[y, max(x - 20, 0):x + 21] = (0, 255, 0)
    mss.tools.to_png(np.ascontiguousarray(img).tobytes(), (img.shape[1], img.shape[0]), output=path)


# --------------------------------------------------------------------------- modes

def calibrate(args):
    print("Calibration: fish by hand in WoW and watch the numbers.")
    print("Note the level while idle, and the peak when the bobber splashes.")
    print(f"Press {args.stop_key.upper()} (or Ctrl+C) to finish.\n")
    recent = deque(maxlen=int(3 / CHUNK_SEC))  # last 3 seconds
    overall_max = 0.0
    try:
        with open_loopback() as rec:
            for rms in levels(rec):
                if stop_event.is_set():
                    break
                recent.append(rms)
                overall_max = max(overall_max, rms)
                bar = "#" * int(min(rms / 0.25, 1.0) * 40)
                print(f"\rlevel {rms:6.3f} | 3s peak {max(recent):6.3f} | max {overall_max:6.3f} |{bar:<40}|",
                      end="", flush=True)
    except KeyboardInterrupt:
        pass
    print(f"\n\nHighest level seen: {overall_max:.3f}")
    print("Use a --threshold a bit below your splash peaks and well above the idle level.")


def test_bobber(args):
    print("Bobber test: casts once, looks for the bobber and puts the mouse on it.")
    countdown(args.start_delay)
    if not wow_focused():
        sys.exit("WoW wasn't the focused window. Run it again and click into WoW during the countdown.")
    with mss.mss() as sct:
        region = search_region(args)
        before = grab(sct, region)
        press(args.cast_key)
        time.sleep(args.settle)
        after = grab(sct, region)
    found = find_bobber(before, after, args)
    save_debug(before, after, args, found, "bobber_debug.png")
    if found:
        x, y = region["left"] + found[0], region["top"] + found[1]
        if wow_focused():
            pydirectinput.moveTo(x, y)
        print(f"Found it at screen ({x}, {y}), strength {found[2]}. The mouse should be on the bobber now.")
    else:
        print("Couldn't find the bobber. Open bobber_debug.png: magenta shows new red pixels.")
        print("  No magenta on the feather -> try --red-min 70 --red-margin 35 (dark zones / night).")
        print("  Magenta on it but too little -> try --min-pixels 6.")
        print("  Bobber outside the picture -> widen --search-area (default 0.15,0.10,0.85,0.75).")
    print("Saved bobber_debug.png. Reel this cast in yourself.")


def fish(args):
    human = Human(not args.no_humanize, args)
    casts = catches = no_bite = not_found = let_go = misclicks = breaks = consecutive_misses = 0
    started = time.monotonic()
    deadline = started + args.hours * 3600 if args.hours else None

    how = "right-clicking the bobber" if args.mode == "mouse" else f"pressing interact key '{args.interact_key}'"
    print(f"Fishing with cast key '{args.cast_key}', reeling in by {how}, threshold {args.threshold}.")
    print(f"Human-like variation: {'on' if human.enabled else 'off'}.")
    print(f"Stop: {args.stop_key.upper()}, mouse to top-left corner, or Ctrl+C.")
    countdown(args.start_delay)

    def missed(reason):
        nonlocal consecutive_misses
        consecutive_misses += 1
        status(f"{reason} ({consecutive_misses} misses in a row)")
        if consecutive_misses >= args.max_misses:
            status(f"{args.max_misses} misses in a row - stopping. Check the game "
                   "(facing water? threshold right? logged out?) and rerun.")
            return True
        return False

    with open_loopback() as rec, mss.mss() as sct:
        while not stop_event.is_set():
            if deadline and time.monotonic() >= deadline:
                status(f"Reached the {args.hours} h limit.")
                break

            if not wow_focused():
                status("WoW isn't the focused window - paused.")
                while not stop_event.is_set() and not wow_focused():
                    wait(rec, 0.5)
                status("Resumed.")
                continue

            rest = human.break_due() if casts else 0
            if rest:
                breaks += 1
                status(f"Taking a break for {rest:.0f}s.")
                wait(rec, rest)
                if stop_event.is_set():
                    break

            if args.mode == "mouse":
                region = search_region(args)
                before = grab(sct, region)
            if not press(args.cast_key):
                continue
            casts += 1

            # Let the cast play out and the bobber land before looking/listening.
            wait(rec, human.settle())

            target = None
            if args.mode == "mouse":
                found = find_bobber(before, grab(sct, region), args)
                if not found:
                    not_found += 1
                    if missed("Couldn't spot the bobber - recasting. (Try --test-bobber.)"):
                        break
                    continue
                target = (region["left"] + found[0], region["top"] + found[1])

            bite = listen_for_bite(rec, args)
            if stop_event.is_set():
                break

            if bite:
                if human.ignore_bite():
                    let_go += 1
                    status("Bite - letting this one go on purpose.")
                    wait(rec, random.uniform(1.5, 4.0))
                    continue
                wait(rec, human.reaction())
                result = reel_in(args, target, human)
                if result is None:
                    status("Heard a bite, but WoW wasn't focused - skipped it.")
                elif result:
                    catches += 1
                    consecutive_misses = 0
                    status(f"Bite! Reeled in. ({catches} caught / {casts} casts)")
                else:
                    misclicks += 1
                    status("Clicked next to the bobber on purpose - that one got away.")
                wait(rec, human.loot_wait())
            else:
                no_bite += 1
                if missed(f"No bite heard in {args.timeout:.0f}s - recasting."):
                    break
                wait(rec, random.uniform(0.8, 2.0) if human.enabled else 1.0)

    mins = (time.monotonic() - started) / 60
    print(f"\nDone after {mins:.1f} min: {casts} casts, {catches} reeled in, {no_bite} with no bite heard, "
          f"{not_found} bobber not found, {let_go} let go and {misclicks} misclicked on purpose, {breaks} breaks.")


# --------------------------------------------------------------------------- entry point

def parse_area(text):
    parts = [float(v) for v in text.split(",")]
    if len(parts) != 4 or not (0 <= parts[0] < parts[2] <= 1 and 0 <= parts[1] < parts[3] <= 1):
        raise argparse.ArgumentTypeError("use left,top,right,bottom as fractions 0-1, e.g. 0.15,0.10,0.85,0.75")
    return parts


def build_parser():
    p = argparse.ArgumentParser(description="Sound-triggered auto-fisher for WoW Classic (Windows).")
    p.add_argument("--calibrate", action="store_true", help="show live audio levels to pick a threshold")
    p.add_argument("--test-bobber", action="store_true", help="cast once and show where it finds the bobber")
    p.add_argument("--mode", choices=["mouse", "interact"], default="mouse",
                   help="mouse = right-click the bobber (default); interact = press the Interact Key")
    p.add_argument("--threshold", type=float, default=0.08, help="loudness that counts as a bite (default 0.08)")
    p.add_argument("--cast-key", default="1", help="key bound to Fishing (default 1)")
    p.add_argument("--interact-key", default="f", help="Interact With Target key, for --mode interact (default f)")
    p.add_argument("--stop-key", default="f12", help="global key that stops the script (default f12)")
    p.add_argument("--no-humanize", action="store_true", help="turn off the human-like variation (exact, fixed timings)")
    p.add_argument("--settle", type=float, default=2.5,
                   help="seconds after casting before looking/listening, with --no-humanize and --test-bobber (default 2.5)")
    p.add_argument("--timeout", type=float, default=20.0, help="seconds to listen for a bite before recasting (default 20)")
    p.add_argument("--reaction", type=float, default=0.4, help="delay from bite to reel-in, with --no-humanize (default 0.4)")
    p.add_argument("--loot-wait", type=float, default=2.0, help="wait after reeling in, with --no-humanize (default 2)")
    p.add_argument("--max-misses", type=int, default=10, help="stop after this many misses in a row (default 10)")
    p.add_argument("--hours", type=float, default=0, help="stop after this many hours (default 0 = run until stopped)")
    p.add_argument("--start-delay", type=int, default=5, help="countdown before starting (default 5)")
    p.add_argument("--search-area", type=parse_area, default=[0.15, 0.10, 0.85, 0.75],
                   help="where to look for the bobber: left,top,right,bottom as window fractions")
    p.add_argument("--red-min", type=int, default=100, help="minimum red value for the bobber feather (default 100)")
    p.add_argument("--red-margin", type=int, default=50, help="how much redder than green/blue it must be (default 50)")
    p.add_argument("--min-pixels", type=int, default=15, help="minimum new red pixels to count as the bobber (default 15)")
    return p


def main():
    args = build_parser().parse_args()
    if sys.platform != "win32":
        sys.exit("This script needs Windows.")

    make_dpi_aware()
    start_stop_key_listener(args.stop_key)
    try:
        if args.calibrate:
            calibrate(args)
        elif args.test_bobber:
            test_bobber(args)
        else:
            fish(args)
    except pydirectinput.FailSafeException:
        print("\nStopped: mouse moved to the top-left corner.")
    except KeyboardInterrupt:
        print("\nStopped with Ctrl+C.")


if __name__ == "__main__":
    main()
