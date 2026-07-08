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


class TestAssignXSections:
    def test_narrow_board_is_one_section(self):
        # Five 1u keys span 5u (95.25mm); well under a 330mm plate.
        cols = columns((0, [1]), (1, [1]), (2, [1]), (3, [1]), (4, [1]))
        assignments = Keyboard._assign_x_sections(cols, x_build_size=330, left_margin=10)
        assert section_count(assignments) == 1

    def test_board_wider_than_plate_splits(self):
        # ~21u board on a 200mm (~10u) plate must use more than one section.
        cols = columns(*[(i, [1]) for i in range(21)])
        assignments = Keyboard._assign_x_sections(cols, x_build_size=200, left_margin=10)
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
        assignments = Keyboard._assign_x_sections(cols, x_build_size=330, left_margin=10)
        assert section_count(assignments) == 2

    def test_boundary_edge_does_not_spawn_empty_section(self):
        # Two keys in one column whose right edge lands exactly on the plate width
        # must share a single new section rather than each appending one. This is
        # the structural fix over the old append-in-else loop.
        exactly_one_plate = 5 * SPACING
        cols = [
            (0.0, [SPACING]),                                   # fits section 0
            (SPACING, [exactly_one_plate, exactly_one_plate]),  # both == plate width
        ]
        assignments = Keyboard._assign_x_sections(
            cols, x_build_size=exactly_one_plate, left_margin=0)
        # No phantom section, and both boundary keys share one index.
        assert section_count(assignments) == 2
        assert assignments[1] == [1, 1]

    def test_left_margin_reserves_wall_space(self):
        # A key ending at 195mm fits a 200mm plate with no margin, but not once a
        # 10mm wall is reserved (195 + 10 > 200), forcing a new section. A first
        # key that comfortably fits keeps section 0 populated in both cases.
        cols = [(0.0, [50.0]), (100.0, [195.0])]
        no_margin = Keyboard._assign_x_sections(cols, x_build_size=200, left_margin=0)
        with_margin = Keyboard._assign_x_sections(cols, x_build_size=200, left_margin=10)
        assert section_count(no_margin) == 1
        assert section_count(with_margin) == 2

    def test_empty_board(self):
        assert Keyboard._assign_x_sections([], x_build_size=330, left_margin=10) == []


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
