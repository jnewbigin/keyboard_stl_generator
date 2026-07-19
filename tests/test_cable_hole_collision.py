"""Tests for ``Body.screw_clashes_with_cable_hole``.

The cable hole is cut through the back (top) wall, so it can only clash with
top-edge screws. A screw at normalised grid x sits at real x
``x + screw_edge_x_inset`` once the assembly is placed, while the cable hole is
centred at ``left_margin + real_max_x / 2`` - the two coincide only when the
side margins are symmetric, which is exactly what the old exact-midpoint check
got wrong.
"""
from parameters import Parameters
from body import Body


def make_body(**overrides):
    """Build a Body with fixed real dimensions so the screw grid is known.

    real_max_x is pinned to 300mm and real_max_y to 200mm; margins/screw/cable
    settings can be overridden per test.
    """
    params = dict(
        left_margin=10, right_margin=10, top_margin=10, bottom_margin=10,
        cable_hole=True, cable_hole_width=11,
        screw_diameter=4, screw_hole_body_wall_width=2, screw_edge_inset=7,
    )
    params.update(overrides)
    parameters = Parameters(params)
    parameters.real_max_x = 300.0
    parameters.real_max_y = 200.0
    parameters.real_case_width = parameters.real_max_x + parameters.left_margin + parameters.right_margin
    parameters.real_case_height = parameters.real_max_y + parameters.top_margin + parameters.bottom_margin
    parameters.update_calculated_attributes()
    return Body(parameters)


class TestSymmetricMargins:
    def test_center_top_screw_clashes(self):
        body = make_body()
        # With symmetric margins the grid centre lands on the cable hole centre.
        assert body.screw_clashes_with_cable_hole(body.x_screw_width / 2, body.y_screw_width)

    def test_screw_just_inside_clearance_clashes(self):
        body = make_body()
        # clearance = cable_hole_width/2 + body_radius = 5.5 + 4 = 9.5; centre real
        # x is 160, so a screw at real x 169 (diff 9) still clashes.
        assert body.screw_clashes_with_cable_hole(169 - body.screw_edge_x_inset, body.y_screw_width)

    def test_screw_just_outside_clearance_is_kept(self):
        body = make_body()
        # real x 170 is 10mm from the centre, past the 9.5mm clearance.
        assert not body.screw_clashes_with_cable_hole(170 - body.screw_edge_x_inset, body.y_screw_width)

    def test_corner_screw_is_kept(self):
        body = make_body()
        assert not body.screw_clashes_with_cable_hole(0, body.y_screw_width)
        assert not body.screw_clashes_with_cable_hole(body.x_screw_width, body.y_screw_width)

    def test_non_top_screw_is_kept(self):
        body = make_body()
        # A bottom-row screw directly below the cable hole must not be dropped.
        assert not body.screw_clashes_with_cable_hole(body.x_screw_width / 2, 0)

    def test_side_screw_is_kept(self):
        body = make_body()
        assert not body.screw_clashes_with_cable_hole(body.x_screw_width / 2, body.y_screw_width / 2)


class TestCableHoleDisabled:
    def test_nothing_clashes_without_a_cable_hole(self):
        body = make_body(cable_hole=False)
        assert not body.screw_clashes_with_cable_hole(body.x_screw_width / 2, body.y_screw_width)


class TestAsymmetricMargins:
    # left=5, right=25 shifts the cable hole 10mm off the grid centre - more than
    # the 9.5mm clearance - so the geometric-centre screw and the screw over the
    # cable hole are two different screws.
    def test_grid_center_screw_no_longer_clashes(self):
        body = make_body(left_margin=5, right_margin=25)
        # The old check skipped this screw unconditionally; it is now safely kept.
        assert not body.screw_clashes_with_cable_hole(body.x_screw_width / 2, body.y_screw_width)

    def test_screw_over_the_cable_hole_clashes(self):
        body = make_body(left_margin=5, right_margin=25)
        # A screw sitting on the actual cable hole centre must be dropped.
        over_hole = body.cable_hole_center_x() - body.screw_edge_x_inset
        assert body.screw_clashes_with_cable_hole(over_hole, body.y_screw_width)


class TestWideCableHole:
    def test_multiple_adjacent_screws_are_dropped(self):
        # A 40mm hole (clearance = 20 + 4 = 24mm) spans several top screws; the
        # old exact-midpoint check could only ever drop one.
        body = make_body(cable_hole_width=40)
        center = body.cable_hole_center_x() - body.screw_edge_x_inset
        clashing = [
            x for x in (center - 20, center - 10, center, center + 10, center + 20)
            if body.screw_clashes_with_cable_hole(x, body.y_screw_width)
        ]
        assert len(clashing) == 5
