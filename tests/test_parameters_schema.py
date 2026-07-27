"""Checks that parameters.schema.json matches the parameters the code accepts.

The schema sets additionalProperties to false so that a mistyped parameter name
is reported by an editor rather than silently ignored, which means the schema
has to be kept in step with Parameters. TestSchemaCoverage is the guard: add a
new parameter to Parameters and it fails until the schema describes it too.
"""
import json
from pathlib import Path

import json5
import jsonschema
import pytest

from parameters import Parameters

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / 'parameters.schema.json'

# Attributes of Parameters that are not read from the parameter file: state the
# generator fills in as it measures the layout, and values derived from other
# parameters by update_calculated_attributes.
INTERNAL_ATTRIBUTES = {
    'logger', 'parameter_dict', 'switch_config',
    'min_x', 'max_x', 'min_y', 'max_y',
    'real_max_x', 'real_max_y', 'real_case_width', 'real_case_height',
    'case_height_base_removed', 'case_height_extra_fill',
    'side_margin_diff', 'top_margin_diff',
    'screw_tap_hole_diameter', 'screw_hole_body_diameter', 'screw_hole_body_radius',
    'x_screw_width', 'y_screw_width',
    'bottom_section_count', 'screw_hole_body_support_end_x',
}

# Schema properties with no matching attribute: consumed by the loader, or
# handled specially by build_attr_from_dict.
LOADER_PROPERTIES = {Parameters.SCHEMA_KEY, Parameters.INCLUDE_KEY, 'custom_switch'}


@pytest.fixture(scope='module')
def schema():
    return json.loads(SCHEMA_PATH.read_text(encoding='utf-8'))


# Fixtures that describe a broken custom switch on purpose, to exercise the
# errors build_attr_from_dict raises. The schema is meant to reject them.
INVALID_ON_PURPOSE = {
    'parameters_custom_switch_no_points.json',
    'parameters_custom_switch_invalid_points.json',
}


def example_files():
    root_files = [path for path in sorted(REPO_ROOT.glob('parameters*.json')) if path != SCHEMA_PATH]
    test_files = sorted((REPO_ROOT / 'parameter_test_files').glob('*.json'))
    return [path for path in root_files + test_files if path.name not in INVALID_ON_PURPOSE]


class TestSchemaItself:
    def test_schema_is_valid(self, schema):
        jsonschema.Draft202012Validator.check_schema(schema)


class TestSchemaCoverage:
    def test_every_parameter_is_described(self, schema):
        described = set(schema['properties'].keys())
        settable = set(Parameters().__dict__.keys()) - INTERNAL_ATTRIBUTES
        assert settable - described == set(), (
            'these attributes are neither described in parameters.schema.json nor listed in '
            'INTERNAL_ATTRIBUTES. Describe them in the schema if a parameter file may set them, '
            'otherwise add them to INTERNAL_ATTRIBUTES'
        )

    def test_no_property_describes_a_parameter_that_does_not_exist(self, schema):
        described = set(schema['properties'].keys()) - LOADER_PROPERTIES
        known = set(Parameters().__dict__.keys())
        assert described - known == set(), 'parameters.schema.json describes unknown parameters'


class TestExampleFiles:
    @pytest.mark.parametrize('file_path', example_files(), ids=lambda path: path.name)
    def test_example_file_validates(self, schema, file_path):
        jsonschema.validate(json5.loads(Parameters.read_parameter_file(file_path)), schema)

    @pytest.mark.parametrize('name', sorted(INVALID_ON_PURPOSE))
    def test_deliberately_broken_fixture_is_rejected(self, schema, name):
        file_path = REPO_ROOT / 'parameter_test_files' / name
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(json5.loads(Parameters.read_parameter_file(file_path)), schema)


class TestRejectsMistakes:
    def test_unknown_parameter_is_rejected(self, schema):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({'no_such_parameter': 18}, schema)

    def test_commented_out_block_is_not_a_parameter(self, schema):
        # Blocks are disabled by commenting them out, so nothing reaches the
        # schema and there is no need for a disabled-key escape hatch.
        parameter_dict = json5.loads('{\n  /* "custom_switch": {"points": [[7, 7]]}, */\n  "case_height": 18\n}')
        jsonschema.validate(parameter_dict, schema)
        assert parameter_dict == {'case_height': 18}

    def test_invalid_switch_type_is_rejected(self, schema):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({'switch_type': 'no_such_switch_type'}, schema)

    def test_circle_needs_a_radius_or_diameter(self, schema):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({'custom_polygons': [{'type': 'circle', 'coordinates': [[0, 0]]}]}, schema)

    def test_polygon_needs_points(self, schema):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({'custom_polygons': [{'type': 'polygon', 'coordinates': [[0, 0]]}]}, schema)

    def test_include_must_be_a_string_or_list(self, schema):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({'include': {'file': 'base.json'}}, schema)