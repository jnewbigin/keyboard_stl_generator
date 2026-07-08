

import math
import logging
import sys

from solid import *
from solid.utils import *

from switch import Switch
from support import Support
from support_cutout import SupportCutout
from cell import Cell
from item_collection import ItemCollection
from rotation_collection import RotationCollection
from body import Body
from pcb import PCB
from switch_config import SwitchConfig
from parameters import Parameters
from cable import Cable
from shape_cutout import ShapeCutout



class Keyboard():

    def __init__(self, parameters: Parameters = Parameters()):

        self.parameters = parameters

        self.logger = logging.getLogger().getChild(__name__)
        
        self.modifier_include_list = ['x', 'y', 'w', 'h', 'r', 'rx', 'ry', 'd', 'p']

        self.kerf = self.parameters.kerf

        self.body = None

        self.desired_section_number = -1

        self.cable_hole_up_offset = self.parameters.cable_hole_up_offset
        self.cable_hole_down_offset = self.parameters.cable_hole_down_offset

        self.cable_hole = self.parameters.cable_hole

        self.switch_type = self.parameters.switch_type
        self.stabilizer_type = self.parameters.stabilizer_type

        self.switch_config = self.parameters.switch_config

        self.build_x = math.floor(parameters.x_build_size / self.parameters.switch_spacing)
        self.build_y = math.floor(parameters.y_build_size / self.parameters.switch_spacing)

        self.switch_collection = ItemCollection()
        self.support_collection = ItemCollection()
        self.support_cutout_collection = ItemCollection()
        self.switch_rotation_collection = RotationCollection(self.parameters)
        self.support_rotation_collection = RotationCollection(self.parameters)
        self.support_cutout_rotation_collection = RotationCollection(self.parameters)

        self.custom_polygon_collection = ItemCollection()

        self.switch_cutouts = union()
        self.switch_supports = union()
        self.switch_support_cutouts = union()
        self.rotate_switch_cutout_collection = union()
        self.rotate_support_collection = union()
        self.rotate_support_cutout_collection = union()

        self.custom_polygon_cutout_collection = union()

        self.switch_section_list = [ItemCollection()]
        self.support_section_list = [ItemCollection()]
        self.support_cutout_section_list = [ItemCollection()]

        self.cable = Cable(parameters)



    def process_keyboard_layout(self, keyboard_layout_dict):
        y = 0.0
        rotation = 0.0
        rx = 0.0
        ry = 0.0
        z_offset = 0.0
        # r_x_offset = 0.0
        # r_y_offset = 0.0
        
        for row in keyboard_layout_dict:
            x = 0.0
            w = 1.0
            h = 1.0

            if type(row) == type([]):
                # A flag to be used to ignore non key data from the layout file
                ignore_next = False
                for col in row:               
                    if type(col) == type({}):

                        for key in col.keys():
                            modifier_type = key
                            
                            if modifier_type in self.modifier_include_list:
                                if modifier_type == 'p':
                                    # KLE profile field, repurposed as a per-switch
                                    # plate z-offset in mm. Sticky like rotation:
                                    # applies until changed (set to 0 to stop).
                                    try:
                                        z_offset = float(col[key])
                                    except (TypeError, ValueError):
                                        z_offset = 0.0
                                    continue

                                size = float(col[key])
                                if modifier_type == 'w':
                                    w = size
                                if modifier_type == 'h':
                                    h = size
                                if modifier_type == 'x':
                                    x += size
                                    r_x_offset = size
                                if modifier_type == 'y':
                                    y += size
                                    r_y_offset = size
                                if modifier_type == 'r':
                                    rotation = size
                                    y = 0
                                    x = 0
                                if modifier_type == 'rx':
                                    rx = size
                                if modifier_type == 'ry':
                                    ry = size
                                if modifier_type == 'd':
                                    # self.logger.debug('Ignore next Item')
                                    ignore_next = True
                        
                    elif ignore_next == False:
                        col_escaped = col.encode("unicode_escape").decode("utf-8")
                        # split on newline character and get the lat element in the resulting list
                        col_escaped = col_escaped.split('\\n')[-1]
                        # self.logger.debug('column value: %s', col_escaped)
                        
                        x_offset = x
                        y_offset = -(y)

                        switch = Switch(x_offset, y_offset, w, h, rotation = rotation, z_offset = z_offset, cell_value = col_escaped, switch_config = self.switch_config, parameters = self.parameters)
                        support = Support(x_offset, y_offset, w, h, self.parameters.plate_thickness, self.parameters.support_bar_height, self.parameters.support_bar_width, rotation = rotation, z_offset = z_offset, parameters = self.parameters)
                        support_cutout = SupportCutout(x_offset, y_offset, w, h, self.parameters.plate_thickness, self.parameters.support_bar_height, self.parameters.support_bar_width, rotation = rotation, z_offset = z_offset, parameters = self.parameters)

                        # Create switch cutout and support object without rotation
                        if rotation == 0.0:
                            self.switch_collection.add_item(x_offset, y_offset, switch)    
                            self.support_collection.add_item(x_offset, y_offset, support)
                            self.support_cutout_collection.add_item(x_offset, y_offset, support_cutout)
                            
                            
                        # Create switch cutout and support object without rotation
                        elif rotation != 0.0:
                            self.switch_rotation_collection.add_item(rotation, x_offset, y_offset, switch, rx, ry)
                            self.support_rotation_collection.add_item(rotation, x_offset, y_offset, support, rx, ry)
                            self.support_cutout_rotation_collection.add_item(rotation, x_offset, y_offset, support_cutout, rx, ry)

                        x += w    
                        w = 1.0
                        h = 1.0

                    elif ignore_next == True:
                        ignore_next = False

                y += 1

        self.switch_collection.set_collection_neighbors('global')

        # create sections of the keyboard for usin in splitting for printing
        self.split_keyboard()

    def process_custom_shapes(self):
        

        if self.parameters.custom_polygons is not None:
            for shape in self.parameters.custom_polygons:
                custom_shape_type = shape['type']
                coordinates_list = shape['coordinates']

                for coordinates in coordinates_list:
                    x = coordinates[0]
                    y = coordinates[1]

                    custom_shape = ShapeCutout(x, y, custom_shape_type, shape, self.parameters)
                    self.custom_polygon_collection.add_item(x, y, custom_shape)


    def get_assembly(self, top = False, bottom = False, all = True, plate_only = False, case_bottom = False):
        
        
        # Init top_assembly and bottom_assembly objects
        top_assembly = union()
        bottom_assembly = union()

        # Get the x and y bounds of the switches
        (min_x, max_x, max_y, min_y) = self.switch_collection.get_collection_bounds()

        # Add all switch and support collection objects to switch and support attributes
        support_collection = self.support_collection
        switch_collection = self.switch_collection
        support_cutout_collection = self.support_cutout_collection

        if self.desired_section_number > -1:
            support_collection = self.support_section_list[self.desired_section_number]
            switch_collection = self.switch_section_list[self.desired_section_number]
            support_cutout_collection = self.support_cutout_section_list[self.desired_section_number]

        self.switch_supports += support_collection.get_moved_union()
        self.switch_cutouts += switch_collection.get_moved_union()
        self.switch_support_cutouts += support_cutout_collection.get_moved_union()

        if self.parameters.custom_polygons is not None:
            self.custom_polygon_cutout_collection = self.custom_polygon_collection.get_moved_union()

        (rotated_min_x, rotated_max_x, rotated_max_y, rotated_min_y) = self.switch_rotation_collection.get_real_collection_bounds()

        self.logger.debug('rotation_bounds: rotated_min_x: %f, rotated_max_x: %f, rotated_max_y: %f, rotated_min_y: %f', 
            rotated_min_x, rotated_max_x, rotated_max_y, rotated_min_y)

        if rotated_min_x < min_x:
            min_x = rotated_min_x
        if rotated_max_x > max_x:
            max_x = rotated_max_x
        if rotated_min_y < min_y:
            min_y = rotated_min_y
        if rotated_max_y > max_y:
            max_y = rotated_max_y

        # Union together all rotated switch cutouts 
        for rotation in self.switch_rotation_collection.get_rotation_list():
            self.switch_cutouts += self.switch_rotation_collection.get_rotated_moved_union(rotation)
            self.switch_supports += self.support_rotation_collection.get_rotated_moved_union(rotation)
            self.switch_support_cutouts += self.support_cutout_rotation_collection.get_rotated_moved_union(rotation)

        # Set body dimensions
        self.parameters.set_dimensions(max_x, min_y, min_x, max_y)

        # Init body object
        self.body = Body(self.parameters)

        # Init PCB object
        # if self.parameters.custom_pcb == True:
        self.pcb = PCB(self.parameters)
        pcb_model = self.pcb.get_model()

        # Add case to top_assembly
        top_assembly += self.body.case(plate_only = plate_only, walls_only = case_bottom)

        if self.parameters.simple_test == False and case_bottom == False:
            # Remove switch suport cutouts
            top_assembly -= self.switch_support_cutouts

            # Add switch supports and remove switch cutouts
            top_assembly += self.switch_supports
            top_assembly -= self.switch_cutouts
        
        # Generate screw hole related objects
        screw_hole_collection = None
        screw_hole_body_collection = None
        screw_hole_body_scaled_collection = None
        if self.parameters.screw_count > 0:
            screw_hole_collection, screw_hole_body_collection, screw_hole_body_scaled_collection = self.body.screw_hole_objects(tap = bottom or case_bottom)

            # Remove screw holes from top top_assembly
            top_assembly -= screw_hole_collection

            bottom_assembly = screw_hole_body_collection
            bottom_assembly -= screw_hole_collection

        body_block = self.body.case(body_block_only = True)
        
        # Remove items marked as not part of desired section
        if self.desired_section_number > -1:
            top_assembly -= self.get_top_section_remove_block(self.desired_section_number)
            # TODO
            bottom_section_inclusion = self.get_bottom_section_remove_block(self.desired_section_number)
            # bottom_assembly -= self.get_bottom_section_remove_block(self.desired_section_number)
        

        self.custom_polygon_cutout_collection = up(self.parameters.case_height_base_removed - (self.parameters.plate_thickness / 2)) (
            self.custom_polygon_cutout_collection
        )
        # Move top_assembly so that the bottom left sits at 0, 0, 0
        top_assembly = up(self.parameters.case_height_base_removed - (self.parameters.plate_thickness / 2)) (
            forward(self.parameters.real_max_y + self.parameters.bottom_margin) (
                right(self.parameters.left_margin) (
                    top_assembly 
                )
            )
        )

        top_assembly += up(self.parameters.case_height_base_removed) ( #) - (self.parameters.plate_thickness / 2)) (
            right(0) (
                pcb_model 
            )
        )

        bottom_assembly = up(self.parameters.case_height_base_removed - (self.parameters.plate_thickness / 2)) (
            forward(self.parameters.real_max_y + self.parameters.bottom_margin) (
                right(self.parameters.left_margin) (
                    bottom_assembly
                )
            )
        )
        
        if screw_hole_collection is not None:
            screw_hole_collection = up(self.parameters.case_height_base_removed - (self.parameters.plate_thickness / 2)) (
                forward(self.parameters.real_max_y + self.parameters.bottom_margin) (
                    right(self.parameters.left_margin) (
                        screw_hole_collection
                    )
                )
            )
            screw_hole_body_collection = up(self.parameters.case_height_base_removed - (self.parameters.plate_thickness / 2)) (
                forward(self.parameters.real_max_y + self.parameters.bottom_margin) (
                    right(self.parameters.left_margin) (
                        screw_hole_body_collection
                    )
                )
            )
            screw_hole_body_scaled_collection = up(self.parameters.case_height_base_removed - (self.parameters.plate_thickness / 2)) (
                forward(self.parameters.real_max_y + self.parameters.bottom_margin) (
                    right(self.parameters.left_margin) (
                        screw_hole_body_scaled_collection
                    )
                )
            )
        
        body_block = up(self.parameters.case_height_base_removed - (self.parameters.plate_thickness / 2)) (
            forward(self.parameters.real_max_y + self.parameters.bottom_margin) (
                right(self.parameters.left_margin) (
                    body_block
                )
            )
        )

        if self.desired_section_number > -1:
            bottom_section_inclusion = up(self.parameters.case_height_base_removed - (self.parameters.plate_thickness / 2)) (
                forward(self.parameters.real_max_y + self.parameters.bottom_margin) (
                    right(self.parameters.left_margin) (
                        bottom_section_inclusion
                    )
                )
            )

        # Create block that will remove material to make case bottom flat
        bottom_diff_plate_width = (self.parameters.real_max_x + self.parameters.right_margin + self.parameters.left_margin) * 2
        bottom_diff_plate_height = (self.parameters.real_max_y + self.parameters.top_margin + self.parameters.bottom_margin) * 2
        bottom_diff_plate = down(self.parameters.case_height_extra * 2) (
            back(bottom_diff_plate_height / 4) (
                left(bottom_diff_plate_width / 4) (
                    cube([ bottom_diff_plate_width, bottom_diff_plate_height, self.parameters.case_height_extra * 2 ])
                )
            )
        )

        # Remove space for a cable to pass through the body
        top_assembly -= self.cable.get_cable_hole()

        # Interesect objects with a test block to handle testing specific parts of a model
        if self.parameters.test_block == True:
            test_block_x = self.parameters.test_block_x_end - self.parameters.test_block_x_start
            test_block_y = self.parameters.test_block_y_end - self.parameters.test_block_y_start
            test_block_z = self.parameters.test_block_z_end - self.parameters.test_block_z_start

            self.logger.info('test_block_x: %f, test_block_y: %f, test_block_z: %f', test_block_x, test_block_y, test_block_z)

            test_block = translate(
                [
                    self.parameters.test_block_x_start, 
                    self.parameters.test_block_y_start, 
                    self.parameters.test_block_z_start
                ]
            ) (
                cube([test_block_x, test_block_y, test_block_z])
            )

            top_assembly *= test_block
            bottom_assembly *= test_block
            screw_hole_collection *= test_block
            screw_hole_body_collection *= test_block
            screw_hole_body_scaled_collection *= test_block
            body_block *= test_block

        # Remove thw custom cutouts before tilting
        top_assembly -= self.custom_polygon_cutout_collection

        # Tile the body if desired
        if self.parameters.tilt > 0.0:
            top_assembly = rotate(self.parameters.tilt, [1, 0, 0]) ( top_assembly )
            bottom_assembly = rotate(self.parameters.tilt, [1, 0, 0]) ( bottom_assembly )
            if screw_hole_collection is not None:
                screw_hole_collection = rotate(self.parameters.tilt, [1, 0, 0]) ( screw_hole_collection )
                screw_hole_body_collection = rotate(self.parameters.tilt, [1, 0, 0]) ( screw_hole_body_collection )
                screw_hole_body_scaled_collection = rotate(self.parameters.tilt, [1, 0, 0]) ( screw_hole_body_scaled_collection )
            body_block = rotate(self.parameters.tilt, [1, 0, 0]) ( body_block )

        # Remove bottom block to make bottom of case flat. For a fused walls+bottom
        # shell the walls must reach down to the bottom cover so the two overlap and
        # join into a single solid instead of merely touching at z = 0.
        if case_bottom == True:
            top_assembly -= down(self.parameters.bottom_cover_thickness) ( bottom_diff_plate )
        else:
            top_assembly -= bottom_diff_plate
        bottom_assembly -= down(self.parameters.bottom_cover_thickness) ( bottom_diff_plate )



        # bottom_assembly += self.body.bottom_cover()
        # bottom_assembly += body_block
        bottom_assembly += self.body.bottom_cover() * body_block
        if self.desired_section_number > -1:
            bottom_assembly *= bottom_section_inclusion

        if screw_hole_collection is not None:
            bottom_assembly -= screw_hole_collection

        # # TEST ####
        # # Union together all rotated supports
        # rotation = list(self.support_rotation_collection.get_rotation_list())[0]
        # # top_assembly = self.support_rotation_collection.get_union(rotation)
        # # top_assembly -= self.switch_rotation_collection.get_union(rotation)
        # rx_list = list(self.support_rotation_collection.get_rx_list(rotation))
        # # self.logger.debug('rotation %f, rx_list: %s', rotation, str(rx_list))
        # ry_list = list(self.support_rotation_collection.get_ry_list_in_rx(rotation, rx_list[0]))
        # rx = rx_list[0]
        # ry = ry_list[0]
        # self.logger.debug('rotation %f, rx_list: %s, ry_list: %s', rotation, str(rx_list), str(ry_list))
        # top_assembly = self.support_rotation_collection.get_rotated_union(rotation)
        # top_assembly -= self.switch_rotation_collection.get_rotated_union(rotation)
        # rotation_max_x = self.switch_rotation_collection.get_max_x(rotation, rx, ry)
        # (rotation_min_x, rotation_max_x, rotation_max_y, rotation_min_y) = self.switch_rotation_collection.get_real_collection_bounds()
        # self.logger.debug('rotation %f, rotation_min_x: %f, rotation_max_x: %f, rotation_max_y: %f, rotation_min_y: %f', rotation, rotation_min_x, rotation_max_x, rotation_max_y, rotation_min_y)
        # # top_assembly = self.support_rotation_collection.get_rotated_moved_union(rotation)
        # # top_assembly -= self.switch_rotation_collection.get_rotated_moved_union(rotation)

        # top_assembly = self.switch_rotation_collection.draw_rotated_items(rotation)
        
        # return top_assembly
        # ############


        if top == True or plate_only == True:
            if screw_hole_body_scaled_collection is not None:
                return (top_assembly - screw_hole_body_scaled_collection)
            else:
                return top_assembly
        elif bottom == True:
            return bottom_assembly
        elif case_bottom == True:
            # Case walls fused with the bottom cover, no plate (tray-mount shell)
            top_assembly += bottom_assembly
            return top_assembly
        else:
            top_assembly += bottom_assembly
            return top_assembly
        
    
    # def get_cable_hole(self):

    #     if self.cable_hole == True:
    #         return up(self.parameters.case_height_base_removed - (self.parameters.cable_hole_height / 2) - self.parameters.plate_thickness - self.cable_hole_down_offset ) (
    #             right(self.parameters.left_margin + (self.parameters.real_max_x / 2)) ( 
    #                 forward(self.parameters.bottom_margin + self.parameters.top_margin + self.parameters.real_max_y) ( 
    #                     cube([self.parameters.cable_hole_width, self.parameters.case_wall_thickness * 2, self.parameters.cable_hole_height], center = True) 
    #                 ) 
    #             ) 
    #         )
    #     else:
    #         return union()


    def split_keyboard(self):
        

        (min_x, max_x, max_y, min_y) = self.switch_collection.get_collection_bounds()
        self.logger.debug('max_x: %d, min_y: %d', max_x, min_y)
        self.logger.debug('build_x: %d, build_y: %d', self.build_x, self.build_y)

        x_parts = math.ceil(max_x / self.build_x)
        y_parts = math.ceil(abs(min_y) / self.build_y)
        self.logger.debug('x_parts: %d, y_parts: %d', x_parts, y_parts)

        # Walk the keys column by column (ascending x, matching the seam logic in
        # _assign_x_sections) and describe each column as its left edge in mm plus
        # the right edge of every key in it. The pure seam math decides which
        # section each key belongs to; distributing the actual items is separate.
        column_keys = [(x, self.switch_collection.get_sorted_y_list_in_x(x))
                       for x in self.switch_collection.get_sorted_x_list()]
        columns = [
            (self.parameters.U(x),
             [self.switch_collection.get_item(x, y).x_end_mm for y in ys])
            for (x, ys) in column_keys
        ]

        assignments = self._balanced_x_sections(
            columns, self.parameters.x_build_size, self.parameters.left_margin)

        section_count = max(self._count_sections(assignments), 1)
        while len(self.switch_section_list) < section_count:
            self.switch_section_list.append(ItemCollection())
            self.support_section_list.append(ItemCollection())
            self.support_cutout_section_list.append(ItemCollection())

        for (x, ys), column_sections in zip(column_keys, assignments):
            for y, section in zip(ys, column_sections):
                self.switch_section_list[section].add_item(x, y, self.switch_collection.get_item(x, y))
                self.support_section_list[section].add_item(x, y, self.support_collection.get_item(x, y))
                self.support_cutout_section_list[section].add_item(x, y, self.support_cutout_collection.get_item(x, y))

        for section in self.switch_section_list:
            section.set_collection_neighbors()

    @staticmethod
    def _assign_x_sections(columns, threshold, left_margin):
        # Decide which printable x-section each key belongs to, working purely in
        # millimetres so the logic can be unit tested without a Keyboard.
        #
        #   columns:   ascending-x list of (x_start_mm, [x_end_mm, ...]) - one entry
        #              per x column, listing the right edge of every key in it.
        #   threshold: the widest a section's x-extent (right edge + left_margin,
        #              measured from the section start) may grow before the next
        #              key opens a new section.
        #   returns:   a list parallel to columns; each element is a list of section
        #              indices (one per key). Section count is max index + 1.
        #
        # The section start only advances at a column boundary, so a wide key
        # straddling the seam is kept whole in the next section rather than being
        # cut.
        current_x_start = 0.0
        current_section = 0
        next_section = 0
        section_start = {}
        assignments = []
        for x_start_mm, x_ends in columns:
            column_sections = []
            for x_end_mm in x_ends:
                reach = x_end_mm + left_margin - current_x_start
                if reach < threshold:
                    section = current_section
                elif reach > threshold and next_section > current_section:
                    section = next_section
                else:
                    next_section = current_section + 1
                    section = next_section
                section_start.setdefault(section, x_start_mm)
                column_sections.append(section)
            assignments.append(column_sections)
            if next_section > current_section:
                current_x_start = section_start[next_section]
                current_section = next_section
        return assignments

    @staticmethod
    def _count_sections(assignments):
        return max((s for column in assignments for s in column), default=-1) + 1

    @staticmethod
    def _balanced_x_sections(columns, x_build_size, left_margin):
        # Packing greedily up to the full plate width uses the fewest sections but
        # fills each to the brim, leaving a thin remainder (e.g. a 27.75u board on a
        # 300mm plate splits 11.5u / 15.25u / 2u). Section count is monotonic in the
        # threshold, so keep the greedy section count but re-pack with the smallest
        # threshold that still yields it - which minimises the widest section and
        # spreads the keys as evenly as the plate and un-cuttable wide keys allow.
        target_count = Keyboard._count_sections(
            Keyboard._assign_x_sections(columns, x_build_size, left_margin))
        if target_count <= 1:
            return Keyboard._assign_x_sections(columns, x_build_size, left_margin)

        low, high = 0.0, float(x_build_size)
        for _ in range(40):
            mid = (low + high) / 2
            count = Keyboard._count_sections(
                Keyboard._assign_x_sections(columns, mid, left_margin))
            if count <= target_count:
                high = mid
            else:
                low = mid

        assignments = Keyboard._assign_x_sections(columns, high, left_margin)
        if Keyboard._count_sections(assignments) != target_count:
            # The search converged just below a step; fall back to the plate width.
            return Keyboard._assign_x_sections(columns, x_build_size, left_margin)
        return assignments

    def get_top_section_remove_block(self, section_number):
        section = self.switch_section_list[section_number]

        self.logger.debug('Get Section %d', section_number)

        (min_x, max_x, max_y, min_y) = section.get_collection_bounds()
        self.logger.debug('Section Bounds: min_x: %f, max_x: %f, max_y: %f, min_y: %f', min_x, max_x, max_y, min_y)

        remove_block_height = self.parameters.case_height_base_removed * 4
        remove_block_z_offset = remove_block_height / 2
        remove_block_length = self.parameters.real_max_x

        section_has_left_global_neighbor = section.has_global_left_neighbor_section()

        # Carve the section out of the plate by clipping every elementary y-band
        # (key rows, empty spacer rows, rows this section owns no keys in, and the
        # top/bottom margins) down to the section's x-extent. The per-band
        # staircase and interlock-seam logic lives in get_section_x_clip.
        return self.get_section_x_clip(
            section, min_x, max_x, section_has_left_global_neighbor,
            remove_block_length, remove_block_height, remove_block_z_offset)

    def section_key_seam_bands(self, section, min_x, max_x, section_has_left_global_neighbor, remove_block_length):
        # For every key in the section return its y-band and the x at which the
        # section's kept plate ends on the right and starts on the left (the
        # interlock seam positions used by get_section_x_clip).
        #
        # The interlock seam between two sections sits halfway between the last
        # key of one section and the first key of the next, so the pieces meet
        # with no gap and no overlap. A keyless gap (e.g. beside the spacebar) is
        # therefore filled - half by each neighbouring section - reproducing the
        # solid whole-board plate instead of leaving a void. For adjacent keys
        # the halfway point is right at the key edge, giving the usual tight
        # interlock. (An earlier version capped this overhang to a small tab,
        # which orphaned the middle of a big gap and left it without plate.)
        bands = []
        for rx in section.get_rx_list():
            for ry in section.get_ry_list_in_rx(rx):
                for x in section.get_x_list_in_rx_ry(rx, ry):
                    for y in section.get_y_list_in_rx_ry_x(x, rx, ry):
                        item: Switch = section.get_item(x, y)

                        right_keep = self.parameters.U(item.x + item.w)
                        if item.has_neighbor('right', 'global') == True:
                            neighbor_offset = item.get_neighbor_offset('right', 'global')
                            right_keep += self.parameters.U(neighbor_offset / 2)
                        else:
                            right_keep += self.parameters.U(max_x - item.end_x)

                        left_keep = remove_block_length
                        if item.has_neighbor('left', 'global') == True:
                            left_keep = self.parameters.U(item.x)
                            neighbor_offset = item.get_neighbor_offset('left', 'global')
                            if neighbor_offset > 0.0:
                                left_keep -= self.parameters.U(neighbor_offset / 2)
                        elif section_has_left_global_neighbor == True:
                            left_keep = self.parameters.U(min_x)

                        bands.append({
                            'y_lo': item.y - item.h,
                            'y_hi': item.y,
                            'right_keep': right_keep,
                            'left_keep': left_keep,
                        })
        return bands

    def get_section_x_clip(self, section, min_x, max_x, section_has_left_global_neighbor, remove_block_length, remove_block_height, remove_block_z_offset):
        clip = union()

        bands = self.section_key_seam_bands(section, min_x, max_x, section_has_left_global_neighbor, remove_block_length)
        if len(bands) == 0:
            return clip

        # Sweep the full board height (plus margins) and clip every elementary
        # y-band, so key rows, empty spacer rows and the top/bottom margins are
        # all clipped to the section's x-extent. A section may own no keys in
        # some rows (e.g. the bottom row) yet its plate still spans the whole
        # board, which is what left the "extra long" full-width strips.
        (board_min_x, board_max_x, board_max_y, board_min_y) = self.switch_collection.get_collection_bounds()

        # The board's own left/right edge must be kept, not clipped. (Derive this
        # from the real board bounds; self.parameters.min_x / max_x are unset.)
        include_left_border = (min_x == board_min_x)
        include_right_border = (max_x == board_max_x)

        top_margin_cells = (self.parameters.top_margin / self.parameters.switch_spacing) + 1
        bottom_margin_cells = (self.parameters.bottom_margin / self.parameters.switch_spacing) + 1
        sweep_lo = board_min_y - bottom_margin_cells
        sweep_hi = board_max_y + top_margin_cells

        key_y_lo = min(b['y_lo'] for b in bands)
        key_y_hi = max(b['y_hi'] for b in bands)
        overall_right = max(b['right_keep'] for b in bands)
        overall_left = min(b['left_keep'] for b in bands)

        edges = set([sweep_lo, sweep_hi])
        for b in bands:
            if sweep_lo < b['y_lo'] < sweep_hi:
                edges.add(b['y_lo'])
            if sweep_lo < b['y_hi'] < sweep_hi:
                edges.add(b['y_hi'])
        edges = sorted(edges)

        for lo, hi in zip(edges, edges[1:]):
            if hi - lo < 1e-9:
                continue
            mid = (lo + hi) / 2.0

            # right_keep is the rightmost seam among the keys covering this band,
            # so no key is ever removed.
            covering = [b for b in bands if b['y_lo'] - 1e-9 <= mid <= b['y_hi'] + 1e-9]
            if len(covering) > 0:
                right_keep = max(b['right_keep'] for b in covering)
                left_keep = min(b['left_keep'] for b in covering)
            elif mid < key_y_lo or mid > key_y_hi:
                # Top / bottom margin: clip to the section's overall extent so the
                # corners never leave an unclipped strip.
                right_keep = overall_right
                left_keep = overall_left
            else:
                # Interior spacer row: continue the staircase from the nearest
                # key band (below preferred, then above).
                below = [b for b in bands if b['y_hi'] <= lo + 1e-9]
                above = [b for b in bands if b['y_lo'] >= hi - 1e-9]
                source = below if len(below) > 0 else above
                right_keep = max(b['right_keep'] for b in source)
                left_keep = min(b['left_keep'] for b in source)

            y_offset = self.parameters.U(lo) - self.kerf
            bar_height = self.parameters.U(hi - lo) + (self.kerf * 2)

            if include_right_border == False:
                clip += down(remove_block_z_offset) ( right(right_keep) ( forward(y_offset) ( cube([remove_block_length, bar_height, remove_block_height]) ) ) )

            if include_left_border == False:
                clip += down(remove_block_z_offset) ( right(left_keep - remove_block_length) ( forward(y_offset) ( cube([remove_block_length, bar_height, remove_block_height]) ) ) )

        return clip

    
    def get_bottom_section_remove_block(self, section_number):
        
        
        # section = self.switch_section_list[section_number]

        self.logger.debug('Get Section %d', section_number)

        self.logger.debug('real_case_width: %f', self.parameters.real_case_width)
        self.logger.debug('real_case_height: %f', self.parameters.real_case_height)

        section_size = self.parameters.real_case_width / self.parameters.bottom_section_count

        self.logger.debug('section_size: %f', section_size)

        start_x = section_size * section_number
        end_x = start_x + section_size

        (start_x, end_x) = self.get_screw_support_interference_offset(start_x, end_x)

        x_offset = start_x - self.parameters.right_margin
        y_offset = self.parameters.real_case_height / 2 + self.parameters.real_case_height
        z_offset = self.parameters.case_height_extra_fill / 2


        width = end_x - start_x
        height = self.parameters.real_case_height * 2
        thickness = self.parameters.case_height_extra_fill * 2

        self.logger.debug('section: %d, x_offset: %f, width: %f, y_offset: %f', section_number, x_offset, width, y_offset)

        return right(x_offset) ( back(y_offset) ( down(z_offset) ( cube([width, height, thickness]) ) ) )



    def get_screw_support_interference_offset(self, start_x, end_x):

        for coord_string in self.body.screw_hole_info.keys():
            screw_hole_info = self.body.screw_hole_info[coord_string]

            screw_x = screw_hole_info['x']
            # screw_y = screw_hole_info['y']

            # self.logger.debug('coord_string: %s, screw_x: %f, screw_y: %f', coord_string, screw_x, screw_y)

            screw_hole_min_x = screw_x - screw_hole_info['support_directions']['left']
            screw_hole_max_x = screw_x + screw_hole_info['support_directions']['right']

            # self.logger.debug('screw_hole_min_x: %f, screw_hole_max_x: %f', screw_hole_min_x, screw_hole_max_x)

            # Left side of section cutout is within a screw hole support
            if start_x > screw_hole_min_x and start_x < screw_hole_max_x:
                # self.logger.debug('Left side in support: old start_x: %f', start_x)
                # Left sie of section cutout is in the middle of a screw hole
                # move the start to the right
                if start_x >= screw_x:
                    start_x = screw_hole_max_x
                if start_x < screw_x:
                    start_x = screw_hole_min_x

                # self.logger.debug('Left side in support: new start_x: %f', start_x)

            # Right side of section cutout is within a screw hole support
            if end_x > screw_hole_min_x and end_x < screw_hole_max_x:
                # self.logger.debug('Right side in support: old end_x: %f', end_x)
                # Right side of section cutout is in the middle of a screw hole
                # move the end to the right
                if end_x >= screw_x:
                    end_x = screw_hole_max_x
                if end_x < screw_x:
                    end_x = screw_hole_min_x

                # self.logger.debug('Right side in support: new end_x: %f', end_x)

        return (start_x, end_x)




    
    def set_section(self, section_number):
        self.desired_section_number = section_number

    def get_top_section_count(self):
        return len(self.switch_section_list)


    def get_top_section_dimensions(self):
        # Width and height in mm for each top section. Width is the section's
        # switch x-span plus the left_margin the splitter reserves for the case
        # wall - i.e. the extent that was checked against x_build_size. Height is
        # the full board height, since sections are only split along x.
        dimensions = []
        for section in self.switch_section_list:
            min_x, max_x, max_y, min_y = section.get_collection_bounds()
            width = self.parameters.U(max_x - min_x) + self.parameters.left_margin
            dimensions.append((width, self.parameters.real_case_height))
        return dimensions


    def get_bottom_section_count(self):
        return self.parameters.bottom_section_count