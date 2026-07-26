from solid import *
from solid import OpenSCADObject
from solid.utils import *

import logging
import sys
from typing import Any

from cell import Cell, CellProperties
from parameters import Parameters
from switch_config import SwitchConfig

class Switch(Cell):
    """
    Defines a Switch object that inherits from the Cell class

    ...

    Attributes
    ----------
    props : CellProperties
        position, size, rotation, z offset and key text of the switch in
        keyboard layout U units

    parameters : Parameters
        object containing parameter settings

    switch_config : SwitchConfig, default None
        config opbject for switch

    Methods
    -------
    switch_cutout()
        Get a switch soild that matches the attribute settings
    update_all_neighbors_set(neighbor_group = 'local')
        Check if all neighbors are defined where they exist and set the neighbor_check_complete value to match
    get_all_neighbors_set(neighbor_group = 'local')
        Get the value of neighbor_check_complete for the passed in neughbor group
    get_neighbor(neighbor_name, neighbor_group = 'local')
        Get the neighbor Switch object for the name and group passed in
    set_neighbor(neighbor = None, neighbor_name = '', offset = 0.0, has_neighbor = True, neighbor_group = 'local', perp_offset = 0.0)
        Set a neighbor for the switch object
    has_neighbor(neighbor_name = '', neighbor_group = 'local')
        Return True if switch has a neigbor with name and group passed in. False if no neighbor
    get_neighbor_offset(neighbor_name = '', neighbor_group = 'local')
        Get the x offset to the neighbor for the name and group passed in
    get_neighbor_perp_offset(neighbor_name = '', neighbor_group = 'local')
        Get the perpendicular offset to the neighbor for the name and group passed in
    get_neighbor_direction_list()
        Helper to get list of neighbor direction names
    """

    NEIGHBOR_OPOSITE_DICT = {
        'right': 'left',
        'left': 'right',
        'top': 'bottom',
        'bottom': 'top'
    }


    def __init__(self, props: CellProperties, parameters: Parameters, switch_config: SwitchConfig | None = None) -> None:
        super().__init__(props, parameters)

        self.logger = logging.getLogger().getChild(__name__)

        self.switch_config = switch_config
        if self.switch_config is None:
            self.switch_config = SwitchConfig()

        self.solid = self.switch_cutout()

        self.logger.debug('x: %f, y: %f, w: %f, h: %f, end_x: %f, end_y: %f', self.x, self.y, self.w, self.h, self.end_x, self.end_y) 

        self.global_neighbors: dict[str, Any] = {
            'right': {
            },
            'left': {
            },
            'top': {
            },
            'bottom': {
            },
            'neighbor_check_complete': False
        }

        self.local_neighbors: dict[str, Any] = {
            'right': {
            },
            'left': {
            },
            'top': {
            },
            'bottom': {
            },
            'neighbor_check_complete': False
        }

        # self.right = None
        # self.left_in_section = None
        # self.up_in_section = None
        # self.down_in_section = None

        # self.neighbors
    

    def neighbors_formatted(self, obj: Any, indent: int = 2, current_indent: int = 0) -> str:
        current_output = ''
        current_indent_str = ' ' * current_indent
        if isinstance(obj, dict):
            for i, key in enumerate(obj.keys()):
                value = obj[key]
                current_output += current_indent_str + key + ': '

                if isinstance(value, dict):
                    current_output += '{\n'

                current_output += str(self.neighbors_formatted(value, indent, current_indent + indent))


                if isinstance(value, dict):
                    current_output += current_indent_str+ '}'

                if i < len(obj.keys()) - 1:
                    current_output += ','

                current_output += '\n'

        else:
            current_output += str(obj)

        return current_output


    def __str__(self) -> str:
        return 'Switch: ' + super().__str__()

    def __repr__(self) -> str:
        global_neighbors_json = self.neighbors_formatted(self.global_neighbors, indent=4, current_indent=10)
        local_neighbors_json = self.neighbors_formatted(self.local_neighbors, indent=4, current_indent=10)
        return 'Switch: ' + super().__str__() + '\nglobal neighbors: \n' + global_neighbors_json + '\nlocal neighbors: \n' + local_neighbors_json


    def switch_cutout(self) -> OpenSCADObject:
        """
        Return the polygon that will be used to cutout a place in the plate for a switch

        Returns
        -------
        OpenSCADObject
            The OpenSCADObject for the cutout
        """

        assert self.switch_config is not None
        self.logger.debug('switch %s, switch type: %s, stab type: %s', self.cell_value, self.switch_config.switch_type, self.switch_config.stabilizer_type)

        # switch_poly_points, switch_poly_path = self.switch_config.get_switch_poly_info()
        # stab_poly_points, stab_poly_path = self.switch_config.get_stab_poly_info(key_width = self.switch_length)

        switch_poly_points = self.switch_config.get_switch_poly_info()
        assert switch_poly_points is not None
        switch_poly_path = [range(len(switch_poly_points))]

        stab_poly_points, *support_cutout_poly_points = self.switch_config.get_stab_poly_info(key_width = self.switch_length)

        if len(support_cutout_poly_points) == 2:
            advanced_poly_points = support_cutout_poly_points[1]
        else:
            advanced_poly_points = []
        support_cutout_poly_points = support_cutout_poly_points[0]
        
        
        self.logger.debug('\tswitch_poly_points: %d, switch_poly_path: %d', len(switch_poly_points), len(switch_poly_path))

        # Create switch cutout polygon
        cutout_polygon = polygon(switch_poly_points, switch_poly_path)

        # Create stab polygon if it is defined
        if stab_poly_points is not None:
            stab_poly_path = [range(len(stab_poly_points))]
            
            self.logger.debug('\t\tstab_poly_points: %d, stab_poly_path: %d', len(stab_poly_points), len(stab_poly_path))
            stab = polygon(stab_poly_points, stab_poly_path) + mirror([1, 0, 0]) ( polygon(stab_poly_points, stab_poly_path) )
            # stab = polygon(stab_poly_points, stab_poly_path)# + mirror([1, 0, 0]) ( polygon(stab_poly_points, stab_poly_path) )
            if support_cutout_poly_points is not None:
                support_cutout_poly_path = [range(len(support_cutout_poly_points))]
                support_cutout = polygon(support_cutout_poly_points, support_cutout_poly_path) + mirror([1, 0, 0]) ( polygon(support_cutout_poly_points, support_cutout_poly_path) )
            cutout_polygon += stab

        # Through-plate cutouts are a centered column. When a switch is raised
        # (z_offset > 0) the local plate cap sits higher, so grow the column by
        # twice the offset: after get_moved() lifts it by z_offset the top still
        # clears the raised cap and the bottom still punches the base plate.
        extrude_height = 10 + (2 * self.z_offset)

        cutout = linear_extrude(height = extrude_height, center = True)(cutout_polygon)

        if support_cutout_poly_points is not None:
            cutout += down( (10 / 2) + (self.parameters.plate_thickness / 2) ) (
                linear_extrude(height = 10, center = True)(support_cutout)
            )

        # advanced poly points
        # multiple polygons
        # cutout
        # support_cutout
        # support_infill
        for advanced in advanced_poly_points:
            action, poly_points = advanced
            poly_path = [range(len(switch_poly_points))]
            advanced_polygon = polygon(poly_points, poly_path)

            if action == 'cutout':
                cutout += linear_extrude(height = extrude_height, center = True)(advanced_polygon)
            elif action == 'stab_cutout':
                # stab cutout it mirrored to each side of the switch
                support_cutout = advanced_polygon + mirror([1, 0, 0]) ( advanced_polygon )
                cutout += linear_extrude(height = extrude_height, center = True)(support_cutout)
            elif action == 'support_cutout':
                # support cutout it mirrored to each side of the switch
                support_cutout = advanced_polygon + mirror([1, 0, 0]) ( advanced_polygon )

                # and then extrude down to remove supports
                cutout += down( (10 / 2) + (self.parameters.plate_thickness / 2) ) (
                    linear_extrude(height = 10, center = True)(support_cutout)
                )
            elif action == 'support_infill':
                # support cutout it mirrored to each side of the switch
                support_cutout = advanced_polygon + mirror([1, 0, 0]) ( advanced_polygon )

                # and then extrude down to remove supports
                infill = down( (10 / 2) + (self.parameters.plate_thickness / 2) ) (
                    linear_extrude(height = 10, center = True)(support_cutout)
                )
            else:
                raise ValueError("Unknown action: " + action)


        cutout = rotate(a = 180, v = (0, 0, 1)) ( cutout )

        # Rotate a key if it is taller than it is wide
        if self.vertical:
            
            cutout = rotate(a = -90, v = (0, 0, 1)) ( cutout )

        offset_cutout = right(self.w_mm / 2) ( back(self.h_mm / 2) ( cutout ) )

        return offset_cutout



    def update_all_neighbors_set(self, neighbor_group: str = 'local') -> None:

        if neighbor_group == 'local':
            neighbor_dict = self.local_neighbors
        elif neighbor_group == 'global':
            neighbor_dict =  self.global_neighbors

            
        all_neighbors_set = True
        for direction in neighbor_dict.keys():
            if direction != 'neighbor_check_complete':
                if len(neighbor_dict[direction].keys()) == 0:
                    all_neighbors_set = False

        neighbor_dict['neighbor_check_complete'] = all_neighbors_set


    def get_all_neighbors_set(self, neighbor_group: str = 'local') -> bool:

        if neighbor_group == 'local':
            neighbor_dict = self.local_neighbors
        elif neighbor_group == 'global':
            neighbor_dict =  self.global_neighbors

        return neighbor_dict['neighbor_check_complete']


    def get_neighbor(self, neighbor_name: str, neighbor_group: str = 'local') -> 'Switch | None':
        
        neighbor = None

        if neighbor_group == 'local':
            neighbor = self.local_neighbors[neighbor_name]['neighbor']
        elif neighbor_group == 'global':
            neighbor =  self.global_neighbors[neighbor_name]['neighbor']

        return neighbor

    def set_neighbor(self, neighbor: 'Switch | None' = None, neighbor_name: str = '', offset: float = 0.0, has_neighbor: bool = True, neighbor_group: str = 'local', perp_offset: float = 0.0) -> None:
        
        temp_dict = {
            'has_neighbor': has_neighbor,
            'neighbor': neighbor,
            'offset': offset,
            'perp_offset': perp_offset
        }
        
        if neighbor_group == 'local':
            self.local_neighbors[neighbor_name] = temp_dict
        elif neighbor_group == 'global':
            self.global_neighbors[neighbor_name] = temp_dict
        
    # def set_right_neighbor(self, neighbor = None, offset = 0.0, has_neighbor = True, neighbor_group = 'local', perp_offset = 0.0):
    #     self.set_neighbor(neighbor, 'right', offset, has_neighbor, neighbor_group, perp_offset)

    # def set_left_neighbor(self, neighbor = None, offset = 0.0, has_neighbor = True, neighbor_group = 'local', perp_offset = 0.0):
    #     self.set_neighbor(neighbor, 'left', offset, has_neighbor, neighbor_group, perp_offset)

    # def set_top_neighbor(self, neighbor = None, offset = 0.0, has_neighbor = True, neighbor_group = 'local', perp_offset = 0.0):
    #     self.set_neighbor(neighbor, 'top', offset, has_neighbor, neighbor_group, perp_offset)

    # def set_bottom_neighbor(self, neighbor = None, offset = 0.0, has_neighbor = True, neighbor_group = 'local', perp_offset = 0.0):
    #     self.set_neighbor(neighbor, 'bottom', offset, has_neighbor, neighbor_group, perp_offset)

    def has_neighbor(self, neighbor_name: str = '', neighbor_group: str = 'local') -> bool:
        if neighbor_group == 'local':
            return self.local_neighbors[neighbor_name]['has_neighbor']
        else:
            return self.global_neighbors[neighbor_name]['has_neighbor']

    def get_neighbor_offset(self, neighbor_name: str = '', neighbor_group: str = 'local') -> float:
        if neighbor_group == 'local':
            return self.local_neighbors[neighbor_name]['offset']
        else:
            return self.global_neighbors[neighbor_name]['offset']

    def get_neighbor_perp_offset(self, neighbor_name: str = '', neighbor_group: str = 'local') -> float:
        if neighbor_group == 'local':
            return self.local_neighbors[neighbor_name]['perp_offset']
        else:
            return self.global_neighbors[neighbor_name]['perp_offset']

    def get_neighbor_direction_list(self) -> list[str]:

        name_list = []

        for neighbor_name in self.local_neighbors.keys():
            if isinstance(self.local_neighbors[neighbor_name], dict):
                name_list.append(neighbor_name)

        return name_list
