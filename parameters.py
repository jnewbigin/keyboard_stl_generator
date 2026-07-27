import logging
import math
import sys
from collections.abc import Sequence
from pathlib import Path, PurePath

import json5
import jsonschema

from switch_config import SwitchConfig

# from cell import Cell

logger = logging.getLogger(__name__)


class Parameters:

    # SWITCH_SPACING = 19.05

    # Keys consumed by the loader itself rather than set as attributes.
    INCLUDE_KEY = 'include'
    SCHEMA_KEY = '$schema'

    SCHEMA_PATH = Path(__file__).resolve().parent / 'parameters.schema.json'

    _schema: dict | None = None

    PARAMETER_FILE_SUFFIXES = ('.json', '.json5')

    # Parameters handled by build_attr_from_dict rather than set directly.
    SPECIAL_PARAMETERS = ('custom_switch',)

    # Parameters that were renamed. The old names are not accepted; this only
    # points at the replacement when an old name turns up in a parameter file.
    RENAMED_PARAMETERS = {
        'plate_wall_thickness': 'case_wall_thickness',
        'hole_width': 'cable_hole_width',
        'hole_height': 'cable_hole_height'
    }

    def __init__(self, parameter_dict: dict | None = None) -> None:

        self.logger = logger

        self.parameter_dict = parameter_dict

        # self.default_parameter_dict = {
        #     'plate_supports': True,

        #     'x_build_size' : 200,
        #     'y_build_size' : 200,

        #     'switch_type': 'mx_openable',
        #     'stabilizer_type': 'cherry',

        #     'custom_shape': False,
        #     'custom_shape_points': None,
        #     'custom_shape_path': None,

        #     'kerf' : 0.00,

        #     'top_margin' : 0,
        #     'bottom_margin' : 0,
        #     'left_margin' : 0,
        #     'right_margin' : 0,
        #     'case_height' : 10,
        #     # 'plate_wall_thickness' : 2.0,
        #     'case_wall_thickness' : 0.0,
        #     'plate_thickness' : 1.111,
        #     'plate_corner_radius' : 0,
        #     'bottom_cover_thickness': 0,

        #     'support_bar_height' : 3.0,
        #     'support_bar_width' : 1.0,
        #     'tilt': 0.0,

        #     'simple_test': False,

        #     'screw_count': 0,
        #     'screw_diameter': 0,
        #     'screw_edge_inset': 0,

        #     'cable_hole': False,
        #     'hole_width': 10,
        #     'hole_height': 10,
        #     'cable_hole_down_offset': 1
        # }

        self.switch_spacing = 19.05

        self.x_build_size = 200
        self.y_build_size = 200
        self.kerf = 0.01

        # Interlocking finger joint between printed sections. The shared seam
        # zig-zags by section_finger_depth (mm) every section_finger_height
        # (key units) of travel, alternating side to side, so the pieces lock
        # together. Fingers are clamped so they never cut a key, so they appear
        # where there is spare plate (the top/bottom margins and keyless gaps).
        # Set section_finger_depth to 0 for a plain butt-joint seam.
        self.section_finger_depth = 4.0
        self.section_finger_height = 2.0

        self.switch_type = 'mx_openable'
        self.stabilizer_type = 'cherry_costar'

        # Custom Switch Cutout Attributes
        self.custom_shape = False
        self.custom_shape_points: list | None = None
        self.custom_shape_path: list | None = None

        self.plate_supports = True
        self.support_bar_height = 3.0
        self.support_bar_width = 3.0
        self.support_bar_fillet = 0.5

        self.top_margin = 10.0
        self.bottom_margin = 10.0
        self.left_margin = 10.0
        self.right_margin = 10.0

        self.case_height = 18
        self.case_wall_thickness = 3.0
        self.plate_thickness = 1.111
        self.plate_corner_radius = 4
        self.bottom_cover_thickness = 1
        self.tilt = 2.0

        self.simple_test = False

        self.screw_count = 4
        self.screw_diameter = 4
        self.screw_edge_inset = 7
        self.screw_edge_x_inset: float | None = None
        self.screw_edge_y_inset: float | None = None
        self.screw_hole_body_wall_width = 2
        self.screw_hole_body_support_x_factor = 4

        self.custom_screw_hole_coordinates_origin = [0, 0]
        self.custom_screw_hole_coordinates: list | None = None

        self.cable_hole = False
        self.cable_diameter = 4
        self.cable_hole_width = 10
        self.cable_hole_height = 10
        self.cable_hole_up_offset = 1
        self.cable_hole_down_offset = 1
        # Horizontal centre of the cable hole in mm from the left case edge.
        # None keeps the hole centred on the key field.
        self.cable_hole_x_offset: float | None = None

        self.custom_polygons: list | None = None

        self.custom_pcb: bool | None = None
        self.pcb_width: float | None = None
        self.pcb_height: float | None = None
        self.pcb_top_left_coordinates: list | None = None
        self.pcb_left_switch_center_x_coordinate: float | None = None
        self.pcb_top_switch_center_y_coordinate: float | None = None
        self.pcb_case_top_margin: float | None = None
        self.pcb_case_bottom_margin: float | None = None
        self.pcb_case_right_margin: float | None = None
        self.pcb_case_left_margin: float | None = None

        self.test_block = False
        self.test_block_x_start = 0
        self.test_block_x_end = 0
        self.test_block_y_start = 0
        self.test_block_y_end = 0
        self.test_block_z_start = 0
        self.test_block_z_end = 0

        self.switch_config: SwitchConfig | None = None

        self.min_x = 0.0
        self.max_x = 0.0
        self.min_y = 0.0
        self.max_y = 0.0

        self.real_max_x = 0.0
        self.real_max_y = 0.0
        self.real_case_width = 0.0
        self.real_case_height = 0.0

        self.case_height_extra = 50

        # Calculated attributes
        self.case_height_base_removed: float | None = None
        self.case_height_extra_fill: float | None = None
        self.side_margin_diff: float | None = None
        self.top_margin_diff: float | None = None
        self.screw_tap_hole_diameter: float | None = None
        self.screw_hole_body_diameter: float | None = None
        self.screw_hole_body_radius: float | None = None
        self.x_screw_width: float | None = None
        self.y_screw_width: float | None = None
        self.bottom_section_count: int | None = None
        self.screw_hole_body_support_end_x: float | None = None

        if self.parameter_dict is not None:
            self.build_attr_from_dict(self.parameter_dict)

        # self.validate_parameters()

    def __repr__(self) -> str:
        output = 'Parameters:\n'
        ignore_attr_names = [
            'logger', 'parameter_dict', 'switch_config',
            'min_x', 'max_x', 'min_y', 'max_y',
            'real_max_x', 'real_max_y',
            # 'real_case_width', 'real_case_height',
            'case_height_extra', 'case_height_base_removed', 'case_height_extra_fill', 'side_margin_diff',
            'top_margin_diff', 'screw_tap_hole_diameter', 'screw_hole_body_diameter', 'screw_hole_body_radius',
            'x_screw_width', 'y_screw_width', 'bottom_section_count', 'screw_hole_body_support_end_x',
            'test_block', 'test_block_x_start', 'test_block_x_end', 'test_block_y_start',
            'test_block_y_end', 'test_block_z_start', 'test_block_z_end'
        ]
        for attr_name in self.__dict__:
            if attr_name not in ignore_attr_names:
                output += f'{attr_name}: {self.__dict__[attr_name]!s}\n'

        return output

    def U(self, u_value: float) -> float:
        return u_value * self.switch_spacing

    def cable_hole_center_x(self) -> float:
        # Real x of the cable hole centre once the assembly is placed (the case
        # left edge sits at x = 0). Requires set_dimensions to have run.
        if self.cable_hole_x_offset is not None:
            return self.cable_hole_x_offset
        return self.left_margin + (self.real_max_x / 2)

    def update_calculated_attributes(self) -> None:
        # Calculated attributes
        if self.screw_edge_x_inset is None:
            self.screw_edge_x_inset = self.screw_edge_inset
        if self.screw_edge_y_inset is None:
            self.screw_edge_y_inset = self.screw_edge_inset

        self.case_height_base_removed = self.case_height - self.bottom_cover_thickness
        self.case_height_extra_fill = self.case_height + self.case_height_extra
        self.side_margin_diff = self.right_margin - self.left_margin
        self.top_margin_diff = self.bottom_margin - self.top_margin
        self.screw_tap_hole_diameter = self.screw_diameter - 0.35
        self.screw_hole_body_diameter = self.screw_diameter + (self.screw_hole_body_wall_width * 2)
        self.screw_hole_body_radius = self.screw_hole_body_diameter / 2
        self.x_screw_width = self.real_case_width - (self.screw_edge_x_inset * 2)  # + self.screw_diameter)
        self.y_screw_width = self.real_case_height - (self.screw_edge_y_inset * 2)  # + self.screw_diameter)
        self.bottom_section_count = math.ceil(self.real_case_width / self.x_build_size)
        self.screw_hole_body_support_end_x = (
                                                         self.case_height_extra_fill / self.screw_hole_body_support_x_factor) + self.screw_hole_body_radius

    def set_dimensions(self, max_x: float, min_y: float, min_x: float, max_y: float) -> None:

        self.max_x = max_x
        self.max_x = max_x
        self.min_y = min_y
        self.max_y = max_y
        self.logger.debug('min_x: %f, max_x: %f, max_y: %f, min_y: %f', self.min_x, self.max_x, self.max_y, self.min_y)

        # Get the calculated real max x and y sizes of the board
        self.real_max_x = self.U(self.max_x)
        self.real_max_y = self.U(abs(self.min_y))

        self.real_case_width = self.real_max_x + self.left_margin + self.right_margin
        self.real_case_height = self.real_max_y + self.top_margin + self.bottom_margin

        if self.custom_screw_hole_coordinates is not None:
            self.screw_edge_x_inset = 0
            self.screw_edge_y_inset = 0
            self.logger.debug('Custom Screw Default: screw_edge_x_inset: %f, screw_edge_y_inset: %f',
                              self.screw_edge_x_inset, self.screw_edge_y_inset)

        if self.custom_pcb:
            half_u = self.U(1) / 2

            # Get the top left coordinates for the PCB itself.
            pcb_x_coordinate = 0
            pcb_y_coordinate = 0
            if self.pcb_top_left_coordinates is not None:
                pcb_x_coordinate = self.pcb_top_left_coordinates[0]
                pcb_y_coordinate = self.pcb_top_left_coordinates[1]

            # A custom PCB requires all of these to be supplied in the config.
            assert self.pcb_width is not None
            assert self.pcb_height is not None
            assert self.pcb_left_switch_center_x_coordinate is not None
            assert self.pcb_top_switch_center_y_coordinate is not None
            assert self.pcb_case_left_margin is not None
            assert self.pcb_case_right_margin is not None
            assert self.pcb_case_top_margin is not None
            assert self.pcb_case_bottom_margin is not None

            # Get the x any y coordinates of the top reference switch and left reference switch
            left_switch_left_x_coordinate = self.pcb_left_switch_center_x_coordinate - half_u
            top_switch_top_y_coordinate = self.pcb_top_switch_center_y_coordinate - half_u

            # Get the margin built into the left and top of the PCB
            pcb_left_margin = left_switch_left_x_coordinate - pcb_x_coordinate
            pcb_top_margin = top_switch_top_y_coordinate - pcb_y_coordinate

            pcb_right_margin = self.pcb_width - (pcb_left_margin + self.real_max_x)
            pcb_bottom_margin = self.pcb_height - (pcb_top_margin + self.real_max_y)

            self.left_margin = self.case_wall_thickness + self.pcb_case_left_margin + pcb_left_margin
            self.right_margin = self.case_wall_thickness + self.pcb_case_right_margin + pcb_right_margin
            self.top_margin = self.case_wall_thickness + self.pcb_case_top_margin + pcb_top_margin
            self.bottom_margin = self.case_wall_thickness + self.pcb_case_bottom_margin + pcb_bottom_margin

            if self.custom_screw_hole_coordinates is not None:
                screw_hole_origin_x = self.custom_screw_hole_coordinates_origin[0]
                screw_hole_origin_y = self.custom_screw_hole_coordinates_origin[1]

                screw_hole_pcb_origin_x_offset = screw_hole_origin_x - pcb_x_coordinate
                screw_hole_pcb_origin_y_offset = (pcb_y_coordinate + self.pcb_height) - screw_hole_origin_y

                self.screw_edge_x_inset = self.case_wall_thickness + self.pcb_case_left_margin + screw_hole_pcb_origin_x_offset
                self.screw_edge_y_inset = self.case_wall_thickness + self.pcb_case_bottom_margin + screw_hole_pcb_origin_y_offset
                self.logger.debug('PCB settings: screw_edge_x_inset: %f, screw_edge_y_inset: %f',
                                  self.screw_edge_x_inset, self.screw_edge_y_inset)

        self.logger.debug('real_max_x: %d, real_max_y: %s', self.real_max_x, self.real_max_y)

        self.update_calculated_attributes()

        self.validate_cable_hole()

    def build_attr_from_dict(self, parameter_dict: dict) -> None:

        self.check_parameter_names(parameter_dict)
        self.check_parameter_types(parameter_dict)

        for param in parameter_dict:
            value = parameter_dict[param]

            if param == 'custom_switch':
                if 'points' not in value:
                    raise AttributeError('A set of "points" must exist in the "custom_switch" to use a custom switch')

                self.custom_shape_points = value['points']

                if 'path' in value:
                    self.custom_shape_path = value['path']
                else:
                    self.logger.warning(
                        'Custom Switch defined but no "path" list defined. Points in "points" list will be used in defined order')

                self.custom_shape = True

            setattr(self, param, value)

        self.switch_config = SwitchConfig(kerf=self.kerf, switch_type=self.switch_type,
                                          stabilizer_type=self.stabilizer_type, custom_shape=self.custom_shape,
                                          custom_shape_points=self.custom_shape_points,
                                          custom_shape_path=self.custom_shape_path)

        self.update_calculated_attributes()

        self.validate_parameters()

    @classmethod
    def schema(cls) -> dict:
        if cls._schema is None:
            cls._schema = json5.loads(cls.SCHEMA_PATH.read_text(encoding='utf-8'))
        return cls._schema

    @classmethod
    def check_parameter_types(cls, parameter_dict: dict) -> None:
        # Values reach attributes through setattr, so nothing else checks that
        # what a parameter file supplies is the right type. A string "false"
        # would otherwise read as enabled at every truth test.
        validator = jsonschema.Draft202012Validator(cls.schema())

        problems = []
        for error in sorted(validator.iter_errors(parameter_dict), key=str):
            if error.absolute_path:
                name = '.'.join(str(part) for part in error.absolute_path)
                problems.append(f'{name}: {error.message}')
            else:
                problems.append(error.message)

        if len(problems) > 0:
            raise ValueError('Invalid parameters: {}'.format('; '.join(problems)))

    def check_parameter_names(self, parameter_dict: dict) -> None:
        # Every parameter has an attribute of the same name set up in __init__,
        # so anything else is a typo or a name that no longer exists. Setting it
        # would otherwise be silently ignored and the default used instead.
        known_names = set(self.__dict__.keys()) | set(self.SPECIAL_PARAMETERS)

        problems = []
        for name in parameter_dict:
            if name in known_names:
                continue

            if name in self.RENAMED_PARAMETERS:
                problems.append(f'{name} was renamed to {self.RENAMED_PARAMETERS[name]}')
            else:
                problems.append(f'{name} is not a parameter')

        if len(problems) > 0:
            raise ValueError('Unknown parameters: {}'.format('; '.join(problems)))

    def set_parameter_dict(self, parameter_dict: dict) -> None:
        self.parameter_dict = parameter_dict
        self.build_attr_from_dict(self.parameter_dict)

    @classmethod
    def load_parameter_files(cls, file_paths: Sequence[str | PurePath]) -> dict:
        # Flatten one or more parameter files, and everything they include, into
        # a single dict. Merging is shallow and later always wins: files are
        # merged in the order given, and within a file the includes are merged
        # in list order before the file's own keys, so a file always overrides
        # what it includes.
        if isinstance(file_paths, (str, PurePath)):
            raise TypeError(f'load_parameter_files takes a list of parameter files, not a single {type(file_paths).__name__}. '
                            f'Pass [{str(file_paths)!r}] instead')

        # A file reached down more than one include path is only resolved once.
        resolved_files: dict[Path, dict] = {}

        parameter_dict: dict = {}
        for file_path in file_paths:
            parameter_dict.update(cls.resolve_parameter_file(Path(file_path), [], resolved_files))

        return parameter_dict

    @classmethod
    def resolve_parameter_file(cls, file_path: Path, include_chain: list[Path],
                               resolved_files: dict[Path, dict] | None = None) -> dict:
        if resolved_files is None:
            resolved_files = {}

        real_path = file_path.resolve()

        if real_path in include_chain:
            chain = ' -> '.join(str(path) for path in [*include_chain, real_path])
            raise ValueError(f'Circular parameter file include: {chain}')

        if real_path in resolved_files:
            return dict(resolved_files[real_path])

        cls.check_parameter_file(file_path, include_chain)

        logger.debug('Read parameter file %s', file_path)
        file_text = cls.read_parameter_file(file_path)

        try:
            # Parse with json5 so the parameter file may contain // and /* */
            # comments and trailing commas. json5 is a strict superset of JSON,
            # so plain JSON parameter files keep working unchanged.
            file_dict = json5.loads(file_text)
        except ValueError as error:
            raise ValueError(f'Failed to parse parameter file {file_path}: {error}') from error

        if not isinstance(file_dict, dict):
            raise TypeError(f'Parameter file {file_path} must contain a JSON object')

        file_dict.pop(cls.SCHEMA_KEY, None)
        include_names = cls.include_names(file_dict.pop(cls.INCLUDE_KEY, []), file_path)

        parameter_dict: dict = {}
        for include_name in include_names:
            # Includes are resolved against the including file so a shared set
            # of base files can be included from anywhere.
            include_path = file_path.parent / include_name
            parameter_dict.update(cls.resolve_parameter_file(include_path, [*include_chain, real_path],
                                                             resolved_files))

        parameter_dict.update(file_dict)

        resolved_files[real_path] = parameter_dict

        return dict(parameter_dict)

    @classmethod
    def check_parameter_file(cls, file_path: Path, include_chain: list[Path]) -> None:
        described = f'Parameter file {file_path} included from {include_chain[-1]}' if len(include_chain) > 0 else f'Parameter file {file_path}'

        if file_path.is_dir():
            raise IsADirectoryError(f'{described} is a directory, not a parameter file')

        if not file_path.exists():
            raise FileNotFoundError(f'{described} does not exist')

        if not file_path.is_file():
            raise ValueError(f'{described} is not a regular file')

        if file_path.suffix not in cls.PARAMETER_FILE_SUFFIXES:
            raise ValueError('{} must be named {}'.format(described, ' or '.join(cls.PARAMETER_FILE_SUFFIXES)))

    @classmethod
    def include_names(cls, include_value: object, file_path: Path) -> list[str]:
        names: list[str] = []

        if isinstance(include_value, str):
            names = [include_value]
        elif isinstance(include_value, list) and all(isinstance(name, str) for name in include_value):
            names = list(include_value)
        else:
            raise TypeError(f'"{cls.INCLUDE_KEY}" in {file_path} must be a file name or a list of file names')

        for name in names:
            if name.strip() == '':
                raise ValueError(f'"{cls.INCLUDE_KEY}" in {file_path} contains an empty file name')

        return names

    @staticmethod
    def read_parameter_file(file_path: Path) -> str:
        try:
            return file_path.read_text(encoding='utf-8')
        except UnicodeDecodeError as error:
            raise ValueError(f'Parameter file {file_path} is not utf-8 encoded') from error

    # def get_param(self, parameter_name):

    #     if self.parameter_dict is not None and parameter_name in self.parameter_dict.keys():
    #         return self.parameter_dict[parameter_name]
    #     elif parameter_name in self.default_parameter_dict.keys():
    #         return self.default_parameter_dict[parameter_name]
    #     else:
    #         raise ValueError('No parameter exists with name %s' % (parameter_name))

    def validate_parameters(self) -> None:
        assert self.switch_config is not None
        parameter_error = False
        error_message = ''
        # if self.screw_edge_inset < self.case_wall_thickness + self.screw_hole_body_radius:
        #     parameter_error = True
        #     error_message += 'Screw Edge Inset %f must be greater than case_wall_thickness: %f + screw_hole_body_radius: %f = %f\n' % (self.screw_edge_inset, self.case_wall_thickness, self.screw_hole_body_radius, self.case_wall_thickness + self.screw_hole_body_radius)

        if self.screw_count > 0:
            if self.screw_count < 4:
                parameter_error = True
                error_message += 'Screw count must be at least 4\n'
            if self.screw_count % 2 != 0:
                parameter_error = True
                error_message += 'Screw count must be even\n'

        if self.switch_type not in self.switch_config.switch_type_function_dict:
            parameter_error = True
            error_message += f'switch type {self.switch_type} is not a valid switch type'

        if self.stabilizer_type not in self.switch_config.stab_type_function_dict:
            parameter_error = True
            error_message += f'stabilizer type {self.stabilizer_type} is not a valid stabilizer type'

        if parameter_error:
            print('ERROR:', error_message)
            sys.exit(1)

    def validate_cable_hole(self) -> None:
        # Runs from set_dimensions, once the real case size is known. The top
        # piece spans x = 0 .. real_case_width and z = 0 (case floor) up to the
        # plate underside, so the hole must sit fully inside both.
        if not self.cable_hole:
            return

        assert self.case_height_base_removed is not None
        parameter_error = False
        error_message = ''

        if self.cable_hole_width <= 0:
            parameter_error = True
            error_message += 'cable_hole_width must be greater than 0\n'

        if self.cable_hole_height <= 0:
            parameter_error = True
            error_message += 'cable_hole_height must be greater than 0\n'

        center = self.cable_hole_center_x()
        half_width = self.cable_hole_width / 2
        if center - half_width < 0 or center + half_width > self.real_case_width:
            parameter_error = True
            error_message += (f'cable hole (centre {center:.2f}mm, width {self.cable_hole_width:.2f}mm) does not fit within the {self.real_case_width:.2f}mm case width\n')

        available_height = self.case_height_base_removed - self.plate_thickness - self.cable_hole_down_offset
        if self.cable_hole_height > available_height:
            parameter_error = True
            error_message += (f'cable hole (height {self.cable_hole_height:.2f}mm) does not fit within the {available_height:.2f}mm available below the plate\n')

        if parameter_error:
            print('ERROR:', error_message)
            sys.exit(1)
