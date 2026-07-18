from solid import *
from solid import OpenSCADObject
from solid.utils import *

import logging

from cell import Cell
from parameters import Parameters

class Support(Cell):

    def __init__(self, x: float, y: float, w: float, h: float, plate_thickness: float, support_bar_height: float, support_bar_width: float, rotation: float = 0.0,  r_x_offset: float = 0.0, r_y_offset: float = 0.0, z_offset: float = 0.0, set_to_origin: bool = True, cell_value: str = '', parameters: Parameters = Parameters()) -> None:
        super().__init__(x, y, w, h, rotation,  r_x_offset, r_y_offset, z_offset = z_offset, cell_value = cell_value, parameters = parameters)

        self.logger = logging.getLogger().getChild(__name__)
        
        self.plate_thickness = plate_thickness
        self.set_to_origin = set_to_origin
        self.support_bar_height = support_bar_height
        self.support_bar_width = support_bar_width

        self.solid = self.switch_support()

    def __str__(self) -> str:
        return 'Support: ' + super().__str__()

    def switch_support_outline(self) -> OpenSCADObject:

        # The skirt hangs below the cap. When the switch is raised, extend the
        # skirt downward by z_offset so that once get_moved() lifts the whole
        # support by z_offset the skirt still lands on the base plate.
        skirt_drop = self.support_bar_height + self.z_offset

        d = down(skirt_drop / 2) (
            cube([self.w_mm, self.h_mm, skirt_drop + self.plate_thickness], center = True)
        )

        d -= down(skirt_drop / 2) (
            cube([self.w_mm - (self.support_bar_width / 2), self.h_mm - (self.support_bar_width / 2), skirt_drop *2], center = True)
        )

        if self.set_to_origin == True:
            d = right(self.w_mm / 2) ( back(self.h_mm / 2) ( d ) )

        return d
        
    def switch_support(self) -> OpenSCADObject:
        
        d = cube([self.w_mm, self.h_mm, self.plate_thickness], center = True)

        if self.set_to_origin == True:
            d = right(self.w_mm / 2) ( back(self.h_mm / 2) ( d ) )
            
        d += self.switch_support_outline()

        return d