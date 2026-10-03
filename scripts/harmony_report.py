"""Run the corpus through translate_chord and print one line per source id.

    python scripts/harmony_report.py

Downloads whatever the cache ($FORMAT_CONVERTERS_CACHE, default ~/.cache/format-converters) lacks.
The first lines are "<source id> rn=.. letter=.. approx=.. none=.. no_chord=.."; the rest says how
the run compares with the prototype's baseline (tests/corpus/baseline.json.gz).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))

from corpus import fetch, run  # noqa: E402


def main() -> int:
    fetch.fetch_all()
    res = run.run()
    print("\n".join(run.format_counts(res["counts"])))
    base_counts = {}
    for sid, refs in res["baseline"].items():
        c = {o: 0 for o in run.OUTCOMES}
        for v in refs.values():
            c[v.rstrip("*")] += 1
        base_counts[sid] = c
    print("\nprototype baseline, as rn/letter/approx/none/no_chord (the function rule is not applied in it):")
    for sid in sorted(base_counts):
        print(f"  prototype {sid}: " + "/".join(str(base_counts[sid][o]) for o in run.OUTCOMES))
    print("\nchords stored as their function (suspension, addition, omission, Cad64):", dict(res["function"]))
    print(f"chords worse than the baseline: {len(res['worse'])}; verification problems: {len(res['problems'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
