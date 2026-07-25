#!/usr/bin/env python3

import argparse
from collections.abc import Sequence
from typing import Any
import json
# import math
import re
import logging
import os
# import os.path
import subprocess
# import time

from solid import *
from solid.utils import *

from parameters import Parameters
from keyboard import Keyboard
from cable import Cable

# Preview colors given to each section so the pieces are distinguishable in the
# per-section, exploded and assembled scad views. color() only affects the
# OpenSCAD preview; rendered STL geometry is unchanged.
SECTION_COLORS = ['salmon', 'lightgreen', 'lightblue', 'gold', 'plum', 'cyan']

# Set logger level variables
console_logging_level = logging.WARN
file_logging_level = logging.DEBUG


# Get root logger and set main logger level to DEBUG
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)


# Create formatters
console_formatter = logging.Formatter('%(name)s %(levelname)s: %(funcName)s: [%(lineno)d]: %(message)s')
file_formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(funcName)s: [%(lineno)d]: %(message)s')

# Create console handler and set level to info
console_handler = logging.StreamHandler()
console_handler.setLevel(console_logging_level)

# Add formatter to console_handler
console_handler.setFormatter(console_formatter)

# Add console handler to logger
logger.addHandler(console_handler)

# Get file info that will be used to create log file
script_location = Path(os.path.dirname(os.path.realpath(__file__)))
log_file_name = 'generator.log'
log_file_path = script_location / log_file_name

# Create file handler and set level to info
file_handler = logging.FileHandler(log_file_path, mode = 'w')
file_handler.setLevel(file_logging_level)

# Add formatter to file_handler
file_handler.setFormatter(file_formatter)

# Add file handler to logger
logger.addHandler(file_handler)


# Helper for parser to ensure filename argument has the correct extension
def CheckExt(choices: set[str], append: bool = False) -> type[argparse.Action]:
    class Act(argparse.Action):
        def __call__(self, parser: argparse.ArgumentParser, namespace: argparse.Namespace, fname: str | Sequence[Any] | None, option_string: str | None = None) -> None:
            assert isinstance(fname, str)
            ext = os.path.splitext(fname)[1][1:]
            if ext not in choices:
                option_string = '({})'.format(option_string) if option_string else ''
                parser.error("file doesn't end with one of {}{}".format(choices,option_string))
            elif append:
                file_names = list(getattr(namespace, self.dest, None) or [])
                file_names.append(fname)
                setattr(namespace, self.dest, file_names)
            else:
                setattr(namespace,self.dest,fname)

    return Act



def main() -> None:

    parameter_file_extensions = {suffix.lstrip('.') for suffix in Parameters.PARAMETER_FILE_SUFFIXES}

    parser = argparse.ArgumentParser(description='Build custom keyboard SCAD file using keyboard layout editor format')
    parser.add_argument('-i', '--input-file', metavar = 'layout_json_file_name.json', help = 'A path to a keyboard layout editor json file', required = True, action=CheckExt({'json'}))
    # parser.add_argument('-o', '--output-folder', metavar = 'scad', help = 'A path to a folder to store the generated open scad file')
    parser.add_argument('-p', '--parameter-file', metavar = 'parameters.json', help = 'A JSON file containing parameters for the object being made. May be given more than once, in which case later files override earlier ones', default = None, action=CheckExt(parameter_file_extensions, append = True))
    parser.add_argument('-s', '--section', metavar = 'section_num', help = 'The number of the section that should be built', type = int, default = -1)
    parser.add_argument('-a', '--all-sections', help = 'Output all the parts for all possible sections in separate files', default = False, action = 'store_true')
    parser.add_argument('-e', '--exploded', help = 'Create test file with each section shown as an exploded view', default = False, action = 'store_true')
    parser.add_argument('-f', '--fragments', metavar = 'num_fragments', help = 'The number of fragments to be used when creating curves', type = int, default = 20)
    parser.add_argument('-r', '--render', help = 'Render an STL from the generated scad file', default = False, action = 'store_true')
    parser.add_argument('--switch-type-in-filename', help = 'Add the switch type name and stabilizer type name to the filename', default = False, action = 'store_true')

    # Parse command line arguments
    args = parser.parse_args()
    logger.debug(vars(args))

    # Create Path object from input file argument
    input_file_path = Path(args.input_file)

    # Get base folder path
    base_path = input_file_path.parent

    # Get input file name only
    file_name_only = input_file_path.name
    
    # Get layout name from file name
    layout_name = input_file_path.stem

    # Generate output scad and stl output folder paths
    output_base_folder = base_path / layout_name
    scad_folder_path = output_base_folder / 'scad'
    stl_folder_path = output_base_folder / 'stl'

    # Ensure all output folders exist
    if output_base_folder.is_dir() == False:
        output_base_folder.mkdir()

    if scad_folder_path.is_dir() == False:
        scad_folder_path.mkdir()

    if stl_folder_path.is_dir() == False:
        stl_folder_path.mkdir()

    logger.debug('layout_name: %s', str(layout_name))
    logger.debug('base_path: %s', str(base_path))
    logger.debug('file_name_only: %s', str(file_name_only))
    
    # define output file extensions
    scad_postfix = '.scad'
    stl_postfix  = '.stl'

    # Set fragments per circle
    FRAGMENTS = args.fragments
    logger.debug('\tFragments: %d', FRAGMENTS)

    # Pattern and Replacement strings to be used when trying to turn keyboard-layout-editor raw output into valid JSON
    json_key_pattern = '([{,])([xywha1]+):'
    json_key_replace = '\\1"\\2":'

    # Open JSON layout file
    logger.debug('Read layout JSON string from file %s', input_file_path)
    try:
        keyboard_layout = input_file_path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        message = 'Layout file %s is not utf-8 encoded' % (input_file_path)
        logger.error(message)
        print('ERROR:', message)
        exit(1)
    except OSError as error:
        logger.error('Failed to read layout file: %s', error)
        print('ERROR:', error)
        exit(1)

    keyboard_layout_dict = None

    # Load keyboard layout dictionary
    logger.debug('Parse layout file JSON string')
    try:
        # Attempt to parse to provided JSON string
        keyboard_layout_dict = json.loads(keyboard_layout)
        logger.debug('Valid Json Parsed')
    except:
        # Failed to parse the JSON test.
        # This most likely means that the keyboard-layout-editor raw output was provided
        # Attempt to modify that string to make it valid JSON
        keyboard_layout = '[%s]' % (keyboard_layout)
        keyboard_layout = re.sub(json_key_pattern, json_key_replace, keyboard_layout)
        try:
            keyboard_layout_dict = json.loads(keyboard_layout)
            logger.info('Initial layout Json Invalid. Json modified and parsed')
        except:
            logger.error('Failed to parse layout json after attempt at correction.')
            raise

    logger.debug('keyboard_layout_dict: %s', str(keyboard_layout_dict))


    # Read parameter files
    parameter_dict = None
    if args.parameter_file is not None:
        logger.debug('Load parameter files %s', args.parameter_file)
        try:
            parameter_dict = Parameters.load_parameter_files(args.parameter_file)
        except (OSError, TypeError, ValueError) as error:
            logger.error('Failed to load parameter files: %s', error)
            print('ERROR:', error)
            exit(1)

        logger.debug('parameter_dict: %s', str(parameter_dict))


    # Set parameters from input file
    try:
        parameters = Parameters(parameter_dict)
    except (AttributeError, TypeError, ValueError) as error:
        logger.error('Failed to apply parameters: %s', error)
        print('ERROR:', error)
        exit(1)
    
    # Create Keyboard instance
    keyboard = Keyboard(parameters)

    # Process the keyboard layout object
    keyboard.process_keyboard_layout(keyboard_layout_dict)
    keyboard.process_custom_shapes()

    logger.debug('kerf: %f', keyboard.kerf)

    # Dictionary of SolidPython solid objects that need to be rendered to SCAD and to STL if desired
    solid_object_dict: dict = {}

    # Create objects for each of the generated sections
    if args.all_sections == True:
        # Iterate over all sections generated and add all sections to solid_object_dict
        for section in range(keyboard.get_top_section_count()):
            # Set current section for generator
            keyboard.set_section(section)

            section_color = SECTION_COLORS[section % len(SECTION_COLORS)]

            # Create dict for section
            solid_object_dict[section] = {}

            # Add top assembly, plate, and all assembly to section dict. render()
            # forces CGAL evaluation in the OpenSCAD preview: these trees are far
            # past the CSG normalization element limit, so a plain F5 preview
            # aborts normalization and shows nothing. color() must stay outside
            # render(), which drops any colors inside it.
            solid_object_dict[section]['top'] = color(section_color) ( render() ( keyboard.get_assembly(top = True) ) )
            solid_object_dict[section]['all'] = color(section_color) ( render() ( keyboard.get_assembly(all = True) ) )
            solid_object_dict[section]['plate'] = color(section_color) ( render() ( keyboard.get_assembly(plate_only = True) ) )

            # If there is a bottom section for the current section add it to section dict
            if section < keyboard.get_bottom_section_count():
                solid_object_dict[section]['bottom'] = color(section_color) ( render() ( keyboard.get_assembly(bottom = True) ) )
                solid_object_dict[section]['case_bottom'] = color(section_color) ( render() ( keyboard.get_assembly(case_bottom = True) ) )
            
    # Create exploded object
    elif args.exploded == True:
        solid_object_dict[-1] = {}
        solid_object_dict[-1]['top'] = union()
        solid_object_dict[-1]['plate'] = union()
        solid_object_dict[-1]['bottom'] = union()
        solid_object_dict[-1]['case_bottom'] = union()
        for section in range(keyboard.get_top_section_count()):
            keyboard.set_section(section)
            section_color = SECTION_COLORS[section % len(SECTION_COLORS)]
            solid_object_dict[-1]['top'] += color(section_color) ( up(5 * section) ( right(10 * section) ( render() ( keyboard.get_assembly(top = True) ) ) ) )
            solid_object_dict[-1]['plate'] += color(section_color) ( up(5 * section) ( right(10 * section) ( render() ( keyboard.get_assembly(plate_only = True) ) ) ) )
            if section < keyboard.get_bottom_section_count():
                solid_object_dict[-1]['bottom'] += color(section_color) ( up(5 * section) ( right(10 * section) ( render() ( keyboard.get_assembly(bottom = True) ) ) ) )
                solid_object_dict[-1]['case_bottom'] += color(section_color) ( up(5 * section) ( right(10 * section) ( render() ( keyboard.get_assembly(case_bottom = True) ) ) ) )
    

    # Create objects for a specified section
    elif args.section > -1:
        # Set desired section to create
        keyboard.set_section(args.section)

        section_color = SECTION_COLORS[args.section % len(SECTION_COLORS)]

        # Create dict for section
        solid_object_dict[args.section] = {}

        # Add top assembly, plate, and all assembly to section dict
        solid_object_dict[args.section]['top'] = color(section_color) ( render() ( keyboard.get_assembly(top = True) ) )
        solid_object_dict[args.section]['all'] = color(section_color) ( render() ( keyboard.get_assembly(all = True) ) )
        solid_object_dict[args.section]['plate'] = color(section_color) ( render() ( keyboard.get_assembly(plate_only = True) ) )

        # If there is a bottom section for the current section add it to section dict
        if args.section < keyboard.get_bottom_section_count():
            solid_object_dict[args.section]['bottom'] = color(section_color) ( render() ( keyboard.get_assembly(bottom = True) ) )
            solid_object_dict[args.section]['case_bottom'] = color(section_color) ( render() ( keyboard.get_assembly(case_bottom = True) ) )

    # Create an objects that are not split into sections. No other options were specified
    else:
        logger.debug('Create whole object. No other options specified')
        solid_object_dict['all'] = {}
        solid_object_dict['all']['top'] = render() ( keyboard.get_assembly(top = True) )
        solid_object_dict['all']['bottom'] = render() ( keyboard.get_assembly(bottom = True) )
        solid_object_dict['all']['all'] = render() ( keyboard.get_assembly(all = True) )
        solid_object_dict['all']['plate'] = render() ( keyboard.get_assembly(plate_only = True) )
        solid_object_dict['all']['case_bottom'] = render() ( keyboard.get_assembly(case_bottom = True) )
    
    # Add global items that are not dependent on the sections or parts of the item to build
    solid_object_dict['global'] = {}

    # Generate a strain relief piece for the cable hole
    if parameters.cable_hole == True:
        cable = Cable(parameters)
        solid_object_dict['global']['cable_holder_main'] = cable.holder_main()
        solid_object_dict['global']['cable_holder_clamp'] = cable.holder_clamp()
        solid_object_dict['global']['cable_holder_all'] = cable.holder_all()

    print(parameters)
    print('Case Height: %f, Case Width: %f\n' % (parameters.real_case_height, parameters.real_case_width))
    
    logger.info('Case Height: %f, Case Width: %f', parameters.real_case_height, parameters.real_case_width)
    logger.info('Sections In Top: %d', keyboard.get_top_section_count())
    logger.info('Sections In Bottom: %d', keyboard.get_bottom_section_count())


    ############################################################
    # Render SCAD and STL files
    ############################################################
    subprocess_dict: dict[str, subprocess.Popen | None] = {}

    # Per-part lists of the section scad files, used to build assembly views.
    assembly_includes: dict = {}

    switch_type_for_filename = ''
    stab_type_for_filename = ''

    for section in solid_object_dict.keys():

        if args.switch_type_in_filename == True:
            switch_type_for_filename = '_' + parameters.switch_type
            stab_type_for_filename = '_' + parameters.stabilizer_type

        section_postfix = ''

        # Creating global items that have no relation to switch type
        if isinstance(section, str) and section == 'global':
            switch_type_for_filename = ''
            stab_type_for_filename = ''
        
        # If the current object dict section is an int greater than -1 add the section number to the filename
        if isinstance(section, int) and section > -1:
            section_postfix = '_section_%d' % (section)
        
        if args.exploded == True:
            section_postfix = '_exploded'

        for part_name in solid_object_dict[section].keys():
            part_name_formatted = '_' + part_name

            scad_file_name = scad_folder_path / (layout_name + section_postfix + part_name_formatted + switch_type_for_filename + stab_type_for_filename + scad_postfix)
            stl_file_name = stl_folder_path / (layout_name + section_postfix + part_name_formatted + switch_type_for_filename + stab_type_for_filename + stl_postfix)

            if solid_object_dict[section][part_name] is not None:
                logger.info('Generate scad file with name %s', scad_file_name)
                # Generate SCAD file from assembly. include_orig_code=False stops
                # SolidPython from appending this script's source to the .scad file:
                # it lands inside a /* */ block and any */ in the source breaks
                # OpenSCAD's (non-nesting) comment parsing.
                scad_render_to_file(solid_object_dict[section][part_name], scad_file_name, file_header=f'$fn = {FRAGMENTS};', include_orig_code=False)
                print('Generated scad file with name', scad_file_name)

                # Record per-section files so they can be stitched into an
                # assembly view (see below). Only real numbered sections apply.
                if isinstance(section, int) and section > -1:
                    assembly_includes.setdefault(part_name, []).append(scad_file_name.name)

                # Render STL if option is chosen
                if args.render:
                    logger.debug('Render STL from SCAD')
                    logger.info('Generate stl file with name %s from %s', stl_file_name, scad_file_name)

                    openscad_command_list = ['openscad', '-o', '%s' % (stl_file_name), '%s' % (scad_file_name)]
                    subprocess_dict[stl_file_name] = subprocess.Popen(openscad_command_list)
    
    
    ################################################################
    #  Write assembly views
    ################################################################
    # For each part that was split into sections, write a scad file that includes
    # every section's file so the pieces can be viewed together as the assembled
    # keyboard. The sections are clipped in place, so including them reconstructs
    # the whole board. The assembly file sits alongside the section files, so a
    # bare filename include resolves relative to it.
    if args.all_sections == True:
        assembly_switch_postfix = ('_' + parameters.switch_type) if args.switch_type_in_filename else ''
        assembly_stab_postfix = ('_' + parameters.stabilizer_type) if args.switch_type_in_filename else ''
        for part_name, section_files in assembly_includes.items():
            assembly_file_name = scad_folder_path / (layout_name + '_assembled_' + part_name + assembly_switch_postfix + assembly_stab_postfix + scad_postfix)
            # No $fn here: each included section file sets its own, and an
            # assignment in this file would just draw an "overwritten" warning
            # from every include.
            with open(assembly_file_name, 'w') as assembly_file:
                for section_file in section_files:
                    assembly_file.write('include <%s>\n' % (section_file))
            print('Generated assembly scad file with name', assembly_file_name)


    ################################################################
    #  Wait for render processes to complete
    ################################################################
    if args.render:
        logger.debug(subprocess_dict)
        running = True
        while running == True:
            running = False
            for stl_file_name in subprocess_dict.keys():
                p = subprocess_dict[stl_file_name]
                if p is not None:
                    # running = True
                    rcode = None
                    try:
                        rcode = p.wait(.1)
                    except subprocess.TimeoutExpired as err:
                        running = True
                    if rcode is not None:
                        logger.info('Render Complete: file: %s', stl_file_name)
                        print('Render Complete: file:', stl_file_name)
                        subprocess_dict[stl_file_name] = None
            # time.sleep(1)



    logger.info('Generation Complete')

    # Summary of the sections the board was split into and their size relative to
    # the configured build plate.
    section_dimensions = keyboard.get_top_section_dimensions()
    print('\nSection summary (build plate %.1f x %.1f mm):'
          % (parameters.x_build_size, parameters.y_build_size))
    print('  %d top section(s), %d bottom section(s)'
          % (keyboard.get_top_section_count(), keyboard.get_bottom_section_count()))
    for section_number, (width, height) in enumerate(section_dimensions):
        fits = width <= parameters.x_build_size and height <= parameters.y_build_size
        print('    Section %d: %.1f x %.1f mm%s'
              % (section_number, width, height, '' if fits else '  (exceeds build plate!)'))

    if keyboard.split_recommendation is not None:
        print('\n' + keyboard.split_recommendation)

if __name__ == "__main__":
    main()
