import itertools
import logging
import math
from collections.abc import Iterator
from typing import Any

from solid import *
from solid import OpenSCADObject
from solid.utils import *

from body import Body
from cable import Cable
from cell import CellProperties
from item_collection import ItemCollection
from parameters import Parameters
from pcb import PCB
from rotation_collection import RotationCollection
from shape_cutout import ShapeCutout
from split_file import SavedSplit, SeamBand, SplitFile, SplitFileError
from support import Support
from support_cutout import SupportCutout
from support_properties import SupportProperties
from switch import Switch


class Keyboard:

    def __init__(self, parameters: Parameters = Parameters()) -> None:

        self.parameters = parameters

        self.logger = logging.getLogger().getChild(__name__)

        self.modifier_include_list = ["x", "y", "w", "h", "r", "rx", "ry", "d", "p"]

        self.kerf = self.parameters.kerf

        self.body: Body | None = None

        self.pcb: PCB | None = None

        self.desired_section_number = -1

        self.cable_hole_up_offset = self.parameters.cable_hole_up_offset
        self.cable_hole_down_offset = self.parameters.cable_hole_down_offset

        self.cable_hole = self.parameters.cable_hole

        self.switch_type = self.parameters.switch_type
        self.stabilizer_type = self.parameters.stabilizer_type

        self.switch_config = self.parameters.switch_config

        self.build_x = math.floor(
            parameters.x_build_size / self.parameters.switch_spacing
        )
        self.build_y = math.floor(
            parameters.y_build_size / self.parameters.switch_spacing
        )

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

        # Section boundaries (mm x) chosen from the real key footprints when the
        # board has rotated clusters. None means the plain non-rotated column
        # splitter decides the seams (see _section_x_boundaries).
        self.planned_boundaries: list[float] | None = None
        self.split_recommendation: str | None = None

        # A split restored from file pins the boundaries for a board the plain
        # column splitter would otherwise re-plan. planned_boundaries stays None
        # for those, so the bottom cover is still divided evenly rather than cut
        # at the plate seams - just into the number of pieces it was saved with.
        self.forced_boundaries: list[float] | None = None
        self.forced_bottom_section_count: int | None = None
        self.saved_split: SavedSplit | None = None

        self.cable = Cable(parameters)

    def process_keyboard_layout(self, keyboard_layout_dict: Any) -> None:
        y = 0.0
        rotation = 0.0
        rx = 0.0
        ry = 0.0
        z_offset = 0.0

        for row in keyboard_layout_dict:
            x = 0.0
            w = 1.0
            h = 1.0

            if isinstance(row, list):
                # A flag to be used to ignore non key data from the layout file
                ignore_next = False
                col: Any
                for col in row:
                    if isinstance(col, dict):

                        key: Any
                        for key in col:
                            modifier_type = key

                            if modifier_type in self.modifier_include_list:
                                if modifier_type == "p":
                                    # KLE profile field, repurposed as a per-switch
                                    # plate z-offset in mm. Sticky like rotation:
                                    # applies until changed (set to 0 to stop).
                                    try:
                                        z_offset = float(col[key])
                                    except (TypeError, ValueError):
                                        z_offset = 0.0
                                    continue

                                size = float(col[key])
                                if modifier_type == "w":
                                    w = size
                                if modifier_type == "h":
                                    h = size
                                if modifier_type == "x":
                                    x += size
                                if modifier_type == "y":
                                    y += size
                                if modifier_type == "r":
                                    rotation = size
                                    y = 0
                                    x = 0
                                if modifier_type == "rx":
                                    rx = size
                                if modifier_type == "ry":
                                    ry = size
                                if modifier_type == "d":
                                    # self.logger.debug('Ignore next Item')
                                    ignore_next = True

                    elif not ignore_next:
                        col_escaped = col.encode("unicode_escape").decode("utf-8")
                        # split on newline character and get the lat element in the resulting list
                        col_escaped = col_escaped.split("\\n")[-1]
                        # self.logger.debug('column value: %s', col_escaped)

                        x_offset = x
                        y_offset = -(y)

                        switch_props = CellProperties(
                            x_offset,
                            y_offset,
                            w,
                            h,
                            rotation=rotation,
                            z_offset=z_offset,
                            cell_value=col_escaped,
                        )
                        support_props = CellProperties(
                            x_offset,
                            y_offset,
                            w,
                            h,
                            rotation=rotation,
                            z_offset=z_offset,
                        )

                        switch = Switch(
                            switch_props,
                            self.parameters,
                            switch_config=self.switch_config,
                        )
                        support = Support(
                            support_props,
                            SupportProperties.from_parameters(self.parameters),
                            self.parameters,
                        )
                        support_cutout = SupportCutout(
                            support_props,
                            SupportProperties.from_parameters(
                                self.parameters, set_to_origin=False
                            ),
                            self.parameters,
                        )

                        # Create switch cutout and support object without rotation
                        if rotation == 0.0:
                            self.switch_collection.add_item(x_offset, y_offset, switch)
                            self.support_collection.add_item(
                                x_offset, y_offset, support
                            )
                            self.support_cutout_collection.add_item(
                                x_offset, y_offset, support_cutout
                            )

                        # Create switch cutout and support object without rotation
                        elif rotation != 0.0:
                            self.switch_rotation_collection.add_item(
                                rotation, x_offset, y_offset, switch, rx, ry
                            )
                            self.support_rotation_collection.add_item(
                                rotation, x_offset, y_offset, support, rx, ry
                            )
                            self.support_cutout_rotation_collection.add_item(
                                rotation, x_offset, y_offset, support_cutout, rx, ry
                            )

                        x += w
                        w = 1.0
                        h = 1.0

                    elif ignore_next:
                        ignore_next = False

                y += 1

        self.switch_collection.set_collection_neighbors("global")

        # create sections of the keyboard for usin in splitting for printing
        self.split_keyboard()

    def process_custom_shapes(self) -> None:

        if self.parameters.custom_polygons is not None:
            for shape in self.parameters.custom_polygons:
                custom_shape_type = shape["type"]
                coordinates_list = shape["coordinates"]

                for coordinates in coordinates_list:
                    x = coordinates[0]
                    y = coordinates[1]

                    custom_shape = ShapeCutout(
                        CellProperties(x, y), custom_shape_type, shape, self.parameters
                    )
                    self.custom_polygon_collection.add_item(x, y, custom_shape)

    def get_assembly(
        self,
        top: bool = False,
        bottom: bool = False,
        all: bool = True,
        plate_only: bool = False,
        case_bottom: bool = False,
    ) -> OpenSCADObject:

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
            support_cutout_collection = self.support_cutout_section_list[
                self.desired_section_number
            ]

        self.switch_supports += support_collection.get_moved_union()
        self.switch_cutouts += switch_collection.get_moved_union()
        self.switch_support_cutouts += support_cutout_collection.get_moved_union()

        if self.parameters.custom_polygons is not None:
            self.custom_polygon_cutout_collection = (
                self.custom_polygon_collection.get_moved_union()
            )

        (rotated_min_x, rotated_max_x, rotated_max_y, rotated_min_y) = (
            self.switch_rotation_collection.get_real_collection_bounds()
        )

        self.logger.debug(
            "rotation_bounds: rotated_min_x: %f, rotated_max_x: %f, rotated_max_y: %f, rotated_min_y: %f",
            rotated_min_x,
            rotated_max_x,
            rotated_max_y,
            rotated_min_y,
        )

        min_x = min(min_x, rotated_min_x)
        max_x = max(max_x, rotated_max_x)
        min_y = min(min_y, rotated_min_y)
        max_y = max(max_y, rotated_max_y)

        # Union together all rotated switch cutouts
        for rotation in self.switch_rotation_collection.get_rotation_list():
            self.switch_cutouts += (
                self.switch_rotation_collection.get_rotated_moved_union(rotation)
            )
            self.switch_supports += (
                self.support_rotation_collection.get_rotated_moved_union(rotation)
            )
            self.switch_support_cutouts += (
                self.support_cutout_rotation_collection.get_rotated_moved_union(
                    rotation
                )
            )

        # Set body dimensions
        self.parameters.set_dimensions(max_x, min_y, min_x, max_y)

        # Init body object
        self.body = Body(self.parameters)

        # Init PCB object
        # if self.parameters.custom_pcb == True:
        self.pcb = PCB(self.parameters)
        pcb_model = self.pcb.get_model()

        # Add case to top_assembly
        assert self.body is not None
        top_assembly += self.body.case(plate_only=plate_only, walls_only=case_bottom)

        if not self.parameters.simple_test and not case_bottom:
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
            assert self.body is not None
            (
                screw_hole_collection,
                screw_hole_body_collection,
                screw_hole_body_scaled_collection,
            ) = self.body.screw_hole_objects(tap=bottom or case_bottom)

            # Remove screw holes from top top_assembly
            top_assembly -= screw_hole_collection

            bottom_assembly = screw_hole_body_collection
            bottom_assembly -= screw_hole_collection

        assert self.body is not None
        body_block = self.body.case(body_block_only=True)

        # Remove items marked as not part of desired section
        if self.desired_section_number > -1:
            top_assembly -= self.get_top_section_remove_block(
                self.desired_section_number
            )
            # TODO
            bottom_section_inclusion = self.get_bottom_section_remove_block(
                self.desired_section_number
            )
            # bottom_assembly -= self.get_bottom_section_remove_block(self.desired_section_number)

        assert self.parameters.case_height_base_removed is not None
        self.custom_polygon_cutout_collection = up(
            self.parameters.case_height_base_removed
            - (self.parameters.plate_thickness / 2)
        )(self.custom_polygon_cutout_collection)
        # Move top_assembly so that the bottom left sits at 0, 0, 0
        top_assembly = up(
            self.parameters.case_height_base_removed
            - (self.parameters.plate_thickness / 2)
        )(
            forward(self.parameters.real_max_y + self.parameters.bottom_margin)(
                right(self.parameters.left_margin)(top_assembly)
            )
        )

        top_assembly += up(
            self.parameters.case_height_base_removed
        )(  # ) - (self.parameters.plate_thickness / 2)) (
            right(0)(pcb_model)
        )

        bottom_assembly = up(
            self.parameters.case_height_base_removed
            - (self.parameters.plate_thickness / 2)
        )(
            forward(self.parameters.real_max_y + self.parameters.bottom_margin)(
                right(self.parameters.left_margin)(bottom_assembly)
            )
        )

        if screw_hole_collection is not None:
            assert screw_hole_body_collection is not None
            assert screw_hole_body_scaled_collection is not None
            screw_hole_collection = up(
                self.parameters.case_height_base_removed
                - (self.parameters.plate_thickness / 2)
            )(
                forward(self.parameters.real_max_y + self.parameters.bottom_margin)(
                    right(self.parameters.left_margin)(screw_hole_collection)
                )
            )
            screw_hole_body_collection = up(
                self.parameters.case_height_base_removed
                - (self.parameters.plate_thickness / 2)
            )(
                forward(self.parameters.real_max_y + self.parameters.bottom_margin)(
                    right(self.parameters.left_margin)(screw_hole_body_collection)
                )
            )
            screw_hole_body_scaled_collection = up(
                self.parameters.case_height_base_removed
                - (self.parameters.plate_thickness / 2)
            )(
                forward(self.parameters.real_max_y + self.parameters.bottom_margin)(
                    right(self.parameters.left_margin)(
                        screw_hole_body_scaled_collection
                    )
                )
            )

        body_block = up(
            self.parameters.case_height_base_removed
            - (self.parameters.plate_thickness / 2)
        )(
            forward(self.parameters.real_max_y + self.parameters.bottom_margin)(
                right(self.parameters.left_margin)(body_block)
            )
        )

        if self.desired_section_number > -1:
            bottom_section_inclusion = up(
                self.parameters.case_height_base_removed
                - (self.parameters.plate_thickness / 2)
            )(
                forward(self.parameters.real_max_y + self.parameters.bottom_margin)(
                    right(self.parameters.left_margin)(bottom_section_inclusion)
                )
            )

        # Create block that will remove material to make case bottom flat
        bottom_diff_plate_width = (
            self.parameters.real_max_x
            + self.parameters.right_margin
            + self.parameters.left_margin
        ) * 2
        bottom_diff_plate_height = (
            self.parameters.real_max_y
            + self.parameters.top_margin
            + self.parameters.bottom_margin
        ) * 2
        bottom_diff_plate = down(self.parameters.case_height_extra * 2)(
            back(bottom_diff_plate_height / 4)(
                left(bottom_diff_plate_width / 4)(
                    cube(
                        [
                            bottom_diff_plate_width,
                            bottom_diff_plate_height,
                            self.parameters.case_height_extra * 2,
                        ]
                    )
                )
            )
        )

        # Remove space for a cable to pass through the body
        top_assembly -= self.cable.get_cable_hole()

        # Interesect objects with a test block to handle testing specific parts of a model
        if self.parameters.test_block:
            test_block_x = (
                self.parameters.test_block_x_end - self.parameters.test_block_x_start
            )
            test_block_y = (
                self.parameters.test_block_y_end - self.parameters.test_block_y_start
            )
            test_block_z = (
                self.parameters.test_block_z_end - self.parameters.test_block_z_start
            )

            self.logger.info(
                "test_block_x: %f, test_block_y: %f, test_block_z: %f",
                test_block_x,
                test_block_y,
                test_block_z,
            )

            test_block = translate(
                [
                    self.parameters.test_block_x_start,
                    self.parameters.test_block_y_start,
                    self.parameters.test_block_z_start,
                ]
            )(cube([test_block_x, test_block_y, test_block_z]))

            top_assembly *= test_block
            bottom_assembly *= test_block
            assert screw_hole_collection is not None
            assert screw_hole_body_collection is not None
            assert screw_hole_body_scaled_collection is not None
            screw_hole_collection *= test_block
            screw_hole_body_collection *= test_block
            screw_hole_body_scaled_collection *= test_block
            body_block *= test_block

        # Remove thw custom cutouts before tilting
        top_assembly -= self.custom_polygon_cutout_collection

        # Tile the body if desired
        if self.parameters.tilt > 0.0:
            top_assembly = rotate(self.parameters.tilt, [1, 0, 0])(top_assembly)
            bottom_assembly = rotate(self.parameters.tilt, [1, 0, 0])(bottom_assembly)
            if screw_hole_collection is not None:
                assert screw_hole_body_collection is not None
                assert screw_hole_body_scaled_collection is not None
                screw_hole_collection = rotate(self.parameters.tilt, [1, 0, 0])(
                    screw_hole_collection
                )
                screw_hole_body_collection = rotate(self.parameters.tilt, [1, 0, 0])(
                    screw_hole_body_collection
                )
                screw_hole_body_scaled_collection = rotate(
                    self.parameters.tilt, [1, 0, 0]
                )(screw_hole_body_scaled_collection)
            body_block = rotate(self.parameters.tilt, [1, 0, 0])(body_block)

        # Remove bottom block to make bottom of case flat. For a fused walls+bottom
        # shell the walls must reach down to the bottom cover so the two overlap and
        # join into a single solid instead of merely touching at z = 0.
        if case_bottom:
            top_assembly -= down(self.parameters.bottom_cover_thickness)(
                bottom_diff_plate
            )
        else:
            top_assembly -= bottom_diff_plate
        bottom_assembly -= down(self.parameters.bottom_cover_thickness)(
            bottom_diff_plate
        )

        # bottom_assembly += self.body.bottom_cover()
        # bottom_assembly += body_block
        assert self.body is not None
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

        if top or plate_only:
            if screw_hole_body_scaled_collection is not None:
                return top_assembly - screw_hole_body_scaled_collection
            return top_assembly
        if bottom:
            return bottom_assembly
        if case_bottom:
            # Case walls fused with the bottom cover, no plate (tray-mount shell)
            top_assembly += bottom_assembly
            return top_assembly
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

    def load_split(self, saved: SavedSplit) -> None:
        # Pin the split to a previously saved one. Must be called before
        # process_keyboard_layout, which is what triggers the split.
        self.saved_split = saved

    def current_split(self) -> SavedSplit:
        return SavedSplit(
            footprint_planned=self.planned_boundaries is not None,
            plate_mm=self.parameters.x_build_size,
            bottom_section_count=self.get_bottom_section_count(),
            boundaries=self._section_x_boundaries(),
            section_widths=[
                width for (width, _height) in self.get_top_section_dimensions()
            ],
            sections=[
                [
                    (SplitFile.round_unit(item.x), SplitFile.round_unit(item.y))
                    for item in self._iter_collection_items(section)
                ]
                for section in self.switch_section_list
            ],
            seams=self.seam_profiles(),
        )

    def split_keyboard(self) -> None:
        if self.saved_split is not None:
            self._split_keyboard_from_saved(self.saved_split)
            return

        # Boards with rotated clusters (split/ergo layouts) can't be sectioned by
        # the plain column splitter below - it only sees the non-rotated keys and
        # would run a seam straight through a rotated cluster. Route those through
        # the footprint-aware planner, which keeps each cluster whole and places
        # the seams in the real gaps. Non-rotated boards keep the original path.
        cluster_spans = self._rotated_cluster_spans()
        if cluster_spans:
            self._split_keyboard_by_footprint(cluster_spans)
            return

        (min_x, max_x, max_y, min_y) = self.switch_collection.get_collection_bounds()
        self.logger.debug("max_x: %d, min_y: %d", max_x, min_y)
        self.logger.debug("build_x: %d, build_y: %d", self.build_x, self.build_y)

        x_parts = math.ceil(max_x / self.build_x)
        y_parts = math.ceil(abs(min_y) / self.build_y)
        self.logger.debug("x_parts: %d, y_parts: %d", x_parts, y_parts)

        # Walk the keys column by column (ascending x, matching the seam logic in
        # _assign_x_sections) and describe each column as its left edge in mm plus
        # the right edge of every key in it. The pure seam math decides which
        # section each key belongs to; distributing the actual items is separate.
        column_keys = [
            (x, self.switch_collection.get_sorted_y_list_in_x(x))
            for x in self.switch_collection.get_sorted_x_list()
        ]
        columns = [
            (
                self.parameters.U(x),
                [self.switch_collection.get_item(x, y).x_end_mm for y in ys],
            )
            for (x, ys) in column_keys
        ]

        assignments = self._balanced_x_sections(
            columns, self.parameters.x_build_size, self.parameters.left_margin
        )

        section_count = max(self._count_sections(assignments), 1)
        while len(self.switch_section_list) < section_count:
            self.switch_section_list.append(ItemCollection())
            self.support_section_list.append(ItemCollection())
            self.support_cutout_section_list.append(ItemCollection())

        for (x, ys), column_sections in zip(column_keys, assignments):
            for y, section in zip(ys, column_sections):
                self.switch_section_list[section].add_item(
                    x, y, self.switch_collection.get_item(x, y)
                )
                self.support_section_list[section].add_item(
                    x, y, self.support_collection.get_item(x, y)
                )
                self.support_cutout_section_list[section].add_item(
                    x, y, self.support_cutout_collection.get_item(x, y)
                )

        for section_collection in self.switch_section_list:
            section_collection.set_collection_neighbors()

    def _rotated_cluster_spans(self) -> list[tuple[float, float]]:
        # Real (post-rotation) x-extent in mm of each rotated cluster, merged
        # where clusters overlap in x. A boundary must never fall inside one of
        # these spans, so the seam can't slice a rotated key. Empty for a plain
        # non-rotated board.
        #
        # Mirror exactly how RotationCollection.get_rotated_moved_union places
        # the keys: each key's cell corners are rotated about the origin by
        # -rotation, then the cluster is shifted right by U(rx). Using the full
        # key cell (not the smaller switch cutout) keeps the span conservative.
        U = self.parameters.U
        spans: list[list[float]] = []
        for (
            rotation,
            collection,
        ) in self.switch_rotation_collection.rotation_collection.items():
            theta = math.radians(-rotation)
            cos_t, sin_t = math.cos(theta), math.sin(theta)
            xs: list[float] = []
            for rx in collection.get_rx_list():
                x_shift = U(rx)
                for ry in collection.get_ry_list_in_rx(rx):
                    for x in collection.get_x_list_in_rx_ry(rx, ry):
                        for y in collection.get_y_list_in_rx_ry_x(x, rx, ry):
                            item = collection.get_item(x, y, rx, ry)
                            corners = (
                                (item.x, item.y),
                                (item.x + item.w, item.y),
                                (item.x + item.w, item.y - item.h),
                                (item.x, item.y - item.h),
                            )
                            for cell_x, cell_y in corners:
                                real_x, real_y = U(cell_x), U(cell_y)
                                xs.append((real_x * cos_t - real_y * sin_t) + x_shift)
            if xs:
                spans.append([min(xs), max(xs)])
        spans.sort()
        merged: list[list[float]] = []
        for lo, hi in spans:
            if merged and lo <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], hi)
            else:
                merged.append([lo, hi])
        return [(lo, hi) for lo, hi in merged]

    @staticmethod
    def plan_section_cuts(
        board_left: float,
        board_right: float,
        plate: float,
        uncuttable_spans: list[tuple[float, float]],
        safety: float,
    ) -> tuple[list[float], bool]:
        # Choose the fewest boundary x positions (mm) that cut the board into
        # sections no wider than the plate, with no boundary inside an uncuttable
        # (rotated cluster) span. Greedy: extend each section as far right as the
        # plate allows, then pull the cut left of any cluster it lands in (with a
        # safety gap so seam finger jitter can't reach the cluster). Returns
        # (cuts, ok); ok is False when a cluster is too wide to fit the plate.
        spans = sorted(uncuttable_spans)

        def run(tight: bool) -> tuple[list[float], bool]:
            cuts: list[float] = []
            start = board_left
            for _ in range(1000):
                if board_right - start <= plate + 1e-6:
                    return cuts, True
                limit = start + plate
                cut = limit
                if tight:
                    # End the section right after the last cluster that fully
                    # fits, instead of running to the plate limit. That keeps a
                    # cluster's section snug so the keys just past it fall in the
                    # next section and the seam needn't bulge past the plate to
                    # clear them.
                    ends = [
                        hi + safety
                        for lo, hi in spans
                        if lo >= start - 1e-9 and hi + safety <= limit + 1e-9
                    ]
                    if ends:
                        cut = max(ends)
                # Pull the cut clear of any cluster it lands in. Right-to-left so
                # a move that lands in an earlier cluster is caught in the same
                # pass; cut only ever decreases, so this terminates.
                for lo, hi in reversed(spans):
                    if lo - safety < cut < hi + safety:
                        cut = lo - safety
                if cut <= start + 1e-6:
                    return cuts, False
                cuts.append(cut)
                start = cut
            return cuts, False

        greedy_cuts, greedy_ok = run(False)
        tight_cuts, tight_ok = run(True)
        # Prefer the snug placement when it needs no extra sections; otherwise the
        # greedy one uses the fewest sections.
        if tight_ok and len(tight_cuts) <= len(greedy_cuts):
            return tight_cuts, tight_ok
        return greedy_cuts, greedy_ok

    def _split_keyboard_by_footprint(
        self, cluster_spans: list[tuple[float, float]]
    ) -> None:
        U = self.parameters.U
        (f_min_x, f_max_x, f_max_y, f_min_y) = self._full_board_bounds()
        board_left = U(f_min_x) - self.parameters.left_margin
        board_right = U(f_max_x) + self.parameters.right_margin
        plate = self.parameters.x_build_size
        safety = self.parameters.section_finger_depth + self.kerf + 1.0

        cuts, fits = self.plan_section_cuts(
            board_left, board_right, plate, cluster_spans, safety
        )
        self.planned_boundaries = cuts

        self._assign_sections_to_boundaries(cuts)

        self.split_recommendation = self._describe_split(cuts, plate, fits)

    def _assign_sections_to_boundaries(
        self,
        cuts: list[float],
        key_sections: dict[tuple[float, float], int] | None = None,
    ) -> None:
        while len(self.switch_section_list) < len(cuts) + 1:
            self.switch_section_list.append(ItemCollection())
            self.support_section_list.append(ItemCollection())
            self.support_cutout_section_list.append(ItemCollection())

        # Each non-rotated key joins the section its centre falls in; the seam
        # then routes around it so it is never cut. Rotated keys are kept whole by
        # the cut placement, so the clip assigns them to the correct side without
        # them needing to live in a section collection (their local coordinates
        # would break the seam maths - that is a later step).
        #
        # key_sections restores a saved split. Its recorded sections win, because
        # a staggered row can leave a key on the far side of the straight boundary
        # from the section it was planned into. A key it does not name has been
        # added or shifted since, so it falls back to the boundary; if that lands
        # it somewhere that matters, the seam check will say so.
        for x in self.switch_collection.get_sorted_x_list():
            for y in self.switch_collection.get_sorted_y_list_in_x(x):
                item = self.switch_collection.get_item(x, y)
                centre = (item.x_start_mm + item.x_end_mm) / 2.0
                section = sum(1 for cut in cuts if centre >= cut)
                if key_sections is not None:
                    section = key_sections.get(
                        (SplitFile.round_unit(x), SplitFile.round_unit(y)), section
                    )
                self.switch_section_list[section].add_item(x, y, item)
                self.support_section_list[section].add_item(
                    x, y, self.support_collection.get_item(x, y)
                )
                self.support_cutout_section_list[section].add_item(
                    x, y, self.support_cutout_collection.get_item(x, y)
                )

        for section_collection in self.switch_section_list:
            section_collection.set_collection_neighbors()

    def _split_keyboard_from_saved(self, saved: SavedSplit) -> None:
        # Rebuild a recorded split rather than planning a fresh one, then prove it
        # still describes this board: the same kind of planner, every section
        # still populated, every seam unmoved and no section grown past the plate.
        # Anything else and a section printed from the earlier run would no longer
        # fit its neighbours, so refuse to build instead of quietly changing shape.
        cluster_spans = self._rotated_cluster_spans()
        if bool(cluster_spans) != saved.footprint_planned:
            was = (
                "rotated clusters" if saved.footprint_planned else "no rotated clusters"
            )
            raise SplitFileError(
                f"the saved split was planned for a board with {was}, but this board is the other kind"
            )

        cuts = list(saved.boundaries)
        self._assign_sections_to_boundaries(cuts, saved.key_sections())
        if saved.footprint_planned:
            self.planned_boundaries = cuts
        else:
            self.forced_boundaries = cuts
            self.forced_bottom_section_count = saved.bottom_section_count

        self._check_saved_cuts_clear_clusters(cuts, cluster_spans)
        self._check_saved_sections_populated(cuts, cluster_spans)
        self._check_saved_seams(saved)
        self._check_saved_section_widths(saved)

        if saved.footprint_planned:
            plate = self.parameters.x_build_size
            fits = all(hi - lo <= plate + 1e-6 for lo, hi in cluster_spans)
            self.split_recommendation = self._describe_split(cuts, plate, fits)

    def _check_saved_cuts_clear_clusters(
        self, cuts: list[float], cluster_spans: list[tuple[float, float]]
    ) -> None:
        # Rotated keys never join a section collection, so the seam check cannot
        # see them: a cluster that has shifted since the split was saved would let
        # a cut land in the middle of it and the clip would saw through the switch
        # cutouts. Hold a restored cut to the clearance plan_section_cuts gives a
        # fresh one - it places a cut at exactly lo - safety, so compare with a
        # tolerance rather than rejecting the split that was just saved.
        safety = self.parameters.section_finger_depth + self.kerf + 1.0
        for cut in cuts:
            for low, high in cluster_spans:
                if low - safety + 1e-6 < cut < high + safety - 1e-6:
                    raise SplitFileError(
                        f"the cut at x = {cut:.1f} mm now falls inside a rotated cluster "
                        f"spanning x = {low:.1f} to {high:.1f} mm"
                    )

    def _check_saved_sections_populated(
        self, cuts: list[float], cluster_spans: list[tuple[float, float]]
    ) -> None:
        # An empty section means the board no longer reaches that far, so the
        # recorded split cannot be rebuilt. Read the restored collections, since
        # that is what the geometry is cut from - the recorded assignment decides
        # them, not the boundaries. A section may legitimately hold nothing but a
        # rotated cluster, which never lands in a section collection.
        edges = [-math.inf, *cuts, math.inf]
        for section, (low, high) in enumerate(itertools.pairwise(edges)):
            has_key = (
                next(
                    self._iter_collection_items(self.switch_section_list[section]), None
                )
                is not None
            )
            has_cluster = any(
                span_low < high and span_high > low
                for span_low, span_high in cluster_spans
            )
            if not (has_key or has_cluster):
                raise SplitFileError(
                    f"section {section} of the saved split holds no keys on this board"
                )

    def _check_saved_seams(self, saved: SavedSplit) -> None:
        for section, (recorded, current) in enumerate(
            zip(saved.seams, self.seam_profiles())
        ):
            mismatch = SplitFile.seam_mismatch(recorded, current)
            if mismatch is not None:
                raise SplitFileError(
                    f"the seam between sections {section} and {section + 1} has moved: {mismatch}"
                )

    def _check_saved_section_widths(self, saved: SavedSplit) -> None:
        # A section that already overflowed the plate it was planned against keeps
        # its warning - it could never be loaded again otherwise. One that has
        # only just outgrown the plate is fatal, since it can no longer be
        # printed at all.
        plate = self.parameters.x_build_size
        widths = [width for (width, _height) in self.get_top_section_dimensions()]
        for section, (width, recorded) in enumerate(zip(widths, saved.section_widths)):
            if width > plate + 1e-6 and recorded <= saved.plate_mm + 1e-6:
                raise SplitFileError(
                    f"section {section} is now {width:.1f} mm wide and no longer fits the {plate:.1f} mm "
                    f"build plate (it was {recorded:.1f} mm when the split was saved)"
                )

    def _describe_split(self, cuts: list[float], plate: float, fits: bool) -> str:
        # Report the true section widths (these include the seam's finger/weave
        # around keys), so an over-plate section is flagged honestly.
        widths = [w for (w, _h) in self.get_top_section_dimensions()]
        lines = [f"Split recommendation (rotated layout, plate {plate:.0f} mm):"]
        if not fits:
            lines.append(
                "  WARNING: a rotated cluster is wider than the plate - it cannot be split to fit."
            )
        lines.append(
            "  %d section(s); cut at x = %s mm"
            % (len(cuts) + 1, ", ".join(f"{c:.1f}" for c in cuts) if cuts else "(none)")
        )
        for i, w in enumerate(widths):
            flag = (
                ""
                if w <= plate + 1e-6
                else "  (exceeds plate - needs finer/angled splitting)"
            )
            lines.append("    section %d width %.1f mm%s" % (i, w, flag))
        return "\n".join(lines)

    @staticmethod
    def _assign_x_sections(
        columns: list[tuple[float, list[float]]], threshold: float, left_margin: float
    ) -> list[list[int]]:
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
        section_start: dict = {}
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
    def _count_sections(assignments: list[list[int]]) -> int:
        return max((s for column in assignments for s in column), default=-1) + 1

    @staticmethod
    def _balanced_x_sections(
        columns: list[tuple[float, list[float]]],
        x_build_size: float,
        left_margin: float,
    ) -> list[list[int]]:
        # Packing greedily up to the full plate width uses the fewest sections but
        # fills each to the brim, leaving a thin remainder (e.g. a 27.75u board on a
        # 300mm plate splits 11.5u / 15.25u / 2u). Section count is monotonic in the
        # threshold, so keep the greedy section count but re-pack with the smallest
        # threshold that still yields it - which minimises the widest section and
        # spreads the keys as evenly as the plate and un-cuttable wide keys allow.
        target_count = Keyboard._count_sections(
            Keyboard._assign_x_sections(columns, x_build_size, left_margin)
        )
        if target_count <= 1:
            return Keyboard._assign_x_sections(columns, x_build_size, left_margin)

        low, high = 0.0, float(x_build_size)
        for _ in range(40):
            mid = (low + high) / 2
            count = Keyboard._count_sections(
                Keyboard._assign_x_sections(columns, mid, left_margin)
            )
            if count <= target_count:
                high = mid
            else:
                low = mid

        assignments = Keyboard._assign_x_sections(columns, high, left_margin)
        if Keyboard._count_sections(assignments) != target_count:
            # The search converged just below a step; fall back to the plate width.
            return Keyboard._assign_x_sections(columns, x_build_size, left_margin)
        return assignments

    def get_top_section_remove_block(self, section_number: int) -> OpenSCADObject:
        self.logger.debug("Get Section %d", section_number)
        assert self.parameters.case_height_base_removed is not None
        remove_block_height = self.parameters.case_height_base_removed * 4
        remove_block_z_offset = remove_block_height / 2
        return self.get_section_x_clip(
            section_number, remove_block_height, remove_block_z_offset
        )

    @staticmethod
    def _iter_collection_items(collection: ItemCollection) -> Iterator[Any]:
        for rx in collection.get_rx_list():
            for ry in collection.get_ry_list_in_rx(rx):
                for x in collection.get_x_list_in_rx_ry(rx, ry):
                    for y in collection.get_y_list_in_rx_ry_x(x, rx, ry):
                        yield collection.get_item(x, y, rx, ry)

    def _full_board_bounds(self) -> tuple[float, float, float, float]:
        # Bounds of the whole board (min_x, max_x, max_y, min_y) merging the
        # non-rotated switches with the real, post-rotation extent of any
        # rotated clusters - the same merge set_dimensions uses for the case
        # size. Rotated ergo halves dip below the central cluster, so relying on
        # switch_collection alone underestimates the board and leaves the extra
        # plate uncut.
        (min_x, max_x, max_y, min_y) = self.switch_collection.get_collection_bounds()
        (r_min_x, r_max_x, r_max_y, r_min_y) = (
            self.switch_rotation_collection.get_real_collection_bounds()
        )
        return (
            min(min_x, r_min_x),
            max(max_x, r_max_x),
            max(max_y, r_max_y),
            min(min_y, r_min_y),
        )

    def _board_y_band_edges(self) -> list[float]:
        # Every distinct row edge across the whole board (plus the top/bottom
        # margins), so a section's clip and its neighbour's clip sweep the exact
        # same y-bands and their shared seam lines up band for band.
        (b_min_x, b_max_x, b_max_y, b_min_y) = self._full_board_bounds()
        top_margin_cells = (
            self.parameters.top_margin / self.parameters.switch_spacing
        ) + 1
        bottom_margin_cells = (
            self.parameters.bottom_margin / self.parameters.switch_spacing
        ) + 1
        sweep_lo = b_min_y - bottom_margin_cells
        sweep_hi = b_max_y + top_margin_cells
        edges = {sweep_lo, sweep_hi}
        for item in self._iter_collection_items(self.switch_collection):
            for edge in (item.y - item.h, item.y):
                if sweep_lo - 1e-9 < edge < sweep_hi + 1e-9:
                    edges.add(edge)
        return sorted(edges)

    def _section_x_boundaries(self) -> list[float]:
        # Nominal straight seam x (mm) for each boundary between section i and
        # i+1 (one per adjacent pair). Placed at the centre of the gap between the
        # two sections' keys and clamped so neither section's plate can exceed
        # x_build_size. Both neighbouring sections read the same value, so their
        # plates meet with no overlap and no void.
        #
        # A footprint-planned board (rotated clusters) has already chosen cuts in
        # the real gaps; use them verbatim so the seam sits where a cluster is
        # kept whole. A split restored from file pins them the same way.
        if self.forced_boundaries is not None:
            return list(self.forced_boundaries)
        if self.planned_boundaries is not None:
            return list(self.planned_boundaries)
        U = self.parameters.U
        build = self.parameters.x_build_size
        left_margin = self.parameters.left_margin
        right_margin = self.parameters.right_margin
        sections = self.switch_section_list
        boundaries = []
        for i in range(len(sections) - 1):
            (l_min, l_max, l_maxy, l_miny) = sections[i].get_collection_bounds()
            (r_min, r_max, r_maxy, r_miny) = sections[i + 1].get_collection_bounds()
            left_key_left = U(l_min)
            left_key_right = U(l_max)
            right_key_left = U(r_min)
            right_key_right = U(r_max)
            gap_centre = (left_key_right + right_key_left) / 2.0
            # seam <= this keeps section i within the build plate...
            upper = (left_key_left - left_margin) + build
            # ...and seam >= this keeps section i+1 within the build plate.
            lower = (right_key_right + right_margin) - build
            low_bound = max(left_key_right, lower)
            high_bound = min(right_key_left, upper)
            if low_bound <= high_bound:
                seam = min(max(gap_centre, low_bound), high_bound)
            else:
                # Gap too wide to bridge within the build size: sit at the gap
                # centre clamped to the keys. An unavoidable void may remain and
                # the section summary flags the oversize.
                seam = min(max(gap_centre, left_key_right), right_key_left)
            boundaries.append(seam)
        return boundaries

    def seam_profiles(self) -> list[list[SeamBand]]:
        # The mating surface between each adjacent pair of sections, as
        # (y_start_mm, y_end_mm, seam_x_mm) bands - the same seam get_section_x_clip
        # cuts against, in the same y bands.
        #
        # Neighbouring bands sharing a seam x are merged, so the profile describes
        # the polyline itself rather than how the board happened to be sliced into
        # bands. That is what lets a key added or resized inside a section - which
        # splits a band without moving the seam - compare equal.
        U = self.parameters.U
        boundaries = self._section_x_boundaries()
        edges = self._board_y_band_edges()
        profiles = []
        for boundary_index in range(len(boundaries)):
            bands: list[list[float]] = []
            for lo, hi in itertools.pairwise(edges):
                if hi - lo < 1e-9:
                    continue
                seam = self._section_seam_x(boundary_index, boundaries, (lo + hi) / 2.0)
                if (
                    bands
                    and abs(bands[-1][2] - seam) < 1e-9
                    and abs(bands[-1][1] - U(lo)) < 1e-9
                ):
                    bands[-1][1] = U(hi)
                else:
                    bands.append([U(lo), U(hi), seam])
            profiles.append([(band[0], band[1], band[2]) for band in bands])
        return profiles

    def _section_seam_x(
        self, boundary_index: int, boundaries: list[float], mid_y: float
    ) -> float:
        # Shared seam x (mm) for the boundary between section boundary_index and
        # boundary_index+1 at row-midpoint mid_y (units). Starts from the nominal
        # straight seam and is routed so it never cuts a key on this row: pushed
        # right of the left section's keys and left of the right section's keys.
        # A wide key (e.g. the spacebar) that straddles the nominal line makes the
        # seam bulge around it - a tab on one side, a notch on the other.
        U = self.parameters.U
        seam = boundaries[boundary_index]

        # Zig-zag the seam to form interlocking fingers. The offset alternates
        # side to side every section_finger_height of travel; because both
        # neighbouring sections read this same value the tabs and notches are
        # exactly complementary. The key-avoidance clamp below then reins any
        # finger back so it never cuts a key, so fingers only show where there is
        # spare plate (the top/bottom margins and keyless gaps).
        finger_depth = self.parameters.section_finger_depth
        finger_height = self.parameters.section_finger_height
        if finger_depth > 0 and finger_height > 0:
            if math.floor(mid_y / finger_height) % 2 == 0:
                seam += finger_depth
            else:
                seam -= finger_depth

        for item in self._iter_collection_items(
            self.switch_section_list[boundary_index]
        ):
            if (item.y - item.h) - 1e-9 <= mid_y <= item.y + 1e-9:
                seam = max(seam, U(item.x + item.w))
        right_limit = None
        for item in self._iter_collection_items(
            self.switch_section_list[boundary_index + 1]
        ):
            if (item.y - item.h) - 1e-9 <= mid_y <= item.y + 1e-9:
                left_edge = U(item.x)
                right_limit = (
                    left_edge if right_limit is None else min(right_limit, left_edge)
                )
        if right_limit is not None:
            seam = min(seam, right_limit)
        return seam

    def get_section_x_clip(
        self,
        section_number: int,
        remove_block_height: float,
        remove_block_z_offset: float,
    ) -> OpenSCADObject:
        # Carve one section out of the whole plate. Adjacent sections share a
        # single seam line (per y-band) - this section keeps the plate to the left
        # of its right seam and to the right of its left seam, and its neighbour
        # keeps the complementary side. Because the seam is shared, the pieces
        # meet exactly: no overlap (they never both claim the same plate) and no
        # void (nothing is left unclaimed). Outer sides are the board edge.
        clip = union()
        section_count = len(self.switch_section_list)
        (b_min_x, b_max_x, b_max_y, b_min_y) = self._full_board_bounds()
        U = self.parameters.U

        boundaries = self._section_x_boundaries()

        plate_width = (
            U(b_max_x - b_min_x)
            + self.parameters.left_margin
            + self.parameters.right_margin
        )
        remove_block_length = (plate_width * 3.0) + 100.0

        # Bands closer together than this are float noise from
        # _board_y_band_edges rather than a real row boundary - collapse them
        # so the rectangular cuts and the finger chamfer corners agree on
        # exactly the same set of bands.
        edges = self._board_y_band_edges()
        edges = [
            edge for i, edge in enumerate(edges) if i == 0 or edge - edges[i - 1] > 1e-9
        ]
        mids = [(lo + hi) / 2.0 for lo, hi in itertools.pairwise(edges)]

        right_seams = (
            [self._section_seam_x(section_number, boundaries, mid) for mid in mids]
            if section_number < section_count - 1
            else None
        )
        left_seams = (
            [self._section_seam_x(section_number - 1, boundaries, mid) for mid in mids]
            if section_number > 0
            else None
        )

        for band_index, (lo, hi) in enumerate(itertools.pairwise(edges)):
            y_offset = U(lo) - self.kerf
            bar_height = U(hi - lo) + (self.kerf * 2)

            if right_seams is not None:
                right_seam = right_seams[band_index]
                clip += down(remove_block_z_offset)(
                    right(right_seam)(
                        forward(y_offset)(
                            cube([remove_block_length, bar_height, remove_block_height])
                        )
                    )
                )

            if left_seams is not None:
                left_seam = left_seams[band_index]
                clip += down(remove_block_z_offset)(
                    right(left_seam - remove_block_length)(
                        forward(y_offset)(
                            cube([remove_block_length, bar_height, remove_block_height])
                        )
                    )
                )

        chamfer = self.parameters.section_finger_chamfer
        if chamfer > 0:
            for seams, tip in ((right_seams, "max"), (left_seams, "min")):
                if seams is None:
                    continue
                clip += down(remove_block_z_offset)(
                    self._finger_chamfer_cuts(
                        seams, edges, chamfer, tip, remove_block_height
                    )
                )

        return clip

    def _finger_chamfer_corners(
        self, seams: list[float], edges: list[float], chamfer: float, tip: str
    ) -> list[tuple[float, float, float, float, float]]:
        # Wherever a finger seam steps sideways between two y-bands, the tab
        # side of the step leaves one right-angle corner exposed (the notch
        # side leaves the complementary reflex corner, which needs no bevel -
        # nothing juts out there for a mating part to catch on). tip="max"
        # finds that corner for the section left of the seam, tip="min" for
        # the section right of it - the two sections never share a corner,
        # since a 90-degree material angle on one side is a 270-degree
        # (reflex) angle on the other.
        #
        # Returns (tip_x, edge_y, x_sign, y_sign, leg) in mm: cut a right
        # triangle of leg length `leg` from (tip_x, edge_y), running x_sign
        # along x and y_sign along y, to bevel that one corner.
        U = self.parameters.U
        x_sign = -1.0 if tip == "max" else 1.0
        corners = []
        for index in range(1, len(seams)):
            seam_below, seam_above = seams[index - 1], seams[index]
            step = seam_above - seam_below
            if abs(step) < 1e-9:
                continue
            tip_x = (
                max(seam_below, seam_above)
                if tip == "max"
                else min(seam_below, seam_above)
            )
            wide_band_above = abs(seam_above - tip_x) < 1e-9
            y_sign = 1.0 if wide_band_above else -1.0
            wide_band_height = U(
                (edges[index + 1] - edges[index])
                if wide_band_above
                else (edges[index] - edges[index - 1])
            )
            # Halved: the tab band's other edge may have its own step and thus
            # its own chamfer eating into the same band from the far side, so
            # neither one alone may claim more than half the band's height.
            leg = min(chamfer, abs(step), wide_band_height / 2.0)
            if leg <= 1e-9:
                continue
            corners.append((tip_x, U(edges[index]), x_sign, y_sign, leg))
        return corners

    def _finger_chamfer_cuts(
        self,
        seams: list[float],
        edges: list[float],
        chamfer: float,
        tip: str,
        remove_block_height: float,
    ) -> OpenSCADObject:
        cuts = union()
        for tip_x, edge_y, x_sign, y_sign, leg in self._finger_chamfer_corners(
            seams, edges, chamfer, tip
        ):
            wedge = polygon([[0, 0], [x_sign * leg, 0], [0, y_sign * leg]])
            cuts += translate([tip_x, edge_y, 0])(
                linear_extrude(height=remove_block_height)(wedge)
            )
        return cuts

    def get_bottom_section_span(self, section_number: int) -> tuple[float, float]:
        # The x range (mm) of the bottom cover this section keeps.
        if self.planned_boundaries is not None:
            # Split the bottom cover at the same footprint-planned boundaries as
            # the plate. start_x = boundary + right_margin lines the slab up with
            # the top seam once both are shifted into place (the caller's x_offset
            # undoes the right_margin). Outer sections run well past the case edge.
            cuts = self.planned_boundaries
            last = len(cuts)
            rm = self.parameters.right_margin
            start_x = -1000.0 if section_number == 0 else cuts[section_number - 1] + rm
            end_x = (
                self.parameters.real_case_width + 1000.0
                if section_number == last
                else cuts[section_number] + rm
            )
            return (start_x, end_x)

        # get_bottom_section_count, not the parameter behind it: a restored split
        # pins the number of pieces, and each one has to be sized for the same
        # count that is being generated.
        section_size = self.parameters.real_case_width / self.get_bottom_section_count()
        self.logger.debug("section_size: %f", section_size)
        return (section_size * section_number, section_size * (section_number + 1))

    def get_bottom_section_remove_block(self, section_number: int) -> OpenSCADObject:

        # section = self.switch_section_list[section_number]

        self.logger.debug("Get Section %d", section_number)

        self.logger.debug("real_case_width: %f", self.parameters.real_case_width)
        self.logger.debug("real_case_height: %f", self.parameters.real_case_height)

        (start_x, end_x) = self.get_bottom_section_span(section_number)

        (start_x, end_x) = self.get_screw_support_interference_offset(start_x, end_x)

        x_offset = start_x - self.parameters.right_margin
        y_offset = (
            self.parameters.real_case_height / 2 + self.parameters.real_case_height
        )
        assert self.parameters.case_height_extra_fill is not None
        z_offset = self.parameters.case_height_extra_fill / 2

        width = end_x - start_x
        height = self.parameters.real_case_height * 2
        thickness = self.parameters.case_height_extra_fill * 2

        self.logger.debug(
            "section: %d, x_offset: %f, width: %f, y_offset: %f",
            section_number,
            x_offset,
            width,
            y_offset,
        )

        return right(x_offset)(
            back(y_offset)(down(z_offset)(cube([width, height, thickness])))
        )

    def get_screw_support_interference_offset(
        self, start_x: float, end_x: float
    ) -> tuple[float, float]:

        assert self.body is not None
        for coord_string in self.body.screw_hole_info:
            screw_hole_info = self.body.screw_hole_info[coord_string]

            screw_x = screw_hole_info["x"]
            # screw_y = screw_hole_info['y']

            # self.logger.debug('coord_string: %s, screw_x: %f, screw_y: %f', coord_string, screw_x, screw_y)

            screw_hole_min_x = screw_x - screw_hole_info["support_directions"]["left"]
            screw_hole_max_x = screw_x + screw_hole_info["support_directions"]["right"]

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

    def set_section(self, section_number: int) -> None:
        self.desired_section_number = section_number

    def get_top_section_count(self) -> int:
        return len(self.switch_section_list)

    def get_top_section_dimensions(self) -> list[tuple[float, float]]:
        # Width and height in mm of each top section's plate. Width is the kept
        # x-extent between the section's left and right shared seams (board edge
        # for the outer sides), taken across every row so a seam that bulges
        # around a straddling key is measured at its widest. Height is the full
        # board height, since sections only split along x.
        (b_min_x, b_max_x, b_max_y, b_min_y) = self._full_board_bounds()
        U = self.parameters.U
        board_left = U(b_min_x) - self.parameters.left_margin
        board_right = U(b_max_x) + self.parameters.right_margin
        boundaries = self._section_x_boundaries()
        edges = self._board_y_band_edges()
        section_count = len(self.switch_section_list)
        dimensions = []
        for i in range(section_count):
            lefts = []
            rights = []
            for lo, hi in itertools.pairwise(edges):
                if hi - lo < 1e-9:
                    continue
                mid = (lo + hi) / 2.0
                lefts.append(
                    board_left
                    if i == 0
                    else self._section_seam_x(i - 1, boundaries, mid)
                )
                rights.append(
                    board_right
                    if i == section_count - 1
                    else self._section_seam_x(i, boundaries, mid)
                )
            width = (max(rights) - min(lefts)) if lefts else 0.0
            dimensions.append((width, self.parameters.real_case_height))
        return dimensions

    def get_bottom_section_count(self) -> int:
        if self.planned_boundaries is not None:
            return len(self.planned_boundaries) + 1
        # A restored split pins the count. Otherwise Parameters holds it, but is
        # only told the board size once the geometry is built and works the count
        # out from a zero-width case until then, so size it here when the split
        # asks this early.
        count = self.forced_bottom_section_count or self.parameters.bottom_section_count
        if count:
            return count
        (_min_x, max_x, _max_y, _min_y) = self._full_board_bounds()
        case_width = (
            self.parameters.U(max_x)
            + self.parameters.left_margin
            + self.parameters.right_margin
        )
        return math.ceil(case_width / self.parameters.x_build_size)
