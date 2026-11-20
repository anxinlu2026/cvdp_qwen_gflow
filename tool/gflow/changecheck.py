"""Host-side (never inside Qwen's cell): write the RTL of the agent's list of changes with rtlapply and compare it with RtlModel in the simulator (simcheck).
When the whole list differs from RtlModel with all its switches, the entries are also applied one more at a time (the first k entries against RtlModel with the first k switches),
and the first k that differs is reported: a fact about where to look, not a proof (an entry before it may show its error only together with this one).
usage: python3 changecheck.py --work DIR --rtl ORIGINAL_RTL_DIR [--out DIR] [--edges 200]
  --work: the agent's files (rtl_changes.json, rtl_model.py, interface.json); the RTL is written to WORK/rtl_fixed. Prints the facts and one JSON line."""
import argparse, json, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import rtlapply, simcheck

NAME = "rtl_changes.json"


def check(work, rtl, out=None, edges=200, locate=True):
    work, rtl = Path(work), Path(rtl)
    res = {"ok": False, "applied": None}
    lines = []

    def finish():
        res["text"] = "\n".join(lines)
        if out:
            Path(out).mkdir(parents=True, exist_ok=True)
            Path(out, "sim_check.txt").write_text(res["text"] + "\n")
        return res
    if not (work / NAME).exists():
        lines.append(f"there is no file {NAME}: no RTL was written")
        return finish()
    try:
        ch = rtlapply.load(work / NAME)
    except ValueError as e:
        lines.append(str(e)); return finish()
    r = rtlapply.apply(ch, rtl, work / "rtl_fixed")
    names = rtlapply.compare_names(r["names"], work / "rtl_model.py")
    sw = rtlapply.model_switches(work / "rtl_model.py") or []
    res["applied"], res["names_ok"] = r["ok"], sorted(sw) == sorted(r["names"])
    lines.append(f"rtlapply wrote rtl_fixed/ from {NAME}: " + (f'all edits applied ({r["applied"]})' if r["ok"] else f'{r["failed"]} edits NOT applied'))
    lines += [l for l in r["lines"] if "NOT APPLIED" in l or "no edit" in l] + [n for n in names if not n.startswith("every switch")]
    if not r["ok"] or not res["names_ok"]:
        lines.append("the simulator was not run: first every switch of the model needs one entry and every edit must apply")
        return finish()
    s = simcheck.check(work / "rtl_fixed", work, model_rtl=rtl, fix="list:" + ",".join(sw), edges=edges, out=out)
    res["ok"], res["sim"] = bool(s.get("ok")), {k: v for k, v in s.items() if k != "text"}
    lines.append(s["text"])
    if not res["ok"] and locate and len(ch) > 1:
        lines.append("")
        lines.append("the entries one more at a time, in the order of the list (the first k entries applied, against RtlModel with the switches of these k entries):")
        with tempfile.TemporaryDirectory() as d:
            for k in range(1, len(ch) + 1):
                rtlapply.apply(ch[:k], rtl, Path(d, "r"))
                p = simcheck.check(Path(d, "r"), work, model_rtl=rtl, fix="list:" + ",".join(c["switch"] for c in ch[:k]), edges=edges)
                if p.get("ok"):
                    lines.append(f'  first {k} (up to {ch[k - 1]["switch"]}): no difference')
                    continue
                first = next((l.strip() for l in p["text"].splitlines() if l.startswith("  edge")), None) or next((l for l in p["text"].splitlines() if "error" in l.lower()), p["text"].splitlines()[0])[:300]
                lines.append(f'  first {k} (up to {ch[k - 1]["switch"]}): DIFFERENT   {first}')
                lines.append(f'  the entry {ch[k - 1]["switch"]} is the first with which the RTL and RtlModel differ; the entries after it were not run')
                res["first_different"] = ch[k - 1]["switch"]
                break
            else:
                lines.append("  no single step differs: the difference is only there with all switches (a switch of the model without its own entry, or RtlModel(fix of all names) not the same as the names one by one)")
    return finish()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True); ap.add_argument("--rtl", required=True); ap.add_argument("--out"); ap.add_argument("--edges", type=int, default=200)
    a = ap.parse_args()
    r = check(a.work, a.rtl, a.out, a.edges)
    print(r.pop("text")); print(json.dumps(r, default=str)[:1200])
