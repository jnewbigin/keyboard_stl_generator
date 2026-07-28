"""Tests for ``Parameters.load_parameter_files`` and the ``include`` key.

Merging is shallow and later always wins: within a file the includes are merged
in list order and are then overridden by the file's own keys, and across the
command line the files are merged in argument order.
"""

import json

import pytest

from parameters import Parameters


def write(tmp_path, name, contents):
    file_path = tmp_path / name
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(contents), encoding="utf-8")
    return file_path


class TestSingleFile:
    def test_file_without_includes_is_unchanged(self, tmp_path):
        file_path = write(tmp_path, "parameters.json", {"case_height": 18})
        assert Parameters.load_parameter_files([file_path]) == {"case_height": 18}

    def test_include_key_is_not_a_parameter(self, tmp_path):
        write(tmp_path, "base.json", {"case_height": 10})
        file_path = write(tmp_path, "parameters.json", {"include": ["base.json"]})
        assert Parameters.load_parameter_files([file_path]) == {"case_height": 10}

    def test_schema_key_is_not_a_parameter(self, tmp_path):
        file_path = write(
            tmp_path,
            "parameters.json",
            {"$schema": "./parameters.schema.json", "case_height": 18},
        )
        assert Parameters.load_parameter_files([file_path]) == {"case_height": 18}

    def test_json5_comments_and_trailing_commas_are_allowed(self, tmp_path):
        file_path = tmp_path / "parameters.json"
        file_path.write_text(
            '{\n  // a comment\n  "case_height": 18,\n}', encoding="utf-8"
        )
        assert Parameters.load_parameter_files([file_path]) == {"case_height": 18}

    def test_missing_file_names_the_file(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="missing.json"):
            Parameters.load_parameter_files([tmp_path / "missing.json"])

    def test_unparseable_file_names_the_file(self, tmp_path):
        file_path = tmp_path / "parameters.json"
        file_path.write_text("{ this is not json", encoding="utf-8")
        with pytest.raises(ValueError, match="parameters.json"):
            Parameters.load_parameter_files([file_path])

    def test_non_object_file_is_rejected(self, tmp_path):
        file_path = write(tmp_path, "parameters.json", [1, 2, 3])
        with pytest.raises(TypeError, match="must contain a JSON object"):
            Parameters.load_parameter_files([file_path])


class TestIncludeOrder:
    def test_includes_are_merged_in_list_order(self, tmp_path):
        write(tmp_path, "first.json", {"case_height": 10, "kerf": 0.1})
        write(tmp_path, "second.json", {"case_height": 20})
        file_path = write(
            tmp_path, "parameters.json", {"include": ["first.json", "second.json"]}
        )

        assert Parameters.load_parameter_files([file_path]) == {
            "case_height": 20,
            "kerf": 0.1,
        }

    def test_reversing_the_list_reverses_the_winner(self, tmp_path):
        write(tmp_path, "first.json", {"case_height": 10})
        write(tmp_path, "second.json", {"case_height": 20})
        file_path = write(
            tmp_path, "parameters.json", {"include": ["second.json", "first.json"]}
        )

        assert Parameters.load_parameter_files([file_path]) == {"case_height": 10}

    def test_own_keys_override_includes(self, tmp_path):
        write(tmp_path, "base.json", {"case_height": 10, "kerf": 0.1})
        file_path = write(
            tmp_path, "parameters.json", {"include": ["base.json"], "case_height": 18}
        )

        assert Parameters.load_parameter_files([file_path]) == {
            "case_height": 18,
            "kerf": 0.1,
        }

    def test_own_keys_win_even_when_written_above_the_include(self, tmp_path):
        # The position of the "include" key within the file is irrelevant; a
        # file always overrides what it includes.
        write(tmp_path, "base.json", {"case_height": 10})
        file_path = tmp_path / "parameters.json"
        file_path.write_text(
            '{"case_height": 18, "include": ["base.json"]}', encoding="utf-8"
        )

        assert Parameters.load_parameter_files([file_path]) == {"case_height": 18}

    def test_string_include_is_treated_as_a_single_file(self, tmp_path):
        write(tmp_path, "base.json", {"case_height": 10})
        file_path = write(tmp_path, "parameters.json", {"include": "base.json"})

        assert Parameters.load_parameter_files([file_path]) == {"case_height": 10}

    def test_nested_values_are_replaced_not_merged(self, tmp_path):
        write(
            tmp_path, "base.json", {"custom_switch": {"points": [[7, 7]], "path": [0]}}
        )
        file_path = write(
            tmp_path,
            "parameters.json",
            {"include": ["base.json"], "custom_switch": {"points": [[8, 8]]}},
        )

        assert Parameters.load_parameter_files([file_path]) == {
            "custom_switch": {"points": [[8, 8]]}
        }

    def test_include_must_be_a_string_or_list_of_strings(self, tmp_path):
        file_path = write(
            tmp_path, "parameters.json", {"include": {"file": "base.json"}}
        )
        with pytest.raises(TypeError, match="file name"):
            Parameters.load_parameter_files([file_path])

    def test_empty_include_name_is_rejected(self, tmp_path):
        file_path = write(tmp_path, "parameters.json", {"include": [""]})
        with pytest.raises(ValueError, match="empty file name"):
            Parameters.load_parameter_files([file_path])


class TestRejectsBadArguments:
    def test_a_single_path_is_not_mistaken_for_a_list(self, tmp_path):
        # str is a Sequence[str], so without a guard this would iterate the
        # characters of the path and report that "/" does not exist.
        file_path = write(tmp_path, "parameters.json", {"case_height": 18})

        for argument in [str(file_path), file_path]:
            with pytest.raises(TypeError, match="takes a list of parameter files"):
                Parameters.load_parameter_files(argument)

    def test_directory_is_reported_as_a_directory(self, tmp_path):
        (tmp_path / "base").mkdir()
        file_path = write(tmp_path, "parameters.json", {"include": ["base"]})

        with pytest.raises(
            IsADirectoryError, match="is a directory, not a parameter file"
        ):
            Parameters.load_parameter_files([file_path])

    def test_unexpected_extension_is_rejected(self, tmp_path):
        write(tmp_path, "base.txt", {"case_height": 10})
        file_path = write(tmp_path, "parameters.json", {"include": ["base.txt"]})

        with pytest.raises(ValueError, match="must be named .json or .json5"):
            Parameters.load_parameter_files([file_path])

    def test_json5_extension_is_accepted(self, tmp_path):
        write(tmp_path, "base.json5", {"case_height": 10})
        file_path = write(tmp_path, "parameters.json", {"include": ["base.json5"]})

        assert Parameters.load_parameter_files([file_path]) == {"case_height": 10}


class TestNestedIncludes:
    def test_includes_are_resolved_depth_first(self, tmp_path):
        write(tmp_path, "printer.json", {"x_build_size": 150, "kerf": 0.1})
        write(
            tmp_path,
            "base.json",
            {"include": ["printer.json"], "kerf": 0.2, "case_height": 10},
        )
        file_path = write(
            tmp_path, "parameters.json", {"include": ["base.json"], "case_height": 18}
        )

        assert Parameters.load_parameter_files([file_path]) == {
            "x_build_size": 150,
            "kerf": 0.2,
            "case_height": 18,
        }

    def test_include_paths_are_relative_to_the_including_file(self, tmp_path):
        write(tmp_path, "shared/printer.json", {"x_build_size": 150})
        write(
            tmp_path,
            "shared/base.json",
            {"include": ["printer.json"], "case_height": 10},
        )
        file_path = write(
            tmp_path, "boards/parameters.json", {"include": ["../shared/base.json"]}
        )

        assert Parameters.load_parameter_files([file_path]) == {
            "x_build_size": 150,
            "case_height": 10,
        }

    def test_absolute_include_path_is_used_as_given(self, tmp_path):
        base_path = write(tmp_path, "shared/base.json", {"case_height": 10})
        file_path = write(
            tmp_path, "boards/parameters.json", {"include": [str(base_path)]}
        )

        assert Parameters.load_parameter_files([file_path]) == {"case_height": 10}

    def test_diamond_include_is_allowed(self, tmp_path):
        write(tmp_path, "printer.json", {"x_build_size": 150})
        write(tmp_path, "left.json", {"include": ["printer.json"], "case_height": 10})
        write(tmp_path, "right.json", {"include": ["printer.json"], "kerf": 0.2})
        file_path = write(
            tmp_path, "parameters.json", {"include": ["left.json", "right.json"]}
        )

        assert Parameters.load_parameter_files([file_path]) == {
            "x_build_size": 150,
            "case_height": 10,
            "kerf": 0.2,
        }

    def test_missing_include_names_the_including_file(self, tmp_path):
        file_path = write(tmp_path, "parameters.json", {"include": ["missing.json"]})
        with pytest.raises(FileNotFoundError, match="included from .*parameters.json"):
            Parameters.load_parameter_files([file_path])

    def test_self_include_is_a_cycle(self, tmp_path):
        file_path = write(tmp_path, "parameters.json", {"include": ["parameters.json"]})
        with pytest.raises(ValueError, match="Circular parameter file include"):
            Parameters.load_parameter_files([file_path])

    def test_indirect_cycle_is_detected(self, tmp_path):
        write(tmp_path, "base.json", {"include": ["parameters.json"]})
        file_path = write(tmp_path, "parameters.json", {"include": ["base.json"]})
        with pytest.raises(ValueError, match="Circular parameter file include"):
            Parameters.load_parameter_files([file_path])


class TestMultipleFiles:
    def test_files_are_merged_in_argument_order(self, tmp_path):
        first_path = write(tmp_path, "first.json", {"case_height": 10, "kerf": 0.1})
        second_path = write(tmp_path, "second.json", {"case_height": 20})

        assert Parameters.load_parameter_files([first_path, second_path]) == {
            "case_height": 20,
            "kerf": 0.1,
        }
        assert Parameters.load_parameter_files([second_path, first_path]) == {
            "case_height": 10,
            "kerf": 0.1,
        }

    def test_each_file_resolves_its_own_includes_first(self, tmp_path):
        write(tmp_path, "base.json", {"case_height": 10, "kerf": 0.1})
        first_path = write(tmp_path, "first.json", {"kerf": 0.3})
        second_path = write(tmp_path, "second.json", {"include": ["base.json"]})

        # second.json's include is merged after first.json, so base.json's kerf
        # wins over the earlier file on the command line.
        assert Parameters.load_parameter_files([first_path, second_path]) == {
            "case_height": 10,
            "kerf": 0.1,
        }

    def test_no_files_gives_an_empty_dict(self):
        assert Parameters.load_parameter_files([]) == {}


class TestParameterObject:
    def test_loaded_parameters_become_attributes(self, tmp_path):
        write(tmp_path, "base.json", {"case_height": 10, "switch_type": "mx"})
        file_path = write(
            tmp_path, "parameters.json", {"include": ["base.json"], "case_height": 18}
        )

        parameters = Parameters(Parameters.load_parameter_files([file_path]))

        assert parameters.case_height == 18
        assert parameters.switch_type == "mx"
        assert not hasattr(parameters, Parameters.INCLUDE_KEY)
