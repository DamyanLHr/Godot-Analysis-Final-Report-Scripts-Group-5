"""UML class diagrams for proposal P2 (Vlad): the editor test suites. Redraws Vlad's two PlantUML
figures ("Proposed tests for the editor" and the combined tests + split diagram) with the class names
and test cases of our demonstrative patches (Scripts/work/after-split.patch for P1,
Scripts/work/after-tests.patch for P2), in the same style as fig_P1_editor_node_split.png.

Changes from Vlad's originals: our class names (EditorMenuActionHandler, EditorSceneReloader), the
test-case names as implemented, the EditorTestFixture the [Editor] cases need, TestUtils instead of
SignalWatcher (no suite uses SignalWatcher), and "delegates to" instead of composition, because the
split classes are static and EditorNode holds no instances of them.

Usage:  python uml_editor_tests.py [OUT_DIR]
Output: out/figures/fig_P2_editor_tests.png, out/figures/fig_P2_tests_and_split.png
"""
import os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "out", "figures")

FONT = dict(family="DejaVu Sans Mono", size=8)
LINE_H = 0.22
SUITE, EXISTING, SPLIT = "#eef5ea", "#eef1f6", "#fbf4e6"


def uml_class(ax, x, y, w, name, methods, stereotype=None, fill="#ffffff"):
    """Draws a class box with a name compartment and an operations compartment; returns its anchors."""
    title = ([f"«{stereotype}»"] if stereotype else []) + [name]
    h_title = LINE_H * len(title) + 0.12
    h_ops = LINE_H * len(methods) + 0.12
    style = dict(linewidth=1.2, edgecolor="#222222")
    ax.add_patch(Rectangle((x, y - h_title), w, h_title, facecolor=fill, zorder=2, **style))
    ax.add_patch(Rectangle((x, y - h_title - h_ops), w, h_ops, facecolor="#ffffff", zorder=2, **style))
    for i, t in enumerate(title):
        ax.text(x + w / 2, y - 0.08 - LINE_H * (i + 0.5), t, ha="center", va="center", zorder=3,
                fontweight="bold" if t == name else "normal", **FONT)
    for i, m in enumerate(methods):
        ax.text(x + 0.08, y - h_title - 0.08 - LINE_H * (i + 0.5), m, ha="left", va="center", zorder=3, **FONT)
    bottom = y - h_title - h_ops
    return {"top": (x + w / 2, y), "bottom": (x + w / 2, bottom), "left": (x, (y + bottom) / 2),
            "right": (x + w, (y + bottom) / 2), "y_bottom": bottom}


def package(ax, x, y, w, h, title, fill):
    """UML package as a titled frame; (x, y) is the top-left corner."""
    ax.add_patch(Rectangle((x, y - h), w, h, facecolor=fill, edgecolor="#222222", linewidth=1.4, zorder=0))
    ax.text(x + w / 2, y - 0.22, title, ha="center", va="center", fontweight="bold", zorder=1,
            family="DejaVu Sans", size=9)


def arrow(ax, a, b, label=None, label_at=0.5, rad=0.0):
    """UML dependency: dashed line with an open arrowhead."""
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="->", mutation_scale=12, linewidth=1, linestyle="--",
                                 color="#222222", zorder=1, connectionstyle=f"arc3,rad={rad}"))
    if label:
        lx, ly = a[0] + (b[0] - a[0]) * label_at, a[1] + (b[1] - a[1]) * label_at
        ax.text(lx, ly + 0.06, label, ha="center", va="bottom", fontsize=7, style="italic",
                color="#444444", zorder=3, bbox=dict(facecolor="white", edgecolor="none", pad=0.5, alpha=0.8))


def save(fig, name):
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, name)
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="white")
    print("[uml] ->", out)


SCENE_MANAGER_CASES = ['+ "[Editor] Switching scene updates the edited scene"',
                       '+ "[Editor] Switching scene updates the scene tree dock"']
MENU_CASES = ['+ "[Editor] New scene option opens a new scene tab"',
              '+ "[Editor] Quitting asks before discarding unsaved scenes"']
RELOADER_CASES = ['+ "[Editor] Reloaded instances point to the new resource"']
LOG_CASES = ['+ "Short log: drawing starts at the first message"',
             '+ "Line limit reached: drawing starts at the message that fills it"',
             '+ "Repeated message over the limit: its oldest lines are skipped"',
             '+ "Collapsed log: a repeated message takes one line"',
             '+ "Filtered-out messages take no lines"']

# --- Figure 1: the suites (replaces "Proposed tests for the editor") ----------------------------
fig, ax = plt.subplots(figsize=(13.2, 5.0))
ax.set_xlim(0, 19.2); ax.set_ylim(3.3, 8.9); ax.axis("off")
package(ax, 0.1, 8.8, 19.0, 5.4, "tests/editor/ (new, 10 test cases)", SUITE)
uml_class(ax, 0.4, 8.3, 8.9, "TestEditorSceneManager", SCENE_MANAGER_CASES, "test suite")
uml_class(ax, 9.9, 8.3, 8.9, "TestEditorMenuActionHandler", MENU_CASES, "test suite")
uml_class(ax, 0.4, 6.4, 8.9, "TestEditorLog", ["  [EditorLog] cases, no scene tree needed:"] + LOG_CASES, "test suite")
uml_class(ax, 9.9, 6.4, 8.9, "TestEditorSceneReloader", RELOADER_CASES, "test suite")
uml_class(ax, 9.9, 4.9, 8.9, "EditorTestFixture", ["+ open_scene(root) : int",
                                                   "  one EditorNode per [Editor] test case"], "fixture")
save(fig, "fig_P2_editor_tests.png")
plt.close(fig)

# --- Figure 2: suites + what they test (replaces the combined diagram) ---------------------------
# Each suite sits level with the class it tests, so the «tests» arrows run straight across.
fig, ax = plt.subplots(figsize=(16.0, 9.2))
ax.set_xlim(0, 24.4); ax.set_ylim(1.5, 13.9); ax.axis("off")

package(ax, 0.1, 13.8, 9.3, 8.7, "tests/editor/ (new)", SUITE)
s_scene = uml_class(ax, 0.4, 13.2, 8.7, "TestEditorSceneManager", SCENE_MANAGER_CASES, "test suite")
s_menu = uml_class(ax, 0.4, 11.6, 8.7, "TestEditorMenuActionHandler", MENU_CASES, "test suite")
s_reload = uml_class(ax, 0.4, 10.0, 8.7, "TestEditorSceneReloader", RELOADER_CASES + [
    "  (temp scene file via TestUtils::get_temp_path)"], "test suite")
s_log = uml_class(ax, 0.4, 8.4, 8.7, "TestEditorLog", ["+ 5 [EditorLog] cases: every branch of",
                                                       "  find_start_position taken both ways"], "test suite")
fixture = uml_class(ax, 0.4, 6.6, 8.7, "EditorTestFixture", ["+ open_scene(root) : int",
                                                             "  one EditorNode per [Editor] test case"], "fixture")

package(ax, 0.1, 4.6, 9.3, 2.6, "tests/ (existing)", EXISTING)
listener = uml_class(ax, 0.4, 4.0, 5.5, "GodotTestCaseListener", [
    "+ test_case_start()",
    '  "[Editor]" tag sets up SceneTree,',
    "  DisplayServerMock, EditorSettings,",
    "  EditorPaths"], "existing")
uml_class(ax, 6.2, 4.0, 2.9, "TestUtils", ["+ get_temp_path()"], "existing")

package(ax, 10.3, 13.8, 14.0, 12.2, "editor/ (after the split)", SPLIT)
c_scene = uml_class(ax, 11.0, 13.2, 6.5, "EditorSceneManager", ["+ _set_current_scene_nocheck()", "  static"], "new")
c_menu = uml_class(ax, 11.0, 11.6, 6.5, "EditorMenuActionHandler", ["+ _menu_option_confirm()", "  static"], "new")
c_reload = uml_class(ax, 11.0, 10.0, 6.5, "EditorSceneReloader", ["+ reload_instances_with_path_in_edited_scenes()",
                                                                  "  static"], "new")
c_log = uml_class(ax, 11.0, 8.4, 6.5, "EditorLog", [
    "+ find_start_position(messages, visible,",
    "      collapse, line_limit) : StartPosition",
    "- _rebuild_log()"])
node = uml_class(ax, 18.4, 6.6, 5.6, "EditorNode", [
    "+ _menu_option_confirm()",
    "+ _set_current_scene_nocheck()",
    "+ reload_instances_with_path_",
    "    in_edited_scenes()",
    "  (one-line forwarders)"], "coordinator")
ax.text(18.5, 4.5, "The split classes are static and\nreach editor state through\nEditorNode::get_singleton(),"
        "\nso the [Editor] cases need a\nrunning EditorNode (fixture).", fontsize=7, style="italic",
        color="#444444", ha="left", va="top", zorder=3,
        bbox=dict(facecolor="#ffffe0", edgecolor="#999999", pad=4))

for suite, target in ((s_scene, c_scene), (s_menu, c_menu), (s_reload, c_reload), (s_log, c_log)):
    arrow(ax, suite["right"], target["left"], "«tests»")
for i, box in enumerate((c_scene, c_menu, c_reload)):
    arrow(ax, (node["top"][0] - 1.2 + 1.2 * i, node["top"][1]), box["right"], "delegates to" if i == 1 else None, 0.55)
arrow(ax, fixture["right"], node["left"], "«creates»", 0.3)
arrow(ax, fixture["bottom"], listener["top"], "«uses [Editor] setup»", 0.3)
save(fig, "fig_P2_tests_and_split.png")
plt.close(fig)
