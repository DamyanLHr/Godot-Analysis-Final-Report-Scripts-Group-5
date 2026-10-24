"""Puts the three Understand "Dependencies > Depends On" graphs of core/, servers/ and scene/ side by
side as one figure for M3 (pure image composition; no numbers are changed).

Usage: python compose_m3.py [figures_dir]
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.image as mpimg
import matplotlib.pyplot as plt

d = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "figures")
parts = ["core", "servers", "scene"]
imgs = [mpimg.imread(os.path.join(d, f"fig_M3_{p}_depends_on.png")) for p in parts]
fig, axes = plt.subplots(1, 3, figsize=(10, 2.8), dpi=200)
for ax, img, p in zip(axes, imgs, parts):
    ax.imshow(img)
    ax.set_title(f"{p}/ depends on", fontsize=9)
    ax.axis("off")
fig.tight_layout()
out = os.path.join(d, "fig_M3_layer_dependencies.png")
fig.savefig(out, facecolor="white")
print(f"[compose_m3] {out}")
