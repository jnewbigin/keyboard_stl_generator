"""Tests for the parameter type check in ``Parameters.build_attr_from_dict``.

Parameters are applied with setattr, so before this check the value was taken
at face value whatever its type. A quoted "false" is the case that bites: every
feature gate is a truth test, and a non-empty string passes one, so a parameter
file meant to turn something off turned it on instead.
"""
import pytest

from parameters import Parameters


class TestBooleanParameters:
    def test_a_real_boolean_is_applied(self):
        assert Parameters({'cable_hole': True}).cable_hole is True

    def test_quoted_false_is_rejected(self):
        with pytest.raises(ValueError, match="cable_hole: 'false' is not of type 'boolean'"):
            Parameters({'cable_hole': 'false'})

    def test_quoted_true_is_rejected(self):
        with pytest.raises(ValueError, match='cable_hole'):
            Parameters({'cable_hole': 'true'})

    def test_a_number_is_not_a_boolean(self):
        with pytest.raises(ValueError, match='plate_supports'):
            Parameters({'plate_supports': 1})

    def test_nullable_boolean_accepts_null(self):
        assert Parameters({'custom_pcb': None}).custom_pcb is None

    def test_nullable_boolean_rejects_a_string(self):
        with pytest.raises(ValueError, match="custom_pcb: 'false' is not of type 'boolean', 'null'"):
            Parameters({'custom_pcb': 'false'})


class TestNumericParameters:
    def test_a_quoted_number_is_rejected(self):
        with pytest.raises(ValueError, match='screw_count'):
            Parameters({'screw_count': '4'})

    def test_a_fractional_screw_count_is_rejected(self):
        with pytest.raises(ValueError, match='screw_count'):
            Parameters({'screw_count': 4.5})

    def test_a_value_below_the_minimum_is_rejected(self):
        with pytest.raises(ValueError, match='x_build_size'):
            Parameters({'x_build_size': -5})


class TestReporting:
    def test_every_bad_parameter_is_reported_at_once(self):
        with pytest.raises(ValueError) as error:
            Parameters({'cable_hole': 'false', 'screw_count': '4'})

        assert 'cable_hole' in str(error.value)
        assert 'screw_count' in str(error.value)

    def test_an_unknown_name_is_still_reported_by_name(self):
        # The name check runs first, so a typo is named as such rather than
        # being reported as failing the schema.
        with pytest.raises(ValueError, match='not a parameter'):
            Parameters({'cable_holl': True})
