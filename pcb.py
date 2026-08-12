# from ast import Param

import logging

from solid import *
from solid import OpenSCADObject
from solid.utils import *

from parameters import Parameters


class PCB:

    def __init__(self, parameters: Parameters = Parameters()) -> None:

        self.parameters = parameters

        self.logger = logging.getLogger().getChild(__name__)

        self.custom_pcb = self.parameters.custom_pcb
        self.pcb_width = self.parameters.pcb_width
        self.pcb_height = self.parameters.pcb_height
        self.pcb_top_left_coordinates = self.parameters.pcb_top_left_coordinates
        self.pcb_left_switch_center_x_coordinate = (
            self.parameters.pcb_left_switch_center_x_coordinate
        )
        self.pcb_top_switch_center_y_coordinate = (
            self.parameters.pcb_top_switch_center_y_coordinate
        )
        self.pcb_case_top_margin = self.parameters.pcb_case_top_margin
        self.pcb_case_bottom_margin = self.parameters.pcb_case_bottom_margin
        self.pcb_case_right_margin = self.parameters.pcb_case_right_margin
        self.pcb_case_left_margin = self.parameters.pcb_case_left_margin

        self.pcb_thickness = 1.6

        self.pcb_plate_separation = 5

    def get_model(
        self, remove_above: bool = False, remove_bellow: bool = False
    ) -> OpenSCADObject:

        if self.custom_pcb:
            assert self.pcb_case_left_margin is not None
            assert self.pcb_case_bottom_margin is not None
            model_height = self.pcb_thickness
            down_offset = self.pcb_thickness + self.pcb_plate_separation

            if remove_above:
                model_height = self.pcb_thickness + self.parameters.case_height_extra
            elif remove_bellow:
                model_height = self.pcb_thickness + self.parameters.case_height_extra
                down_offset = down_offset + self.parameters.case_height_extra

            return right(
                self.parameters.case_wall_thickness + self.pcb_case_left_margin
            )(
                forward(
                    self.parameters.case_wall_thickness + self.pcb_case_bottom_margin
                )(
                    down(down_offset)(
                        cube([self.pcb_width, self.pcb_height, model_height])
                    )
                )
            )

        return union()
