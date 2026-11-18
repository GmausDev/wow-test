# wow-classic-fisher

A sound-triggered auto-fisher for **World of Warcraft Classic** on Windows.

It casts, finds the bobber on screen, waits for the splash of a bite, right-clicks the bobber and casts again, until you stop it. It also behaves a bit like a person: reaction times vary, the mouse glides rather than jumps, clicks land slightly off-centre, it sometimes lets a fish go or misclicks, and it takes breaks.

> ⚠️ **Read this first.** Automating gameplay breaks Blizzard's Terms of Use, and accounts get suspended or banned for it. The human-like variation makes the pattern less mechanical, but it doesn't make the script undetectable. Long unattended sessions and player reports are still the classic way bots get caught. Use it at your own risk, ideally on an account you can afford to lose.

## How it works

1. **Look:** takes a screenshot of the water just before casting.
2. **Cast:** presses your Fishing key.
3. **Find:** once the bobber lands, takes another screenshot and looks for the *new* red pixels (the bobber's feather). Comparing before and after means red things that were already on screen, like UI or nameplates, are ignored.
4. **Hover and listen:** glides the mouse onto the bobber and rests it there, while watching your PC's audio output for the volume spike of a bite.
5. **Reel in:** right-clicks. Auto Loot takes the catch.

It only reads the screen and the system audio, and sends ordinary key presses and mouse clicks. It doesn't read or change the game's memory or files. It only acts while WoW is the focused window, and pauses if you switch away.

### Why mouse mode?

In Classic Era and Mists Classic (and possibly other Classic clients), the Interact Key only reaches a short distance, so bobbers that land farther out can't be reeled in with it. Clicking the bobber works at any cast distance. If your bobbers always land close enough that the hook icon appears above them, `--mode interact` presses the Interact Key instead and skips the screen reading.

## Requirements

- Windows 10/11
- Python 3.9+
- WoW running on your **main monitor** (fullscreen or windowed)

```powershell
pip install -r requirements.txt
```

## In-game setup (once)

| Setting | What to do |
|---|---|
| Fishing key | Put Fishing on an action bar slot bound to `1` (or pass `--cast-key`) |
| Auto Loot | Turn it on in the options, or type `/console autoLootDefault 1` |
| Sound | Sound Effects **on**; Music, Ambience and Dialog **off** |
| Camera | Zoom all the way into first-person and look out over open water, so the water fills the middle of the screen |
| Spot | Somewhere quiet, without other players running through your view |

Also mute everything else on your PC (Discord, music, browser tabs). The script hears every sound your speakers play, and other noises will look like bites.

## Usage

**1. Calibrate the sound**

```powershell
python wow_fisher.py --calibrate
```

Fish by hand a few times and watch the meter. Note the level while idle and the peak when the bobber splashes. Your threshold goes roughly halfway between. Press `F12` to finish.

**2. Check that it can see the bobber**

```powershell
python wow_fisher.py --test-bobber
```

It casts once, looks for the bobber, puts the mouse on it, and saves `bobber_debug.png`. In that image, magenta marks the new red pixels and a green cross marks where it would click. Reel that cast in yourself.

**3. Fish**

```powershell
python wow_fisher.py --threshold 0.08
```

You get 5 seconds to click into WoW.

**Buffs (lures, food, drinks)**

For zones where you need extra fishing skill, `--buff KEY:MINUTES[:SECONDS]` presses a key on a timer. Repeat it for each buff:

```powershell
python wow_fisher.py --threshold 0.08 --buff 2:10:6 --buff 3:30:12
```

That presses `2` every 10 minutes and waits 6 s for it to finish (a lure), and `3` every 30 minutes with a 12 s wait (food). `MINUTES` is how long the buff lasts; `SECONDS` is how long your character is busy applying or eating it (default 6). Every buff is applied once at the start, then refreshed between casts, a little before it runs out.

- **Lure:** in Classic a lure has to be used and then clicked onto the pole, so put a macro on the key (use your lure's name):
  ```
  /use Bright Baubles
  /use 16
  ```
  If your client applies lures to the equipped pole by itself, the lure can go straight on the bar.
- **Food / drink:** put the item on the bar. Set `SECONDS` to how long you must keep eating for the buff (about 10 s for Well Fed, plus a little), since the next cast makes you stand up.

The script can't see your buffs or bags: it only presses the key on time. When you run out of lures or food it keeps fishing without them.

**Stopping:** press `F12`, slam the mouse into the top-left corner of the screen, or press `Ctrl+C` in the console. It also stops by itself after 10 misses in a row (for example if you died, moved, or got disconnected), and after `--hours` if you set it.

## Options

| Option | Default | What it does |
|---|---|---|
| `--threshold` | `0.08` | Loudness that counts as a bite |
| `--mode` | `mouse` | `mouse` clicks the bobber; `interact` presses the Interact Key |
| `--cast-key` | `1` | Key bound to Fishing |
| `--interact-key` | `f` | Interact With Target key (interact mode only) |
| `--stop-key` | `f12` | Global stop key |
| `--timeout` | `28` | Seconds to listen for a bite before recasting (a cast can last up to about 30 s) |
| `--hours` | `0` | Stop after this many hours (0 = run until stopped) |
| `--close-game` | off | Close WoW when the `--hours` limit is reached (needs `--hours`) |
| `--buff` | none | `KEY:MINUTES[:SECONDS]`: press KEY every MINUTES to refresh a lure/food buff, then wait SECONDS (default 6). Repeatable |
| `--max-misses` | `10` | Stop after this many misses in a row |
| `--no-hover` | off | Don't rest the mouse on the bobber while waiting; move there only when a fish bites (slower) |
| `--no-humanize` | off | Exact, fixed timings with no deliberate mistakes or breaks |
| `--search-area` | `0.15,0.10,0.85,0.75` | Where to look for the bobber: left,top,right,bottom as fractions of the window |
| `--red-min` | `100` | Minimum red value for the feather |
| `--red-margin` | `50` | How much redder than green/blue the feather must be |
| `--min-pixels` | `15` | Minimum new red pixels to count as the bobber |

Run `python wow_fisher.py --help` for the full list.

## Human-like variation

These are set in the `HUMAN` table at the top of `wow_fisher.py`:

| Setting | Default | Meaning |
|---|---|---|
| `reaction` | 0.25–0.9 s, usually ~0.4 | Time from the splash to the click |
| `settle` | 2.3–3.2 s | Wait after casting before looking for the bobber |
| `loot_wait` | 0.9–2.2 s | Pause between reeling in and the next cast |
| `jitter_px` | 3 px (capped at 6) | Normal click offset from the bobber's centre |
| `miss_chance` | 4% | Chance to ignore a bite and let the fish go |
| `misclick_chance` | 2% | Chance to click 22–45 px next to the bobber |
| `move_time` | 0.12–0.35 s | How long the mouse takes to glide to the bobber |
| `break_every` / `break_length` | every 35–90 casts, for 20–150 s | Short breaks |
| `buff_early` | 8–45 s | How long before a buff runs out it gets refreshed |
| `buff_extra` | 0.4–1.8 s | Extra wait after a buff's own apply/eating time |

## Troubleshooting

| Symptom | Try |
|---|---|
| "Couldn't spot the bobber" | Run `--test-bobber` and open `bobber_debug.png`. No magenta on the feather (dark zone or night): `--red-min 70 --red-margin 35`. Too little magenta: `--min-pixels 6`. Bobber outside the picture: widen `--search-area`. |
| Reels in at random moments | Threshold too low, or another app is making noise. Recalibrate and mute other apps. |
| Never hears bites | Threshold too high, or Sound Effects are off or too quiet. Keep volumes the same as when you calibrated. |
| Mouse lands in the wrong place | Make sure WoW is on the main monitor. On multi-monitor setups, the click coordinates follow the main screen. |
| Keys do nothing in game | Run the console as the same user as WoW. If WoW runs as administrator, run the script as administrator too. |

## Limitations

- **Bags:** when your bags are full, it keeps fishing but can't loot.
- **Interruptions:** it doesn't notice being attacked, whispered or disconnected. The miss limit eventually stops it.
- **Testing:** the logic has been tested against simulated audio, screens and input, not against the live game. Expect to tune the threshold and colour settings for your spot.

## Tests

`tests/` runs the script's logic on any OS against simulated audio, screenshots and input. Real WoW isn't needed:

```bash
cd tests
python test_vision.py && python test_interact.py && python test_loop.py && python test_buffs.py
```
