- [Keyboard Case and Plate STL Generator With Automatic Model Segmentation](#keyboard-case-and-plate-stl-generator-with-automatic-model-segmentation)
- [How it Works](#how-it-works)
- [Setup](#setup)
  - [Requirements](#requirements)
  - [Development checks](#development-checks)
  - [Usage](#usage)
  - [Parameters](#parameters)
    - [Splitting Parameters Across Files](#splitting-parameters-across-files)
    - [Schema](#schema)
    - [Renamed Parameters](#renamed-parameters)
  - [Per-Key Options](#per-key-options)
- [Example Output](#example-output)
  - [Output Format](#output-format)
  - [Small Layout Test](#small-layout-test)
  - [Full Size ANSI](#full-size-ansi)
- [Printed Part](#printed-part)
- [Acknowledgements](#acknowledgements)

# Keyboard Case and Plate STL Generator With Automatic Model Segmentation
This is meant to generate a scad and or stl file from a [keyboard-layout-editor](http://www.keyboard-layout-editor.com/) layout file. 

Additionally the model can be automatically segmented so that the parts will fit within the build area of your 3d printer


# How it Works
The program takes a keyboard-layout-editor json file as one of the inputs along with an optional parameter json file to customize other parts of the resulting model

The program can then generate a number of different items. The entire case can be generated as a single model or the case can be broken up so that parts will fit within the build size of your 3d printer. The build size is one of the values that can be placed in the optional parameters file.


# Setup
## Requirements

- **Python**: Python is required to run the program. This was built using Python 3.8.10 but I expect newer versions should work fine

- **[SolidPython](https**://github.com/SolidCode/SolidPython)**: This program relies on SolidPython to generate the actual OpenSCAD script. Dependencies are managed with [Poetry](https://python-poetry.org/). Install them with:

  ```
  poetry install
  ```
- **[OpenSCAD](https://openscad.org/)**: In order to render STL files you will have to have OpenSCAD installed and the OpenSCAD executable must be on your path. OpenSCAD downloads can be found here https://openscad.org/downloads.html

## Development checks

```
poetry run black .           # format; --check reports without writing
poetry run ruff check .      # fast lint; --fix applies the safe fixes
poetry run pylint *.py tests/*.py
poetry run mypy
poetry run pytest
```

Black runs on its defaults, so formatting is not something to have an opinion
about. It wraps at 88 columns while ruff and pylint allow 150, which leaves the
line length checks to catch only the long strings and comments black cannot
split.

Ruff settings live in `pyproject.toml` and pylint's in `.pylintrc`. Design
metrics (argument counts, statement counts and so on) are pylint's job, so the
`PL` rules are left out of the ruff selection to avoid duplicate reports.

## Usage
- Here is an example of the program cli usage
  ![keyboard_stl_generator.py usage](/images/usage.png)

- Basic usage
  
  ```
  poetry run python keyboard_stl_generator.py -i layout_filename.json
  ```

  This will generate the entire case as one piece. It will generate top, bottom, plate, and all scad files

- **-f option**: This option defines the number of faces that will be used when rendering a circle. I suggest using at least 32

- **-a option**: This will generate models for all of the separate model sections based on the 3d printer build plate size

- **-e option**: This generates a potentially useful exploded view where all sections are in one model but they are separated so they can be seen more easily

- **-s option**: This is used to generate just the model for a specific section

## Parameters
- This is an example of a simple parameters file [parameters.json](/parameters.json)
- Parameter files are parsed as [JSON5](https://json5.org/), so `//` and `/* */` comments and trailing commas are allowed. A plain JSON file is still valid JSON5. Files may be named `.json` or `.json5`

### Splitting Parameters Across Files
- A set of parameters can be split across several files, so that things like the build plate size or a switch and stabilizer choice can be written once and shared between boards
- A file pulls in others with the **include** key. Paths are relative to the file doing the including
  ```
  {
      "include": ["base/printer.json", "base/mx_switches.json"],

      "case_height": 18
  }
  ```
- Files can also be listed on the command line by repeating the `-p` option
  ```
  poetry run python keyboard_stl_generator.py -i layout.json -p base/printer.json -p my_board.json
  ```
- **Later always wins.** Includes are merged in the order they are listed, then the file's own parameters are applied over the top, so a file always overrides what it includes. Where the `include` key sits within the file makes no difference. Files given with `-p` are merged in the order they appear on the command line
- Each `-p` file is resolved in full, includes and all, before the next one is merged over it. So a later file's includes still beat an earlier file's own parameters: with `-p first.json -p second.json`, where `second.json` includes `base.json`, a parameter set in `base.json` overrides the same parameter set directly in `first.json`
- An included file may include further files. A file that includes itself, directly or in a loop, is an error
- Merging is per parameter, not per part of a parameter: a file that sets `custom_switch` replaces the whole of an included `custom_switch` rather than merging into it
- Every file must be named `.json` or `.json5` and must be utf-8 encoded

### Schema
- [parameters.schema.json](/parameters.schema.json) describes every parameter, so an editor can offer completion and flag mistakes as you type. The program itself also rejects a parameter it does not recognise, rather than building the model from the default
- The program checks every parameter file against the same schema as it loads, so a value of the wrong type or outside the allowed range is reported by name instead of being used. A quoted `"false"` is a string rather than a boolean, and would otherwise turn a feature on
- Point an editor at it by adding a `$schema` key to the parameter file
  ```
  {
      "$schema": "./parameters.schema.json",

      "case_height": 18
  }
  ```
- The schema rejects any parameter it does not know about, so a block is disabled by commenting it out rather than by renaming its key

### Renamed Parameters
- These parameters were renamed. The old names are not accepted: a file still using one is rejected with an error naming the parameter that replaced it
  - **plate_wall_thickness** is now **case_wall_thickness**
  - **hole_width** is now **cable_hole_width**
  - **hole_height** is now **cable_hole_height**

- Here is a list of the possible parameters and what they do
  - 3d Printer Related Parameters
    - **x_build_size:** X build plate size in mm
    - **y_build_size:** Y build plate size in mm
    - **kerf:** kerf to allow for expansion of material, usefully giving switch holes a bit more space to fit better
  - Switch and Stabilizer Parameters
    - **switch_type:** Switch type. Default: mx_openable. Options: mx_openable, mx, mx_alps, alps, custom (requires custom shape parameters)
    - **stabilizer_type:** Stabilizer type. Default: cherry_costar. Options: cherry_costar, cherry, costar, alps
    - **custom_switch:** Defines the parameters for a custom switch shape. If this is defined it overrides the switch_type selection
      - **points:** List of x, y coordinates. The coordinates must be defined where (0, 0) is the centre of the cutout shape. ex. This would be a 14x14 mm square [[7, 7], [7, -7], [-7, -7], [-7, 7]]
      - **path:** List that defines the order that the points should be traversed to draw the shape. If this is omitted the list of points will be followed in the order the are defined
      - **EXAMPLE:** The following example would create a 14x14 mm square cutout
        ```
        "custom_switch": {
            "points": [
                [7, 7],
                [7, -7],
                [-7, -7],
                [-7, 7]
            ],
            "path": [0, 1, 2, 3]
        }
        ```
  - Plate Only parameters
    - **plate_supports:** Generate support ridges that help to strengthen the plate true or false
    - **support_bar_height:** How far down from the top of the plate the support bars should be in mm
    - **support_bar_width:** How wide the support bars should be in mm
  - Plate and Body Parameters
    - **plate_thickness:** How thick the plate should be. This will affect how well switched hold into the plate in mm
    - **top_margin:** amount of extra material that should be added to top of plate in mm
    - **bottom_margin:** amount of extra material that should be added to bottom of plate in mm
    - **left_margin:** amount of extra material that should be added to left of plate in mm
    - **right_margin:** amount of extra material that should be added to right of plate in mm
    - **case_height:** the height of the case. When tilt is used this will be height of the lowest part of the case in mm
    - **case_wall_thickness:** How thick the walls of the case should be in mm
    - **plate_corner_radius:** The radius to be used in rounding corners of the case in mm
    - **bottom_cover_thickness:** The thickness of the base plate of the case in mm
    - **tilt:** The number of degrees the case should be tilted forward
  - Mounting Screw Parameters
    - **screw_count:** The number of screw holes to generate. If a cable hole is added and a screw hole would interfere with it the screw hole is not created
    - **screw_diameter:** The diameter of the screws to be used in mm
    - **screw_edge_inset:** How far in off the edge of the plate should the centre of the screw hole be.
  - Cable Hole Parameters
    - **cable_hole:** Generate a hole in the back of the case for a cable. true or false
    - **cable_hole_x_offset:** Horizontal centre of the cable hole in mm, measured from the left edge of the case. Omit (or null) to centre the hole on the key field.
    - **cable_hole_width:** The width of the cable hole in mm
    - **cable_hole_height:** The height of the cable hole in mm
    - **cable_hole_down_offset:** How far down from the bottom of the plate thickness should the cable hole be placed.
    - **cable_diameter:** The diameter of the cable. Used to create a strain relief clamp that holds the cable in place so it does not tug on an internal connector
  - Custom Cutout Shapes: These options allow for defining extra cutouts on the plate for things like oled displays or encoders.
    - **custom_polygons:** Define a set of custom polygons to be cutout of the top plate
      - **type:** The type of shape to create. Options: circle, rectangle, polygon
      - **r (circle):** Radius.
      - **d (circle):** Diameter. Used only when r is not given
      - **width (rectangle):** Width of rectangle. If only width is defined the shape will be a square with matching height and width
      - **height (rectangle):** Height of rectangle. If only height is defined the shape will be a square with matching height and width
      - **points (polygon):** List of x, y coordinates that define the vertices of a polygon
      - **path (polygon):** List that defines the order that the points should be traversed to draw the shape. If this is omitted the list of points will be followed in the order the are defined
      - **coordinates:** The coordinates defining x and y distance from the origin the cutout should be moved from. 0, 0 is the bottom left of the keyboard. For circle and rectangle the origin is the bottom left of the shape. For polygon the origin is defined by the points in the points list
      - **EXAMPLE:**
        ```
        "custom_polygons": [
            {
                "type": "circle",
                "d": 7.5,
                "coordinates": [
                    [114.3, 110]
                ]
            },
            {
                "type": "polygon",
                "points": [
                    [0, 0],
                    [-10, 13],
                    [5, 17]
                ],
                "coordinates": [
                    [5, 5]
                ]
            },
            {
                "type": "rectangle",
                "width": 12.5,
                "coordinates": [
                    [0, 0]
                ]
            }
        ]
        ```
  - Custom PCB Parameters: These options are to be used when you want to have a case generated to fit a specific PCB including the mounting holes in the PCB. This was set up specifically to handle easily creating a case for a PCB built in kicad. Mileage may vary for other PCBs
    
    - **custom_pcb:** Generate the case to fit a specific PCB. true or false
    - **pcb_width:** The width of the PCB
    - **pcb_height:** The height of the PCB
    - **pcb_top_left_coordinates:** The coordinates that should represent the top left corner of the PCB. In kicad this would be the actual x,y coordinates of the top left corner in the PCB editor. 
      - **NOTE: If using a custom PCB and custom screw holes for the PCB the custom_screw_hole_coordinates_origin parameter must be in the same coordinate system as the value of pcb_top_left_coordinates**
    - **pcb_left_switch_center_x_coordinate:** The X coordinate for the centre of the left most switch on the layout. 
    - **pcb_top_switch_center_y_coordinate:** The Y coordinate for the centre of the top most switch on the layout.
    - **pcb_case_top_margin:** The space between the top edge of the PCB and the inside of the case wall
    - **pcb_case_bottom_margin:** The space between the bottom edge of the PCB and the inside of the case wall
    - **pcb_case_right_margin:** The space between the right edge of the PCB and the inside of the case wall
    - **pcb_case_left_margin:** The space between the left edge of the PCB and the inside of the case wall

## Per-Key Options
- Some options are set per key in the layout file itself rather than in the parameters file. These use fields from the keyboard-layout-editor format.
  - **p (raised switch height):** The keyboard-layout-editor profile field is repurposed as a per-switch plate height offset in mm. Set it to a number (as a string) to raise a switch above the rest of the plate by that many mm. The switch cutout, its plate-mounted support, and the stabilizer/support cutouts are all lifted together, and the support skirt is stretched back down so it still lands on the base plate, forming a solid raised pedestal. This is useful when some keys use taller keycaps or a different keycap row/profile and need to sit higher.
    - Like rotation, the value is **sticky**: it applies to the key it is set on and every following key until it is changed. Set it back to `"0"` to return to the flat plate.
    - `0` (or omitting it) renders exactly as before.
    - **NOTE:** This does not currently work in combination with rotated keys (`r`/`rx`/`ry`).
    - **EXAMPLE:** In this row `W` and `E` are raised 4 mm while `Q` and `R` stay flat
      ```
      [
        "Q",
        { "p": "4" }, "W", "E",
        { "p": "0" }, "R"
      ]
      ```

# Example Output
## Output Format
- The program exports 4 different files for each model it is set to generate
  - **top**: the top part of a complete case. meant to be screwed to the bottom to make a complete case
  - **bottom**: the bottom of the case with screw posts to connect it to the top of the case
  - **plate**: the plate only with no case walls. The plate still includes the mounting holes
  - **all**: This is just a render of the entire case as one piece. Not really meant for printing just for reference
- The files will be exported into a folder within the same folder where the layout json file is. The folder will have the name of the layout file without the .json extension
- There will be separate scad and stl folders in the export folder


## Small Layout Test
- This shows testing done using a small layout and changing the printer build plate settings to force it to split the design up.

  This is an image of the layout design on keyboard-layout-editor

  ![small_test_layout.png](/images/small_test_layout/small_test_layout.png)

- If just passing in the layout file with the "-i" option the entire case will be generated. An example of the top of the case of that model is shown below

  ![small_test_top.png](/images/small_test_layout/small_test_top.png)

- using the "-a" option it will generate files for 2 different models that make up the entire layout. The images bellow show the separate section top case models

  ![small_test_top_0.png](/images/small_test_layout/small_test_top_0.png)

  ![small_test_top_1.png](/images/small_test_layout/small_test_top_1.png)


- using the "-e" file will generate an exploded view of the case where all the sections are shown but they are offset to be viewed more easily. See the image below

  ![small_test_exploded_top.png](/images/small_test_layout/small_test_exploded_top.png)


## Full Size ANSI
- Bellow is and exploded view of the generated model for a full size keyboard

  ![small_test_exploded_top.png](/images/full_size/full_size_exploded_top.png)


# Printed Part
Here are some pictures of that raw parts from the printer and the assembled case

- Topside of Top
  ![top_topside.jpg](/images/small_test_layout/top_topside.jpg)

- Underside of Top
  ![top_underside.jpg](/images/small_test_layout/top_underside.jpg)

- Top edge on view
  ![top_edge.jpg](/images/small_test_layout/top_edge.jpg)

- Focus on stabilizer cutout
  ![top_stab_cutout.jpg](/images/small_test_layout/top_stab_cutout.jpg)

- Bottom
  ![bottom.jpg](/images/small_test_layout/bottom.jpg)

- Bottom edge on view
  ![bottom_edge.jpg](/images/small_test_layout/bottom_edge.jpg)

- Assembled Front
  ![assembled_front.jpg](/images/small_test_layout/assembled_front.jpg)

- Assembled Side
  ![assembled_side.jpg](/images/small_test_layout/assembled_side.jpg)

- Assembled Tilt 
  ![assembled_tile.jpg](/images/small_test_layout/assembled_tilt.jpg)


# Acknowledgements
Shout out to Will Stevens https://github.com/swill for his plate generator that provided inspiration and very useful measurements. The swillkb plate and case generator is here http://builder.swillkb.com/
