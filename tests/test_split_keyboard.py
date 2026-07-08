"""Tests for the x-axis section splitting used to cut a keyboard into pieces
that each fit a single print bed.

The pure seam math lives in ``Keyboard._assign_x_sections`` and is exercised
directly with hand-built column data (fast, no SolidPython). One end-to-end
characterization test drives the real ``Keyboard`` on a committed layout to
guard the wiring.
"""
import json
from pathlib import Path

from parameters import Parameters
from keyboard import Keyboard

SPACING = 19.05  # default switch_spacing (mm per key unit)
FIXTURES = Path(__file__).parent / "fixtures"


def columns(*specs):
    """Build ``_assign_x_sections`` input from readable (x_start_u, [widths]) specs.

    Each spec is one x column: its left edge in key units and the widths (in
    units) of the keys stacked in that column. Returned coordinates are in mm.
    """
    result = []
    for x_start_u, widths in specs:
        x_ends = [(x_start_u + w) * SPACING for w in widths]
        result.append((x_start_u * SPACING, x_ends))
    return result


def section_count(assignments):
    return max((s for column in assignments for s in column), default=0) + 1


def _section_spans(assignments, cols):
    spans = {}
    for (x_start_mm, x_ends), col_sections in zip(cols, assignments):
        for x_end_mm, section in zip(x_ends, col_sections):
            low, high = spans.get(section, (x_start_mm, x_end_mm))
            spans[section] = (min(low, x_start_mm), max(high, x_end_mm))
    return [high - low for low, high in (spans[s] for s in sorted(spans))]


def max_section_width(assignments, cols):
    return max(_section_spans(assignments, cols))


def min_section_width(assignments, cols):
    return min(_section_spans(assignments, cols))


class TestAssignXSections:
    def test_narrow_board_is_one_section(self):
        # Five 1u keys span 5u (95.25mm); well under a 330mm plate.
        cols = columns((0, [1]), (1, [1]), (2, [1]), (3, [1]), (4, [1]))
        assignments = Keyboard._assign_x_sections(cols, 330, left_margin=10)
        assert section_count(assignments) == 1

    def test_board_wider_than_plate_splits(self):
        # ~21u board on a 200mm (~10u) plate must use more than one section.
        cols = columns(*[(i, [1]) for i in range(21)])
        assignments = Keyboard._assign_x_sections(cols, 200, left_margin=10)
        assert section_count(assignments) >= 2

    def test_wide_key_straddling_seam_is_kept_whole(self):
        # A 6.25u key spanning 10.25->16.5u fits within a 330mm (~17u) plate, so
        # the board should split into exactly 2 sections, not bump the wide key
        # into a spurious third one (the ai_battleship regression).
        cols = columns(
            *[(i, [1]) for i in range(10)],   # 0..10u
            (10.25, [6.25]),                  # wide key: 10.25 -> 16.5u
            *[(i, [1]) for i in range(17, 28)],  # 17..28u
        )
        assignments = Keyboard._assign_x_sections(cols, 330, left_margin=10)
        assert section_count(assignments) == 2

    def test_boundary_edge_does_not_spawn_empty_section(self):
        # Two keys in one column whose right edge lands exactly on the threshold
        # must share a single new section rather than each appending one. This is
        # the structural fix over the old append-in-else loop.
        exactly_one_plate = 5 * SPACING
        cols = [
            (0.0, [SPACING]),                                   # fits section 0
            (SPACING, [exactly_one_plate, exactly_one_plate]),  # both == threshold
        ]
        assignments = Keyboard._assign_x_sections(cols, exactly_one_plate, left_margin=0)
        # No phantom section, and both boundary keys share one index.
        assert section_count(assignments) == 2
        assert assignments[1] == [1, 1]

    def test_left_margin_reserves_wall_space(self):
        # A key ending at 195mm fits a 200mm plate with no margin, but not once a
        # 10mm wall is reserved (195 + 10 > 200), forcing a new section. A first
        # key that comfortably fits keeps section 0 populated in both cases.
        cols = [(0.0, [50.0]), (100.0, [195.0])]
        no_margin = Keyboard._assign_x_sections(cols, 200, left_margin=0)
        with_margin = Keyboard._assign_x_sections(cols, 200, left_margin=10)
        assert section_count(no_margin) == 1
        assert section_count(with_margin) == 2

    def test_empty_board(self):
        assert Keyboard._assign_x_sections([], 330, left_margin=10) == []


class TestBalancedXSections:
    def test_balancing_removes_thin_remainder(self):
        # A ~27.75u board with a 6.25u key at 10.25->16.5u on a ~300mm (15.75u)
        # plate. Greedy packs section 1 to the brim and leaves a 2u sliver;
        # balancing keeps the same section count but evens the widths out.
        cols = columns(
            *[(i, [1]) for i in range(10)],       # 0..10u
            (10.25, [6.25]),                      # wide key: 10.25 -> 16.5u
            *[(i + 0.5, [1]) for i in range(16, 27)],  # 16.5..27.5u
        )
        greedy = Keyboard._assign_x_sections(cols, 300, left_margin=5)
        balanced = Keyboard._balanced_x_sections(cols, 300, left_margin=5)
        # Same number of sections...
        assert section_count(balanced) == section_count(greedy)
        assert section_count(balanced) == 3
        # ...but the widest section is smaller and the sliver is gone.
        assert max_section_width(balanced, cols) < max_section_width(greedy, cols)
        assert min_section_width(balanced, cols) > min_section_width(greedy, cols)

    def test_balancing_preserves_minimum_count(self):
        # On a 330mm plate the wide key forces section 0 to reach 16.5u, so 2
        # sections is the only option; balancing must not add a third.
        cols = columns(
            *[(i, [1]) for i in range(10)],
            (10.25, [6.25]),
            *[(i, [1]) for i in range(17, 28)],
        )
        assert section_count(Keyboard._balanced_x_sections(cols, 330, left_margin=10)) == 2

    def test_single_section_untouched(self):
        cols = columns((0, [1]), (1, [1]), (2, [1]))
        assert section_count(Keyboard._balanced_x_sections(cols, 330, left_margin=10)) == 1


def build_keyboard(fixture_name, x_build_size):
    parameters = Parameters({"x_build_size": x_build_size, "y_build_size": x_build_size})
    keyboard = Keyboard(parameters)
    with open(FIXTURES / fixture_name) as handle:
        keyboard.process_keyboard_layout(json.load(handle))
    return keyboard


def section_widths(keyboard):
    widths = []
    for section in keyboard.switch_section_list:
        min_x, max_x, _, _ = section.get_collection_bounds()
        widths.append(round(max_x - min_x, 2))
    return widths


class TestSplitKeyboardEndToEnd:
    def test_wide_board_fits_two_sections_on_large_plate(self):
        keyboard = build_keyboard("wide_board.json", x_build_size=330)
        assert keyboard.get_top_section_count() == 2
        assert section_widths(keyboard) == [16.5, 11.75]

    def test_wide_board_splits_three_ways_on_small_plate(self):
        keyboard = build_keyboard("wide_board.json", x_build_size=200)
        assert keyboard.get_top_section_count() == 3
        # No thin remainder: the three pieces are evenly sized.
        assert section_widths(keyboard) == [9.5, 9.75, 9.75]

    def test_wide_board_balances_and_avoids_sliver_on_medium_plate(self):
        # 300mm plate: 3 sections are required (the wide key can't share section 0
        # and the remainder is too wide for one more), but balancing must spread
        # them evenly instead of leaving the old 11.5 / 15.25 / 2.0u split.
        keyboard = build_keyboard("wide_board.json", x_build_size=300)
        assert keyboard.get_top_section_count() == 3
        widths = section_widths(keyboard)
        # No sliver: the smallest section is a decent fraction of the largest.
        assert min(widths) > 0.6 * max(widths)
