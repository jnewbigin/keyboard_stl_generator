"""Tests for saving the section split and reusing it on a later run.

The point of the file is that one section can be re-printed after the build is
tweaked: the same split has to come back, or the build has to stop. So these
tests come in pairs - a change that leaves the mating surfaces alone must be
accepted, and one that disturbs them must be refused.
"""

# pylint: disable=protected-access
import copy
import itertools
import json
from dataclasses import replace
from pathlib import Path

import pytest

from keyboard import Keyboard
from parameters import Parameters
from split_file import SplitFile, SplitFileError

SPACING = 19.05  # default switch_spacing (mm per key unit)
FIXTURES = Path(__file__).parent / "fixtures"
BOARD_KEYS = 28  # 28u is wide enough to need three 200mm sections


def board(resize_index=None, width=None, height=None):
    """A two row, 28u board, optionally resizing one key in the second row."""
    rows = [[""] * BOARD_KEYS, []]
    for index in range(BOARD_KEYS):
        if index == resize_index:
            modifiers = {}
            if width is not None:
                modifiers["w"] = width
            if height is not None:
                modifiers["h"] = height
            rows[1].append(modifiers)
        rows[1].append("")
    return rows


def build(layout, split=None, x_build_size=200, **overrides):
    parameters = Parameters(
        {"x_build_size": x_build_size, "y_build_size": 300, **overrides}
    )
    keyboard = Keyboard(parameters)
    if split is not None:
        keyboard.load_split(split)
    keyboard.process_keyboard_layout(layout)
    return keyboard


def fixture_layout(name):
    with open(FIXTURES / name, encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(name="saved")
def saved_fixture():
    """The split of a plain 28u board on a 200mm plate."""
    return build(board()).current_split()


def flat_seams(seams):
    """Flatten seam profiles so they can go through pytest.approx."""
    return [value for profile in seams for band in profile for value in band]


def keys_in_section(keyboard, section):
    return sorted(
        (item.x, item.y)
        for item in keyboard._iter_collection_items(
            keyboard.switch_section_list[section]
        )
    )


def key_index_in_section(keyboard, section):
    """A key index in the middle of the given section, for a one key per column board."""
    boundaries = [0.0, *keyboard._section_x_boundaries(), BOARD_KEYS * SPACING]
    middle = (boundaries[section] + boundaries[section + 1]) / 2.0
    return int(middle // SPACING)


class TestSaveAndReuse:
    def test_saved_split_is_reused_instead_of_replanned(self, saved, tmp_path):
        # A 300mm plate would be planned as fewer sections; the saved split must
        # win, so the sections already printed off the 200mm plan still line up.
        path = tmp_path / "split.json"
        SplitFile.save(path, saved)

        replanned = build(board(), x_build_size=300)
        reused = build(board(), split=SplitFile.load(path), x_build_size=300)

        assert replanned.get_top_section_count() < len(saved.boundaries) + 1
        assert reused.get_top_section_count() == len(saved.boundaries) + 1
        assert reused._section_x_boundaries() == pytest.approx(saved.boundaries)
        assert flat_seams(reused.seam_profiles()) == pytest.approx(
            flat_seams(saved.seams)
        )

    def test_round_trip_through_the_file_is_lossless(self, saved, tmp_path):
        path = tmp_path / "split.json"
        SplitFile.save(path, saved)
        loaded = SplitFile.load(path)
        assert loaded.footprint_planned == saved.footprint_planned
        assert loaded.boundaries == pytest.approx(saved.boundaries)
        assert loaded.section_widths == pytest.approx(saved.section_widths)
        assert flat_seams(loaded.seams) == pytest.approx(flat_seams(saved.seams))
        assert loaded.plate_mm == pytest.approx(saved.plate_mm)

    def test_reused_split_puts_every_key_back_in_the_same_section(self, saved):
        planned = build(board())
        reused = build(board(), split=saved)
        for planned_section, reused_section in zip(
            planned.switch_section_list, reused.switch_section_list
        ):
            assert (
                planned_section.get_collection_bounds()
                == reused_section.get_collection_bounds()
            )

    def test_staggered_board_reloads_its_own_split(self):
        # A staggered row leaves keys on the far side of the straight boundary
        # from the section they were planned into, so the split cannot be rebuilt
        # from the boundaries alone - it has to remember where each key went.
        layout = fixture_layout("wide_board.json")
        planned = build(layout)
        saved = planned.current_split()

        reused = build(layout, split=saved)
        for section in range(planned.get_top_section_count()):
            reused_keys = keys_in_section(reused, section)
            assert reused_keys == keys_in_section(planned, section)
            assert reused_keys  # a section that lost all its keys would pass the line above


class TestChangesAwayFromASeam:
    def test_taller_key_inside_a_section_is_accepted(self, saved):
        # A taller key adds row edges, so the seam is swept in more bands than it
        # was saved with. The mating surface itself has not moved, so the merged
        # profile still matches and the split is reusable.
        planned = build(board())
        index = key_index_in_section(planned, 0)
        reused = build(board(resize_index=index, height=1.5), split=saved)
        assert reused._section_x_boundaries() == pytest.approx(saved.boundaries)

    def test_wider_key_in_the_last_section_is_accepted(self, saved):
        # Widening a key shifts everything to its right, but in the last section
        # nothing to the right of it touches a seam.
        planned = build(board())
        index = key_index_in_section(planned, planned.get_top_section_count() - 1)
        reused = build(board(resize_index=index, width=1.5), split=saved)
        assert reused._section_x_boundaries() == pytest.approx(saved.boundaries)

    def test_unrelated_parameter_change_is_accepted(self, saved):
        reused = build(board(), split=saved, case_height=30, plate_thickness=3.0)
        assert reused._section_x_boundaries() == pytest.approx(saved.boundaries)


class TestChangesThatMoveASeam:
    def test_wider_key_before_a_seam_is_rejected(self, saved):
        # The same edit as the accepted case, but in the first section: every key
        # to its right shifts, including the ones the seam is cut around.
        planned = build(board())
        index = key_index_in_section(planned, 0)
        with pytest.raises(
            SplitFileError, match="seam between sections 0 and 1 has moved"
        ):
            build(board(resize_index=index, width=1.5), split=saved)

    def test_changed_finger_size_is_rejected(self, saved):
        # The interlocking fingers are part of the mating surface: re-cut with a
        # different tooth and the new section will not mesh with the old print.
        with pytest.raises(SplitFileError, match="has moved"):
            build(board(), split=saved, section_finger_depth=7.0)

    def test_changed_switch_spacing_is_rejected(self, saved):
        with pytest.raises(SplitFileError, match="has moved"):
            build(board(), split=saved, switch_spacing=20.0)


class TestSplitNoLongerPossible:
    def test_section_that_outgrew_the_plate_is_rejected(self, saved):
        with pytest.raises(
            SplitFileError, match=r"no longer fits the 120\.0 mm build plate"
        ):
            build(board(), split=saved, x_build_size=120)

    def test_section_already_oversize_when_saved_stays_a_warning(self):
        # A board that could not be split to fit in the first place must stay
        # reusable, or its own file could never be loaded again. Same split, but
        # recorded against a plate its sections never fitted.
        saved = build(board(), x_build_size=200).current_split()
        already_oversize = replace(saved, plate_mm=120)
        assert (
            max(saved.section_widths) > 120
        )  # the sections really are too wide for it

        reused = build(board(), split=already_oversize, x_build_size=120)
        assert reused._section_x_boundaries() == pytest.approx(saved.boundaries)

    def test_board_too_small_for_the_saved_sections_is_rejected(self, saved):
        short_board = [[""] * 6, [""] * 6]
        with pytest.raises(SplitFileError, match="holds no keys on this board"):
            build(short_board, split=saved)

    def test_split_saved_for_the_other_kind_of_board_is_rejected(self, saved):
        with pytest.raises(
            SplitFileError, match="planned for a board with no rotated clusters"
        ):
            build(fixture_layout("rotated_cluster.json"), split=saved)

    def test_section_the_record_leaves_empty_is_rejected(self, saved):
        # The recorded assignment decides what a section holds, so emptiness has
        # to be read from the restored collections. Checking which keys fall
        # between the boundaries instead would call this split populated.
        everything = [origin for section in saved.sections for origin in section]
        forged = replace(
            saved, sections=[[] for _ in saved.sections[:-1]] + [everything]
        )
        with pytest.raises(SplitFileError, match=r"section 0 .* holds no keys"):
            build(board(), split=forged)


class TestRotatedBoard:
    def test_rotated_split_is_recorded_and_reused(self):
        layout = fixture_layout("rotated_cluster.json")
        planned = build(layout, x_build_size=200)
        saved = planned.current_split()
        assert saved.footprint_planned

        reused = build(layout, split=saved, x_build_size=200)
        # The bottom cover follows the plate seams on a footprint planned board;
        # restoring the mode keeps it splitting the same way.
        assert reused.planned_boundaries == pytest.approx(planned.planned_boundaries)
        assert reused.get_bottom_section_count() == planned.get_bottom_section_count()
        assert reused.get_top_section_count() == planned.get_top_section_count()
        assert reused.split_recommendation is not None

    def test_cluster_moved_across_a_saved_cut_is_rejected(self):
        # Rotated keys never join a section collection, so the seam comparison
        # cannot see a cluster that has moved. Without a clearance check of its
        # own the restore is accepted and the clip saws through the cluster.
        layout = fixture_layout("rotated_cluster.json")
        saved = build(layout, x_build_size=200).current_split()

        moved = copy.deepcopy(layout)
        for row in moved:
            for cell in row:
                if isinstance(cell, dict) and "rx" in cell:
                    cell["rx"] = 6

        spans = build(moved, x_build_size=200)._rotated_cluster_spans()
        assert any(
            low <= cut <= high for cut in saved.boundaries for low, high in spans
        ), "the fixture edit must actually move a cluster onto a saved cut"

        with pytest.raises(SplitFileError, match="falls inside a rotated cluster"):
            build(moved, split=saved, x_build_size=200)

    def test_plain_split_does_not_borrow_the_rotated_bottom_split(self, saved):
        # A plain board's bottom cover is an even division of the case, not a
        # copy of the plate seams, so restoring one must not switch modes.
        reused = build(board(), split=saved)
        assert reused.planned_boundaries is None
        assert reused.get_bottom_section_count() == saved.bottom_section_count

    def test_bottom_cover_keeps_its_piece_count_on_a_bigger_plate(self, saved):
        # The bottom count is worked out from the plate, so without pinning it a
        # roomier printer would quietly hand back fewer, larger bottom pieces.
        assert (
            build(board(), x_build_size=400).get_bottom_section_count()
            < saved.bottom_section_count
        )
        assert (
            build(board(), split=saved, x_build_size=400).get_bottom_section_count()
            == saved.bottom_section_count
        )

    def test_bottom_pieces_are_sized_for_the_pinned_count(self, saved):
        # Sizing each piece off the parameter rather than the pinned count would
        # cut the cover into 400mm-plate sized slabs and then emit one per
        # 200mm-plate section, so the pieces would overlap and the last be empty.
        reused = build(board(), split=saved, x_build_size=400)
        (min_x, max_x, max_y, min_y) = reused.switch_collection.get_collection_bounds()
        reused.parameters.set_dimensions(max_x, min_y, min_x, max_y)
        spans = [
            reused.get_bottom_section_span(section)
            for section in range(reused.get_bottom_section_count())
        ]

        assert reused.parameters.real_case_width > 0
        assert spans[0][0] == pytest.approx(0.0)
        assert spans[-1][1] == pytest.approx(reused.parameters.real_case_width)
        for (_start, end), (next_start, _next_end) in itertools.pairwise(spans):
            assert end == pytest.approx(next_start)


class TestFileValidation:
    def write(self, tmp_path, document):
        path = tmp_path / "split.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def valid(self, tmp_path):
        path = tmp_path / "split.json"
        SplitFile.save(path, build(board()).current_split())
        return json.loads(path.read_text(encoding="utf-8"))

    def test_missing_file(self, tmp_path):
        with pytest.raises(SplitFileError, match="cannot read split file"):
            SplitFile.load(tmp_path / "absent.json")

    def test_not_json(self, tmp_path):
        path = tmp_path / "split.json"
        path.write_text("not json at all", encoding="utf-8")
        with pytest.raises(SplitFileError, match="not valid JSON"):
            SplitFile.load(path)

    def test_wrong_version(self, tmp_path):
        document = self.valid(tmp_path)
        document["version"] = 99
        with pytest.raises(SplitFileError, match="version 99"):
            SplitFile.load(self.write(tmp_path, document))

    def test_boundaries_must_ascend(self, tmp_path):
        document = self.valid(tmp_path)
        document["boundaries_mm"] = list(reversed(document["boundaries_mm"]))
        with pytest.raises(SplitFileError, match="ascending order"):
            SplitFile.load(self.write(tmp_path, document))

    def test_non_finite_boundary(self, tmp_path):
        # json.loads accepts NaN and Infinity, which would poison every later
        # comparison, so they are rejected the same way parameter files do.
        document = self.valid(tmp_path)
        path = tmp_path / "split.json"
        path.write_text(
            json.dumps(document).replace(str(document["boundaries_mm"][0]), "NaN"),
            encoding="utf-8",
        )
        with pytest.raises(SplitFileError, match="finite numbers"):
            SplitFile.load(path)

    def test_seam_count_must_match_boundary_count(self, tmp_path):
        document = self.valid(tmp_path)
        document["seams"] = document["seams"][:-1]
        with pytest.raises(SplitFileError, match="seams"):
            SplitFile.load(self.write(tmp_path, document))

    def test_width_count_must_match_boundary_count(self, tmp_path):
        document = self.valid(tmp_path)
        document["section_widths_mm"] = document["section_widths_mm"][:-1]
        with pytest.raises(SplitFileError, match="section widths"):
            SplitFile.load(self.write(tmp_path, document))

    def test_duplicate_key_origin(self, tmp_path):
        # Silently resolving a duplicate to the last section listed would hand
        # back a different split from the one recorded.
        document = self.valid(tmp_path)
        document["sections"][0]["keys"].append(document["sections"][1]["keys"][0])
        with pytest.raises(SplitFileError, match="for more than one section"):
            SplitFile.load(self.write(tmp_path, document))

    def test_malformed_profile_band(self, tmp_path):
        document = self.valid(tmp_path)
        document["seams"][0]["profile"][0] = [1.0, 2.0]
        with pytest.raises(SplitFileError, match=r"\[y_start, y_end, x\]"):
            SplitFile.load(self.write(tmp_path, document))


class TestSeamComparison:
    def test_identical_profiles_match(self):
        profile = [(0.0, 10.0, 5.0), (10.0, 20.0, 7.0)]
        assert SplitFile.seam_mismatch(profile, list(profile)) is None

    def test_extended_y_range_matches_over_the_overlap(self):
        # The board grew in y elsewhere, so the seam runs further than it did.
        # Where the printed section was cut, the surface is untouched.
        recorded = [(0.0, 10.0, 5.0)]
        current = [(-5.0, 10.0, 5.0), (10.0, 15.0, 6.0)]
        assert SplitFile.seam_mismatch(recorded, current) is None

    def test_split_band_with_the_same_x_matches(self):
        recorded = [(0.0, 20.0, 5.0)]
        current = [(0.0, 8.0, 5.0), (8.0, 20.0, 5.0)]
        assert SplitFile.seam_mismatch(recorded, current) is None

    def test_moved_seam_is_reported_with_its_position(self):
        recorded = [(0.0, 20.0, 5.0)]
        current = [(0.0, 8.0, 5.0), (8.0, 20.0, 9.0)]
        message = SplitFile.seam_mismatch(recorded, current)
        assert message is not None
        assert "x = 5.000 mm and now runs at x = 9.000 mm" in message

    def test_no_overlap_is_reported(self):
        assert (
            SplitFile.seam_mismatch([(0.0, 10.0, 5.0)], [(20.0, 30.0, 5.0)]) is not None
        )
