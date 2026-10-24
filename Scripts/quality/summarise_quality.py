"""Turns the raw exports into the tables used in the report (M1, M2, M7 + lizard sanity check).

Inputs (out/):  und_<tag>_functions.csv, und_<tag>_classes.csv, und_<tag>_files.csv  (und_export.py)
                lizard_functions.csv                                                 (lizard_run.sh)
Usage:  python summarise_quality.py [TAG]      (TAG default 57277407)
Output: printed tables + out/summary_<tag>_*.csv
"""
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
TAG = sys.argv[1] if len(sys.argv) > 1 else "57277407"
OUT = os.path.join(HERE, "out")
MODULE_ORDER = ["core", "servers", "scene", "editor", "main", "drivers", "platform", "modules", "tests"]
CC_THRESHOLD = 10       # McCabe (1976)
NEST_THRESHOLD = 4      # nesting depth at which a function is usually hard to follow (stated, not standard)


def module_table(fn):
    g = fn.groupby("module")
    t = pd.DataFrame({
        "functions": g.size(),
        "cc_median": g["Cyclomatic"].median(),
        "cc_p95": g["Cyclomatic"].quantile(0.95),
        "cc_max": g["Cyclomatic"].max(),
        f"n_cc>={CC_THRESHOLD}": g["Cyclomatic"].apply(lambda s: (s >= CC_THRESHOLD).sum()),
        f"pct_cc>={CC_THRESHOLD}": g["Cyclomatic"].apply(lambda s: round(100 * (s >= CC_THRESHOLD).mean(), 2)),
        f"n_nest>={NEST_THRESHOLD}": g["MaxNesting"].apply(lambda s: (s >= NEST_THRESHOLD).sum()),
    })
    return t.reindex([m for m in MODULE_ORDER if m in t.index])


def main():
    fn = pd.read_csv(os.path.join(OUT, f"und_{TAG}_functions.csv"))
    cl = pd.read_csv(os.path.join(OUT, f"und_{TAG}_classes.csv"))
    fi = pd.read_csv(os.path.join(OUT, f"und_{TAG}_files.csv"))
    fn = fn.dropna(subset=["Cyclomatic"])
    pd.set_option("display.width", 200)

    # Godot macros (GDCLASS, GDVIRTUAL, ID types, ...) make Understand create entities that have no
    # source lines of their own: ~20 methods per GDCLASS line. They are not hand-written code, so the
    # analysis population is functions with CountLineCode > 0. The excluded count is reported.
    macro = fn[fn["CountLineCode"] == 0]
    fn = fn[fn["CountLineCode"] > 0]
    print(f"[population] {len(fn)} hand-written functions; excluded {len(macro)} macro-generated entities "
          f"(CountLineCode 0; {int((macro['Cyclomatic'] > 1).sum())} of them with Cyclomatic > 1)")

    print("=== M1 Cyclomatic per function (Understand), by module ===")
    m1 = module_table(fn)
    print(m1.to_string())
    m1.to_csv(os.path.join(OUT, f"summary_{TAG}_m1_modules.csv"))
    print("\nTop 15 functions by Cyclomatic:")
    print(fn.sort_values("Cyclomatic", ascending=False)[["file", "line", "function", "Cyclomatic", "MaxNesting", "CountLineCode"]].head(15).to_string(index=False))

    print("\n=== M2 classes (Understand) ===")
    cl = cl.dropna(subset=["CountClassCoupled"])
    cls = cl[cl["kind"].str.contains("Class", na=False)]
    for col in ["CountClassCoupled", "PercentLackOfCohesion", "CountDeclMethod"]:
        s = cls[col]
        print(f"{col:<22} n={len(s)} median={s.median():.0f} p95={s.quantile(0.95):.0f} max={s.max():.0f}")
    print("\nTop 10 classes by CountClassCoupled:")
    print(cls.sort_values("CountClassCoupled", ascending=False)[["file", "class", "CountClassCoupled", "PercentLackOfCohesion", "CountDeclMethod", "CountLineCode"]].head(10).to_string(index=False))
    print("\nNamed classes:")
    print(cls[cls["class"].isin(["EditorNode", "EditorLog", "RenderingServer", "SceneTree", "Node", "Object"])][["file", "class", "CountClassCoupled", "PercentLackOfCohesion", "CountDeclMethod", "CountLineCode"]].to_string(index=False))

    print("\n=== M7 comment ratio by module (sum comment lines / sum code lines) ===")
    g = fi.groupby("module")[["CountLineComment", "CountLineCode"]].sum()
    g["RatioCommentToCode"] = (g["CountLineComment"] / g["CountLineCode"]).round(3)
    print(g.reindex([m for m in MODULE_ORDER if m in g.index]).to_string())

    print("\n=== Sanity check: lizard vs Understand ===")
    cols = ["NLOC", "CCN", "token", "PARAM", "length", "location", "file", "function", "long_name", "start", "end"]
    lz = pd.read_csv(os.path.join(OUT, "lizard_functions.csv"), names=cols, header=None)
    lz["file"] = lz["file"].str.replace("\\", "/", regex=False)
    lz["module"] = lz["file"].str.split("/").str[0]
    lz_tab = lz.groupby("module")["CCN"].agg(functions="size", median="median", max="max",
                                             n_ge10=lambda s: (s >= CC_THRESHOLD).sum())
    print(lz_tab.reindex([m for m in MODULE_ORDER if m in lz_tab.index]).to_string())
    merged = fn.merge(lz, left_on=["file", "line"], right_on=["file", "start"], how="inner")
    same = (merged["Cyclomatic"] == merged["CCN"]).mean()
    within1 = ((merged["Cyclomatic"] - merged["CCN"]).abs() <= 1).mean()
    rho = merged[["Cyclomatic", "CCN"]].corr(method="spearman").iloc[0, 1]
    print(f"matched functions (same file + start line): {len(merged)}; identical CC: {same:.1%}; "
          f"within +-1: {within1:.1%}; Spearman rho: {rho:.3f}")
    worst = merged.assign(diff=(merged["Cyclomatic"] - merged["CCN"]).abs()).sort_values("diff", ascending=False)
    print(worst[["file", "line", "function_x", "Cyclomatic", "CCN"]].head(5).to_string(index=False))


if __name__ == "__main__":
    main()
