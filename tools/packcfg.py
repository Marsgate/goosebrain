"""Which pack board the pack tools work on: the 3S pack (the default) or the 2S pack.

Every pack tool reads the board from its command line: `--board=pack2s` (or `--board pack2s`), or the environment
variable PACK_BOARD=pack2s for a script that spawns the others. Nothing else changes between the boards but the
constants each tool keeps under `if cfg.BOARD == "pack2s"`.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOARDS = {
    "pack": ROOT / "kicad-pack/goosepack.kicad_pcb",
    "pack2s": ROOT / "kicad-pack-2s/goosepack2s.kicad_pcb",
}


def board_name(default="pack", argv=None):
    """The board named on the command line (--board=NAME or --board NAME), else $PACK_BOARD, else default."""
    argv = sys.argv if argv is None else argv
    for i, a in enumerate(argv):
        if a.startswith("--board="):
            return a[8:]
        if a == "--board" and i + 1 < len(argv):
            return argv[i + 1]
    return os.environ.get("PACK_BOARD", default)


BOARD = board_name()
if BOARD not in BOARDS:
    raise SystemExit(f"unknown pack board {BOARD!r}: {', '.join(BOARDS)}")
PCB = BOARDS[BOARD]
os.environ["PACK_BOARD"] = BOARD      # so a script that re-runs itself or spawns the others (execv) keeps the board
FLAG = f"--board={BOARD}"          # to pass on to the tools a script runs
