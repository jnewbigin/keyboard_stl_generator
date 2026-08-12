"""Record the x-axis section split so a later run can reproduce it exactly.

The split is planned from the layout and the build plate size, so an unrelated
change - a wider margin, a taller case, an extra key - can move a seam or
renumber the sections. A section printed from the earlier run would then no
longer mate with its neighbours. Saving the split lets a later run pin the same
boundaries, and refuse to build when they no longer hold, so one section can be
re-printed on its own.

The mating surface between two sections is a polyline, not a straight line: the
seam bulges around straddling keys and zig-zags into interlocking fingers. That
polyline is recorded alongside the boundaries and re-checked on load, which is
what distinguishes a harmless change (a key resized in the middle of a section)
from a fatal one (a key resized where the seam runs).
"""

import itertools
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# One (y_start_mm, y_end_mm, seam_x_mm) band of a seam polyline.
SeamBand = tuple[float, float, float]

# A key's (x, y) origin in key units, which is how a key is named in a section.
KeyOrigin = tuple[float, float]


@dataclass
class SavedSplit:
    footprint_planned: bool
    plate_mm: float
    bottom_section_count: int
    boundaries: list[float]
    section_widths: list[float]
    sections: list[list[KeyOrigin]]
    seams: list[list[SeamBand]]

    def key_sections(self) -> dict[KeyOrigin, int]:
        return {
            origin: section
            for section, origins in enumerate(self.sections)
            for origin in origins
        }


class SplitFileError(Exception):
    """The saved split cannot be applied to the current build."""


class SplitFile:
    VERSION = 1

    # Seam positions round-trip through the file rounded to PLACES, and the
    # coarsest 3D printer resolves far more than a tenth of a micron, so this
    # tolerance separates real movement from float noise.
    TOLERANCE = 1e-4
    PLACES = 6

    @classmethod
    def save(cls, path: Path, split: SavedSplit) -> None:
        document = {
            "version": cls.VERSION,
            "footprint_planned": split.footprint_planned,
            "plate_mm": round(split.plate_mm, cls.PLACES),
            "bottom_section_count": split.bottom_section_count,
            "boundaries_mm": [round(value, cls.PLACES) for value in split.boundaries],
            "section_widths_mm": [
                round(value, cls.PLACES) for value in split.section_widths
            ],
            "sections": [
                {
                    "section": index,
                    "keys": [
                        [cls.round_unit(x), cls.round_unit(y)] for (x, y) in origins
                    ],
                }
                for index, origins in enumerate(split.sections)
            ],
            "seams": [
                {
                    "boundary": index,
                    "profile": [
                        [
                            round(y_start, cls.PLACES),
                            round(y_end, cls.PLACES),
                            round(seam_x, cls.PLACES),
                        ]
                        for (y_start, y_end, seam_x) in profile
                    ],
                }
                for index, profile in enumerate(split.seams)
            ],
        }
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> SavedSplit:
        raw = cls._read_document(path)
        boundaries = cls._boundaries(raw)
        return SavedSplit(
            footprint_planned=cls._footprint_planned(raw),
            plate_mm=cls._plate(raw),
            bottom_section_count=cls._bottom_section_count(raw),
            boundaries=boundaries,
            section_widths=cls._section_widths(raw, len(boundaries)),
            sections=cls._section_list(raw.get("sections"), len(boundaries) + 1),
            seams=cls._seam_list(raw.get("seams"), len(boundaries)),
        )

    @classmethod
    def round_unit(cls, value: float) -> float:
        # Key origins are dictionary keys, so a saved one has to round exactly the
        # same way the live layout does for the lookup to hit.
        return round(value, cls.PLACES)

    @classmethod
    def _read_document(cls, path: Path) -> dict:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except OSError as error:
            raise SplitFileError(f"cannot read split file {path}: {error}") from error
        except (UnicodeDecodeError, ValueError) as error:
            raise SplitFileError(
                f"split file {path} is not valid JSON: {error}"
            ) from error

        if not isinstance(raw, dict):
            raise SplitFileError(f"split file {path} must contain a JSON object")

        version = raw.get("version")
        if version != cls.VERSION:
            raise SplitFileError(
                f"split file {path} has version {version!r}, expected {cls.VERSION}"
            )
        return raw

    @staticmethod
    def _footprint_planned(raw: dict) -> bool:
        value = raw.get("footprint_planned")
        if not isinstance(value, bool):
            raise SplitFileError(
                'split file field "footprint_planned" must be true or false'
            )
        return value

    @classmethod
    def _plate(cls, raw: dict) -> float:
        plate_mm = cls._number(raw.get("plate_mm"), "plate_mm")
        if plate_mm <= 0:
            raise SplitFileError(
                'split file field "plate_mm" must be greater than zero'
            )
        return plate_mm

    @staticmethod
    def _bottom_section_count(raw: dict) -> int:
        value = raw.get("bottom_section_count")
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise SplitFileError(
                'split file field "bottom_section_count" must be a whole number of one or more'
            )
        return value

    @classmethod
    def _boundaries(cls, raw: dict) -> list[float]:
        boundaries = cls._number_list(raw.get("boundaries_mm"), "boundaries_mm")
        for lower, upper in itertools.pairwise(boundaries):
            if upper <= lower:
                raise SplitFileError(
                    'split file field "boundaries_mm" must be in ascending order'
                )
        return boundaries

    @classmethod
    def _section_widths(cls, raw: dict, boundary_count: int) -> list[float]:
        section_widths = cls._number_list(
            raw.get("section_widths_mm"), "section_widths_mm"
        )
        if len(section_widths) != boundary_count + 1:
            raise SplitFileError(
                f"split file lists {boundary_count} boundaries but {len(section_widths)} section "
                f"widths; expected {boundary_count + 1} widths"
            )
        return section_widths

    @staticmethod
    def _number(value: Any, field: str) -> float:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise SplitFileError(
                f'split file field "{field}" must contain finite numbers, got {value!r}'
            )
        return float(value)

    @classmethod
    def _number_list(cls, value: Any, field: str) -> list[float]:
        if not isinstance(value, list):
            raise SplitFileError(
                f'split file field "{field}" must be a list of numbers'
            )
        return [cls._number(entry, field) for entry in value]

    @classmethod
    def _section_list(cls, value: Any, section_count: int) -> list[list[KeyOrigin]]:
        if not isinstance(value, list):
            raise SplitFileError('split file field "sections" must be a list')
        if len(value) != section_count:
            raise SplitFileError(
                f"split file describes {section_count} sections but lists {len(value)}"
            )

        # A key belongs to exactly one section. Without this a duplicate would
        # quietly resolve to whichever section is listed last, so the split that
        # came back would not be the one that was recorded.
        claimed: set[KeyOrigin] = set()

        sections = []
        for index, entry in enumerate(value):
            if not isinstance(entry, dict) or entry.get("section") != index:
                raise SplitFileError(
                    f'split file section {index} must be an object with "section": {index}'
                )
            keys = entry.get("keys")
            if not isinstance(keys, list):
                raise SplitFileError(
                    f'split file section {index} must have a "keys" list'
                )

            origins: list[KeyOrigin] = []
            for key in keys:
                if not isinstance(key, list) or len(key) != 2:
                    raise SplitFileError(
                        f"split file section {index} keys must be [x, y] pairs"
                    )
                origin = (
                    cls.round_unit(cls._number(key[0], f"sections[{index}].keys")),
                    cls.round_unit(cls._number(key[1], f"sections[{index}].keys")),
                )
                if origin in claimed:
                    raise SplitFileError(
                        f"split file claims the key at x = {origin[0]}, y = {origin[1]} "
                        "for more than one section"
                    )
                claimed.add(origin)
                origins.append(origin)
            sections.append(origins)
        return sections

    @classmethod
    def _seam_list(cls, value: Any, boundary_count: int) -> list[list[SeamBand]]:
        if not isinstance(value, list):
            raise SplitFileError('split file field "seams" must be a list')
        if len(value) != boundary_count:
            raise SplitFileError(
                f"split file lists {boundary_count} boundaries but {len(value)} seams"
            )

        seams = []
        for index, entry in enumerate(value):
            if not isinstance(entry, dict) or entry.get("boundary") != index:
                raise SplitFileError(
                    f'split file seam {index} must be an object with "boundary": {index}'
                )
            profile_raw = entry.get("profile")
            if not isinstance(profile_raw, list) or not profile_raw:
                raise SplitFileError(
                    f'split file seam {index} must have a non-empty "profile" list'
                )

            profile: list[SeamBand] = []
            for band in profile_raw:
                if not isinstance(band, list) or len(band) != 3:
                    raise SplitFileError(
                        f"split file seam {index} profile bands must be [y_start, y_end, x]"
                    )
                y_start, y_end, seam_x = (
                    cls._number(number, f"seams[{index}].profile") for number in band
                )
                if y_end <= y_start:
                    raise SplitFileError(
                        f"split file seam {index} has a band that does not advance in y"
                    )
                if profile and y_start < profile[-1][1] - cls.TOLERANCE:
                    raise SplitFileError(
                        f"split file seam {index} profile bands must be in ascending y order"
                    )
                profile.append((y_start, y_end, seam_x))
            seams.append(profile)
        return seams

    @classmethod
    def seam_mismatch(
        cls, recorded: list[SeamBand], current: list[SeamBand]
    ) -> str | None:
        # Describe the first place the two mating surfaces disagree, or None when
        # they match. Only the y range both cover is compared: a board that grew
        # or shrank in y extends or trims the seam without disturbing the surface
        # an already printed section was cut against.
        if not recorded or not current:
            return "the seam is missing on one side"

        low = max(recorded[0][0], current[0][0])
        high = min(recorded[-1][1], current[-1][1])
        if high - low < cls.TOLERANCE:
            return "the board no longer covers the y range the seam was cut over"

        return cls._first_difference(recorded, current, low, high)

    @classmethod
    def _first_difference(
        cls, recorded: list[SeamBand], current: list[SeamBand], low: float, high: float
    ) -> str | None:
        for lower, upper in itertools.pairwise(
            cls._break_points((recorded, current), low, high)
        ):
            if upper - lower < cls.TOLERANCE:
                continue
            mid = (lower + upper) / 2.0
            was = cls._seam_x_at(recorded, mid)
            now = cls._seam_x_at(current, mid)
            if was is None or now is None:
                return f"the seam is no longer continuous at y = {mid:.3f} mm"
            if abs(was - now) > cls.TOLERANCE:
                return f"at y = {mid:.3f} mm it ran at x = {was:.3f} mm and now runs at x = {now:.3f} mm"
        return None

    @staticmethod
    def _break_points(
        profiles: tuple[list[SeamBand], ...], low: float, high: float
    ) -> list[float]:
        # Every y either profile changes at, so each interval between them has a
        # single seam x on both sides and can be compared with one lookup.
        breaks = {low, high}
        for profile in profiles:
            for y_start, y_end, _seam_x in profile:
                for edge in (y_start, y_end):
                    if low < edge < high:
                        breaks.add(edge)
        return sorted(breaks)

    @staticmethod
    def _seam_x_at(profile: list[SeamBand], y: float) -> float | None:
        for y_start, y_end, seam_x in profile:
            if y_start <= y <= y_end:
                return seam_x
        return None
