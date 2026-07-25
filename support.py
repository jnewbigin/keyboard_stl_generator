from solid import *
from solid import OpenSCADObject
from solid.utils import *

import logging

from cell import Cell
from parameters import Parameters

class Support(Cell):

    def __init__(self, x: float, y: float, w: float, h: float, plate_thickness: float, support_bar_height: float, support_bar_width: float, support_bar_fillet: float = 0.0, rotation: float = 0.0,  r_x_offset: float = 0.0, r_y_offset: float = 0.0, z_offset: float = 0.0, set_to_origin: bool = True, cell_value: str = '', parameters: Parameters = Parameters()) -> None:
        super().__init__(x, y, w, h, rotation,  r_x_offset, r_y_offset, z_offset = z_offset, cell_value = cell_value, parameters = parameters)

        self.logger = logging.getLogger().getChild(__name__)

        self.plate_thickness = plate_thickness
        self.set_to_origin = set_to_origin
        self.support_bar_height = support_bar_height
        self.support_bar_width = support_bar_width
        self.support_bar_fillet = support_bar_fillet

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

        d += self.switch_support_fillet()

        if self.set_to_origin == True:
            d = right(self.w_mm / 2) ( back(self.h_mm / 2) ( d ) )

        return d

    def switch_support_fillet(self) -> OpenSCADObject:

        # A 45-degree gusset in the concave corner where the inside face of the
        # skirt wall meets the underside of the plate, to strengthen the joint.
        # The fillet material that falls inside the switch opening is removed
        # later when the switch cutouts are subtracted, so only the corner
        # gussets outside the opening survive.
        f = self.support_bar_fillet

        inner_x = (self.w_mm - (self.support_bar_width / 2)) / 2
        inner_y = (self.h_mm - (self.support_bar_width / 2)) / 2

        f = min(f, inner_x, inner_y)
        if f <= 0:
            return union()

        eps = 0.01
        top_z = -self.plate_thickness / 2

        band = up(top_z - (f / 2)) (
            cube([2 * (inner_x + eps), 2 * (inner_y + eps), f], center = True)
        )

        opening = hull() (
            up(top_z) ( cube([2 * (inner_x - f), 2 * (inner_y - f), eps], center = True) ),
            up(top_z - f) ( cube([2 * (inner_x + (2 * eps)), 2 * (inner_y + (2 * eps)), eps], center = True) )
        )

        return band - opening
        
    def switch_support(self) -> OpenSCADObject:
        
        d = cube([self.w_mm, self.h_mm, self.plate_thickness], center = True)

        if self.set_to_origin == True:
            d = right(self.w_mm / 2) ( back(self.h_mm / 2) ( d ) )
            
        d += self.switch_support_outline()

        return d