from solid import *
from solid import OpenSCADObject
from solid.utils import *

import logging

from cell import Cell
from parameters import Parameters

class SupportCutout(Cell):

    def __init__(self, x: float, y: float, w: float, h: float, plate_thickness: float, support_bar_height: float, support_bar_width: float, rotation: float = 0.0,  r_x_offset: float = 0.0, r_y_offset: float = 0.0, z_offset: float = 0.0, set_to_origin: bool = False, cell_value: str = '', parameters: Parameters = Parameters()) -> None:
        super().__init__(x, y, w, h, rotation,  r_x_offset, r_y_offset, z_offset = z_offset, cell_value = cell_value, parameters = parameters)

        self.logger = logging.getLogger().getChild(__name__)

        self.plate_thickness = plate_thickness
        self.set_to_origin = set_to_origin
        self.support_bar_height = support_bar_height
        self.support_bar_width = support_bar_width

        self.solid = self.support_cutout()

    # def u(self, u_value):
    #     return u_value * self.SWITCH_SPACING

    def __str__(self) -> str:
        return 'SupportCutout: ' + super().__str__()

    def support_cutout(self) -> OpenSCADObject:
        # Adjacent support cutouts tile the whole plate edge-to-edge and the
        # cutout top sits flush with the plate bottom. Both produce coplanar
        # coincident faces that leave the unioned/subtracted mesh non-manifold.
        # Grow the cube by epsilon in every direction so neighbours overlap and
        # the cut pokes through the plate bottom instead of ending flush.
        eps = 0.01
        # Match the raised support skirt: extend the cleared column downward by
        # z_offset so the cavity spans the full taller skirt once get_moved()
        # lifts it by z_offset.
        skirt_drop = self.support_bar_height + self.z_offset
        d = down(skirt_drop / 2) ( cube([self.w_mm + eps, self.h_mm + eps, skirt_drop + self.plate_thickness + eps], center = True) )

        d = right(self.w_mm / 2) ( back(self.h_mm / 2) ( d ) )

        return d # right(u(w / 2)) ( back(u(h / 2)) ( d ) )
