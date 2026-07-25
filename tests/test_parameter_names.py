"""Tests for the unknown parameter check in ``Parameters.build_attr_from_dict``.

Parameters are applied with setattr, so before this check a name the code does
not know about was accepted in silence: the attribute was created, nothing ever
read it, and the model was built from the default instead.
"""
import pytest

from parameters import Parameters


class TestKnownNames:
    def test_a_real_parameter_is_applied(self):
        assert Parameters({'case_height': 25}).case_height == 25

    def test_custom_switch_is_accepted(self):
        parameters = Parameters({'custom_switch': {'points': [[7, 7], [7, -7], [-7, -7], [-7, 7]]}})

        assert parameters.custom_shape == True

    def test_no_parameters_at_all_is_fine(self):
        assert Parameters().case_height == 18

    def test_calculated_attributes_are_not_reported(self):
        # build_attr_from_dict runs a second time here, after __init__ has added
        # the calculated attributes, so the check must not trip over its own work.
        parameters = Parameters({'case_height': 25})
        parameters.set_parameter_dict({'case_height': 30})

        assert parameters.case_height == 30


class TestUnknownNames:
    def test_a_typo_is_rejected(self):
        with pytest.raises(ValueError, match='case_hieght is not a parameter'):
            Parameters({'case_hieght': 18})

    def test_every_unknown_name_is_reported_at_once(self):
        with pytest.raises(ValueError) as error:
            Parameters({'case_hieght': 18, 'kerff': 0.2})

        assert 'case_hieght is not a parameter' in str(error.value)
        assert 'kerff is not a parameter' in str(error.value)

    def test_set_parameter_dict_is_checked_too(self):
        parameters = Parameters()
        with pytest.raises(ValueError, match='not a parameter'):
            parameters.set_parameter_dict({'no_such_parameter': 1})


class TestRenamedNames:
    @pytest.mark.parametrize('old_name, current_name', sorted(Parameters.RENAMED_PARAMETERS.items()))
    def test_an_old_name_points_at_its_replacement(self, old_name, current_name):
        with pytest.raises(ValueError, match='%s was renamed to %s' % (old_name, current_name)):
            Parameters({old_name: 9.0})

    def test_the_replacement_itself_is_accepted(self):
        for current_name in Parameters.RENAMED_PARAMETERS.values():
            assert hasattr(Parameters(), current_name), current_name
