from solid import *
from solid import OpenSCADObject
from solid.utils import *

import logging
import math
import json
import sys
from dataclasses import dataclass
from parameters import Parameters


@dataclass(frozen=True)
class CellProperties:
    x: float
    y: float
    w: float = 1.0
    h: float = 1.0
    rotation: float = 0.0
    z_offset: float = 0.0
    cell_value: str = ''

    @property
    def x_min(self) -> float:
        return self.x

    @property
    def x_max(self) -> float:
        return self.x + self.w

    @property
    def y_min(self) -> float:
        return self.y - self.h

    @property
    def y_max(self) -> float:
        return self.y

    @property
    def center_x(self) -> float:
        return self.x + (self.w / 2)

    @property
    def center_y(self) -> float:
        return self.y - (self.h / 2)

    @property
    def end_x(self) -> float:
        return self.x + self.w

    @property
    def end_y(self) -> float:
        return self.y - self.h

    @property
    def switch_length(self) -> float:
        return max(self.w, self.h)

    @property
    def vertical(self) -> bool:
        return self.h > self.w


class Cell:
    # Switch Dimensions
    # SWITCH_SPACING = 19.05
    # SQUARE_SIZE = 14
    # SQUARE_SIZE_HALF = SQUARE_SIZE / 2
    # # NOTCH_HEIGHT = 3.5
    # NOTCH_WIDTH = 0.8
    # CLIP_NOTCH_X = SQUARE_SIZE_HALF + NOTCH_WIDTH
    # CLIP_NOTCH_Y_MAX = 6
    # CLIP_NOTCH_Y_MIN = 2.9
    # NOTCH_VERT_SPACING = 5
    # NOTCH_VERT_SPACING_HALF = NOTCH_VERT_SPACING / 2
    # NOTCH_EDGE_OFFSET = 1
    # CORNER_CIRCLE_EDGE_OFFSET = 0.0


    # # #[Stab Dimensions]
    # BAR_BOTTOM_Y = 2.3
    # MAIN_BODY_BOTTOM_Y = 5.53
    # BOTTOM_NOTCH_BOTTOM_Y = 6.45
    # SIDE_NOTCH_TOP_Y = 0.5
    # MAIN_BODY_TOP_Y = 6.77
    # TOP_NOTCH_TOP_Y = 7.75
    # MAIN_BODY_SWITCH_SIDE_X_OFFSET = 3.375
    # COSTAR_NOTCH_SWITCH_SIDE_X_OFFSET = 1.65
    # SIDE_NOTCH_FAR_SIDE_X_OFFSET = 4.2

    CORNER_ORDER = ['top_left', 'top_right', 'bottom_right', 'bottom_left']

    def __init__(self, props: CellProperties, parameters: Parameters) -> None:

        self.logger = logging.getLogger().getChild(__name__)

        self.props = props
        self.parameters = parameters

        # Set by subclasses (Switch, Support, ...) to the built OpenSCAD geometry.
        self.solid: OpenSCADObject

        self.rotation_info: dict[str, dict[str, float]] = {
            'top_left': {
                'order': 0
            },
            'top_right': {
                'order': 1
            },
            'bottom_left': {
                'order': 3
            },
            'bottom_right': {
                'order': 2
            }
        }

        if self.rotation != 0.0:
            self.build_rotation_info()


    @property
    def x(self) -> float:
        return self.props.x

    @property
    def y(self) -> float:
        return self.props.y

    @property
    def w(self) -> float:
        return self.props.w

    @property
    def h(self) -> float:
        return self.props.h

    @property
    def rotation(self) -> float:
        return self.props.rotation

    @property
    def z_offset(self) -> float:
        return self.props.z_offset

    @property
    def cell_value(self) -> str:
        return self.props.cell_value

    @property
    def x_min(self) -> float:
        return self.props.x_min

    @property
    def x_max(self) -> float:
        return self.props.x_max

    @property
    def y_min(self) -> float:
        return self.props.y_min

    @property
    def y_max(self) -> float:
        return self.props.y_max

    @property
    def center_x(self) -> float:
        return self.props.center_x

    @property
    def center_y(self) -> float:
        return self.props.center_y

    @property
    def end_x(self) -> float:
        return self.props.end_x

    @property
    def end_y(self) -> float:
        return self.props.end_y

    @property
    def switch_length(self) -> float:
        return self.props.switch_length

    @property
    def vertical(self) -> bool:
        return self.props.vertical

    @property
    def x_start_mm(self) -> float:
        return self.parameters.U(self.props.x)

    @property
    def x_end_mm(self) -> float:
        return self.x_start_mm + self.parameters.U(self.props.w)

    @property
    def y_start_mm(self) -> float:
        return self.parameters.U(self.props.y)

    @property
    def y_end_mm(self) -> float:
        return self.y_start_mm + self.parameters.U(self.props.h)

    @property
    def h_mm(self) -> float:
        return self.parameters.U(self.props.h)

    @property
    def w_mm(self) -> float:
        return self.parameters.U(self.props.w)

    # @staticmethod
    # def u(u_value):
    #     return u_value * Cell.SWITCH_SPACING

    def __str__(self) -> str:
        return '%s (%f, %f)' % (self.cell_value, self.x, self.y)

    def get(self) -> OpenSCADObject:
        return self.solid

    def get_moved(self) -> OpenSCADObject:
        return up(self.z_offset) ( right(self.x_start_mm) ( forward(self.y_start_mm) ( self.solid ) ) )

    def get_start_x(self) -> float: 
        if self.rotation == 0.0:
            return self.x
        else:
            return self.get_rotated_start_x()

    
    def get_start_y(self) -> float:
        if self.rotation == 0.0:
            return self.y
        else:
            return self.get_rotated_start_y()

    def get_end_x(self) -> float: 
        if self.rotation == 0.0:
            return self.end_x
        else:
            return self.get_rotated_end_x()

    
    def get_end_y(self) -> float:
        if self.rotation == 0.0:
            return self.end_y
        else:
            return self.get_rotated_end_y()

    def get_rotated_start_x(self) -> float:
        min_x = 1000.0
        for corner_name in self.CORNER_ORDER:
            if 'rotated_x' in self.rotation_info[corner_name].keys():
                rotated_x = float(self.rotation_info[corner_name]['rotated_x'])
                if rotated_x < min_x:
                    min_x = rotated_x

        return min_x

    def get_rotated_end_x(self) -> float:
        max_x = -1000.0
        for corner_name in self.CORNER_ORDER:
            if 'rotated_x' in self.rotation_info[corner_name].keys():
                rotated_x = float(self.rotation_info[corner_name]['rotated_x'])
                if rotated_x > max_x:
                    max_x = rotated_x

        return max_x

    def get_rotated_start_y(self) -> float:
        max_y = -1000.0
        for corner_name in self.CORNER_ORDER:
            if 'rotated_y' in self.rotation_info[corner_name].keys():
                rotated_y = float(self.rotation_info[corner_name]['rotated_y'])
                if rotated_y > max_y:
                    max_y = rotated_y
        
        return max_y

    def get_rotated_end_y(self) -> float:
        min_y = 1000.0
        for corner_name in self.CORNER_ORDER:
            if 'rotated_y' in self.rotation_info[corner_name].keys():
                rotated_y = float(self.rotation_info[corner_name]['rotated_y'])
                if rotated_y < min_y:
                    min_y = rotated_y
        
        return min_y

    def hypotenuse(self, adjacent: float, opposite: float) -> float:
        return math.sqrt((float(adjacent) ** 2) + (float(opposite) ** 2))

    def get_hypotenuse_start_angle(self, adjacent: float, opposite: float) -> float:
        try:
            tan = float(opposite) / float(adjacent)
        except ZeroDivisionError:
            
            # angle = 90
            if self.rotation < 0.0:
                angle = 90.0
            else:
                angle = -90.0
            
            return angle

        angle = math.atan( tan )
        angle = math.degrees(angle)
        return angle

    def get_opposite(self, angle: float, hypotenuse: float) -> float:
        sin_angle = math.sin(math.radians(angle))
        opposite = sin_angle * hypotenuse
        if self.rotation < 0.0:
            opposite = -(opposite)
        
        return opposite

    def get_adjacent(self, angle: float, hypotenuse: float) -> float:
        cos_angle = math.cos(math.radians(angle))
        adjacent = cos_angle * hypotenuse
        if self.rotation < 0.0:
            adjacent = -(adjacent)
        
        return adjacent


    def get_rotation_info_points(self) -> list[list[float]]:
        points_orig = []
        points = []
        
        for corner_name in self.CORNER_ORDER:
            # self.logger.debug(corner_name)
            points_orig.append([self.rotation_info[corner_name]['rotated_x'], self.rotation_info[corner_name]['rotated_y']])
            points.append([self.parameters.U(self.rotation_info[corner_name]['rotated_x']), self.parameters.U(self.rotation_info[corner_name]['rotated_y'])])
            
        return points
    
    
    def build_rotation_info(self) -> None:

        # if self.cell_value in ('CC', 'DD', 'HH', 'II', 'JJ', 'LL'):
        #     self.logger.debug('Build Rotation Info for key %s', str(self))

        for corner_name in self.rotation_info.keys():
            adjacent = 0.0
            opposite = 0.0
            if corner_name == 'top_left':
                adjacent = self.x_min
                opposite = self.y_max
            elif corner_name == 'top_right':
                adjacent = self.x_max
                opposite = self.y_max
            elif corner_name == 'bottom_left':
                adjacent = self.x_min
                opposite = self.y_min
            elif corner_name == 'bottom_right':
                adjacent = self.x_max
                opposite = self.y_min

            hypotenuse = self.hypotenuse(adjacent, opposite)
            hypotenuse_start_angle = self.get_hypotenuse_start_angle(adjacent, opposite)
            hypotenuse_rotated_angle = hypotenuse_start_angle - self.rotation

            self.rotation_info[corner_name]['x'] = adjacent
            self.rotation_info[corner_name]['y'] = opposite
            self.rotation_info[corner_name]['hypotenuse'] = hypotenuse
            self.rotation_info[corner_name]['hypotenuse_start_angle'] = hypotenuse_start_angle
            self.rotation_info[corner_name]['hypotenuse_rotated_angle'] = hypotenuse_rotated_angle
            self.rotation_info[corner_name]['rotated_x'] = self.get_adjacent(hypotenuse_rotated_angle, hypotenuse)
            self.rotation_info[corner_name]['rotated_y'] = self.get_opposite(hypotenuse_rotated_angle, hypotenuse)


