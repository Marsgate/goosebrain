"""Route the pack board to a fixed point and say what's left: the loop an LLM (or a person) drives.

    python3 tools/route_loop.py <setup.kicad_pcb> <workdir> [attempt ...] [--board=pack2s]

Each attempt starts from the same post-setup board (tools/route_pack.py setup) and repeats
    kicad-cli DRC with zone refill -> tools/route_llm.py on its unconnected pairs
until a pass routes nothing new. Attempts are route_llm.py option strings, e.g. "" (plain), "--escape=U7",
"--escape=U7 --first=/SW1,/SW2"; "--keep" routes on top of the board's existing routing instead of clearing the
"autoroute" group first; "auto" means: the best attempt so far, plus --first= the nets it left. The last DRC of
each attempt is the score: copper violations first, then unconnected pairs.

<workdir>/loop_report.json holds, for the best attempt: the score, the failed pairs with route_llm.py's diagnosis
(reason, the nets in the way, a hint), the pairs on nets the router skips (planes: route_pack.py's job), and every
attempt's score, so the next move can be read off the file rather than a render.
"""
import collections
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KPY = "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3"
CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
sys.path.insert(0, str(ROOT / "tools"))
import packcfg  # noqa: E402

PCB = packcfg.PCB                                   # --board=pack2s: the 2S pack
COPPER = {"clearance", "shorting_items", "hole_clearance", "holes_co_located", "hole_to_hole", "tracks_crossing",
          "copper_edge_clearance", "track_width", "solder_mask_bridge"}
SKIP = {"/BAT_N", "/PACK-"}                 # planes route_pack.py fans out; match grid_router.SKIP
MAX_PASSES = 1                  # pass 2 has never routed anything new on the pack board


def drc(out):
    subprocess.run([CLI, "pcb", "drc", "--format", "json", "--refill-zones", "--save-board", "-o", out, PCB],
                   check=True, capture_output=True)
    return json.load(open(out))


def net_of(u):
    import re
    m = re.search(r"\[(/[^\]]+)\]", u["items"][0]["description"])
    return m.group(1) if m else "?"


def attempt(setup, work, k, opts):
    shutil.copy(setup, PCB)
    last, passes, stubs = None, [], []
    for p in range(MAX_PASSES):
        d = drc(work / f"a{k}_drc{p}.json")
        rep = work / f"a{k}_pass{p}.json"
        keep = "--keep" in opts.split()                                  # route on top of what's there
        args = [a for a in opts.split() if a != "--keep"] + (["--clear"] if p == 0 and not keep else [])
        if p > 0:
            args = [a for a in args if not a.startswith("--escape=")]     # stubs are laid once
        r = subprocess.run([KPY, "-u", ROOT / "tools/route_llm.py", work / f"a{k}_drc{p}.json", rep, packcfg.FLAG,
                            *args], capture_output=True, text=True, cwd=ROOT)
        if r.returncode:
            raise SystemExit(r.stderr[-2000:])
        last = json.load(open(rep))
        passes.append(last["summary"]["routed"])
        stubs = stubs or last["summary"].get("escape_stubs", [])
        print(f"  attempt {k} pass {p}: {last['summary']['routed']} routed, {last['summary']['failed']} failed",
              flush=True)
        if last["summary"]["routed"] == 0 or last["summary"]["failed"] == 0:
            break
    d = drc(work / f"a{k}_final.json")
    shutil.copy(PCB, work / f"a{k}.kicad_pcb")
    copper = collections.Counter(v["type"] for v in d["violations"] if v["type"] in COPPER)
    unc = d["unconnected_items"]
    return {"attempt": k, "options": opts, "passes_routed": passes,
            "copper_violations": sum(copper.values()), "copper_by_type": dict(copper),
            "unconnected": len(unc), "unconnected_signal": sum(net_of(u) not in SKIP for u in unc),
            "skipped_nets_open": [{"net": net_of(u), "between": [i["description"] for i in u["items"]]}
                                  for u in unc if net_of(u) in SKIP],
            "failed": last["failed"], "escape_stubs": stubs,
            "board": str(work / f"a{k}.kicad_pcb")}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--board")]    # --board=pack2s is packcfg's
    setup, work = Path(args[0]), Path(args[1])
    plans = args[2:] or ["", "--escape=U7", "auto"]
    work.mkdir(parents=True, exist_ok=True)
    results = []
    for k, opts in enumerate(plans):
        if opts == "auto":
            best = min(results, key=lambda r: (r["copper_violations"], r["unconnected"]))
            nets = list(dict.fromkeys(f["net"] for f in best["failed"]))
            opts = " ".join(x for x in (best["options"], "--first=" + ",".join(nets) if nets else "") if x)
        print(f"attempt {k}: {opts or '(plain)'}", flush=True)
        results.append(attempt(setup, work, k, opts))
        r = results[-1]
        print(f"  -> {r['copper_violations']} copper violations, {r['unconnected']} unconnected "
              f"({r['unconnected_signal']} signal)", flush=True)
        best = min(results, key=lambda r: (r["copper_violations"], r["unconnected"]))
        report = {"best": best, "attempts": [{k2: v for k2, v in x.items() if k2 not in ("failed", "escape_stubs")}
                                             for x in results]}
        json.dump(report, open(work / "loop_report.json", "w"), indent=1)
    print(f"best: attempt {best['attempt']} ({best['options'] or 'plain'}): {best['copper_violations']} copper, "
          f"{best['unconnected']} unconnected -> {work / 'loop_report.json'}")


if __name__ == "__main__":
    main()
