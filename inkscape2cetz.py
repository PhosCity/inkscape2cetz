#!/usr/bin/env python
# coding=utf-8
#
# Copyright (C) 2024 PhosCity
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

__version__ = "0.0.1"

import math
import sys
import tempfile

import inkex


def normalize_path(
    shape_elem: inkex.ShapeElement, viewBoxScale: int | float
) -> inkex.Path:
    """
    Normalize path to proper scale and coordinate system.

    Parameters:
    shape_elem (inkex.ShapeElement): Any shape element whose path should be normalized
    scale (int | float): Viewbox scaling for the svg file

    Returns:
    inkex.Path: Normalized path that has transforms, viewbox scale baked in with only bezier and line commands using absolute coordinate
    """
    if shape_elem.TAG != "path":
        shape_elem = shape_elem.to_path_element()

    # Apply any transformations
    shape_elem.apply_transform()

    # Convert commands like A, S, Q, and T to cubic bezier
    elem = shape_elem.path.to_superpath().to_path()

    # Convert all commands to absolute positions
    elem = elem.to_absolute()

    # Apply viewBox scaling
    if viewBoxScale != 1:
        elem.scale(viewBoxScale, viewBoxScale, True)

    # After this, path element will contain only M, L, C, and Z commands
    return elem


def round_number(num: int | float, precision: int) -> int | float:
    """
    Rounds number to a specific precision and converts it to integer if all decimal numbers are zero

    Parameters:
    num (int | float): Number to round
    precision (int): Number of numbers are decimal

    Returns:
    int | float: Rounded number
    """
    rounded = round(float(num), precision)
    return int(rounded) if rounded.is_integer() else rounded


def shift_origin(
    x: int | float, y: int | float, element: inkex.ShapeElement, info: dict
) -> tuple[int | float, int | float]:
    """
    Svg has origin at top left of the page with downwards positive.
    Cetz has origin at the bottom left with upwards positive.
    So we shift the origin to the bottom left of the bounding_box box of selected objects
    and make the y axis positive upwards

    Parameters:
    x (int | float): x coordinate
    y (int | float): y coordinate
    element (inkex.ShapeElement): Any visible element in inkscape
    info (dict): Various infos like bounding_box, scale

    Returns:
    tuple(int | float): shifted x and y coordinate
    """
    return (
        round_number(
            element.to_dimensional(x - info["bounding_box"]["left"], to_unit="cm"),
            info["precision"],
        ),
        round_number(
            element.to_dimensional(info["bounding_box"]["bottom"] - y, to_unit="cm"),
            info["precision"],
        ),
    )


def process_style(element, info, include_markers=False, include_text_info=False):
    """
    Collect all the required styles like color, opacity, stroke etc from an element

    Parameters:
    element (inkex.ShapeElement): Any visible element in inkscape
    info (dict): Various info like bounding_box, scale
    include_markers (bool): Collect any mark information
    include_text_info (bool): Collect texty information

    Returns:
    str: Properly formatted style about an element as cetz understands it
    """

    def process_gradient_stops(stops: list, opacity: int | float) -> list:
        """
        Loop through gradient stops and collect info about each stop

        Parameters:
        stops (list): List of stops
        opacity (int | float): Opacity of whole object

        Returns:
        list: List of properly formatted style about each stop as cetz understands it
        """
        stop_collection = []

        for stop in stops:
            stop_offset = round(stop.offset * 100)

            stop_style = stop.specified_style()
            stop_color = stop_style("stop-color")
            stop_opacity = round(opacity * stop_style("stop-opacity") * 255)

            stop_collection.append(
                f'(rgb("{stop_color.to_rgb()}{stop_opacity:02X}"), {stop_offset}%)'
            )
        return stop_collection

    def process_color(color, style):
        """
        Collect color information of an element

        Parameters:
        color (inkex.Color | inkex.LinearGradient | inkex.RadialGradient): color to process
        style (inkex.Style): Style object composed for this specific element

        Returns:
        str: Properly formatted color style about an element as cetz understands it
        """
        opacity = style("opacity")
        if isinstance(color, inkex.Color):
            effective_opacity = round(opacity * style("fill-opacity") * 255)
            return f'rgb("{color.to_rgb()}{effective_opacity:02X}")'

        elif isinstance(color, inkex.LinearGradient):
            stop_collection = process_gradient_stops(color.stops, opacity)

            angle = math.degrees(
                math.atan2(
                    float(color.y2()) - float(color.y1()),
                    float(color.x2()) - float(color.x1()),
                )
            )
            stop_collection.append(f"angle: {round(angle)}deg")

            return f"gradient.linear({", ".join(stop_collection)})"

        elif isinstance(color, inkex.RadialGradient):
            color.apply_transform()
            stop_collection = process_gradient_stops(color.stops, opacity)

            bbx = info["bbx"]
            left = color.to_dimensional(bbx["left"], to_unit="cm")
            right = color.to_dimensional(bbx["right"], to_unit="cm")
            top = color.to_dimensional(bbx["top"], to_unit="cm")
            bottom = color.to_dimensional(bbx["bottom"], to_unit="cm")
            width = right - left
            height = bottom - top
            cx = round((abs(color.cx() - left) / width) * 100)
            cy = round((abs(color.cy() - top) / height) * 100)
            fx = round((abs(color.fx() - left) / width) * 100)
            fy = round((abs(color.fy() - top) / height) * 100)
            radius = round((color.r() / height) * 100)

            stop_collection.append(
                f"center: ({cx}%, {cy}%), radius: {radius}%, focal-center: ({fx}%, {fy}%)"
            )

            return f"gradient.radial({", ".join(stop_collection)})"

        elif isinstance(color, inkex.MeshGradient):
            inkex.errormsg("Mesh Gradient is not supported yet!")
            sys.exit()

        else:
            inkex.errormsg("Unsupported fill type.")
            sys.exit()

    def process_marker(style, marker_map, marker_type="start"):
        """
        Collect mark information of an element

        Parameters:
        style (inkex.Style): Style object composed for this specific element
        marker_map (dict): Dictionary that maps stock marker of inkscape to a mark available in cetz
        marker_type (str): Type of marker: start or end

        Returns:
        str: Properly formatted marker style about an element as cetz understands it
        """

        marker = style(f"marker-{marker_type}")

        if marker is None:
            return

        marker_id = marker.get("{http://www.inkscape.org/namespaces/inkscape}stockid")

        mark = marker_map.get(marker_id, None)

        if mark is None:
            if info["marker"] == "no_unknown_marker":
                return
            else:
                mark = marker_map.get("Triangle arrow")

        symbol = mark["symbol"]
        fill = mark["fill"]

        return (
            f'{marker_type}: (symbol: "{symbol}", fill: {fill})'
            if fill
            else f'start: (symbol: "{symbol}")'
        )

    style = element.specified_style()
    res = []

    # Fill
    fill = style("fill")
    if fill is not None:
        res.append(f"fill: {process_color(fill, style)}")

    # Stroke
    stroke = style("stroke")
    stroke_width = float(style("stroke-width"))
    if stroke is not None and stroke_width > 0:
        stroke_collection = []

        # Color
        if stroke is not None:
            stroke_collection.append(f"paint: {process_color(stroke, style)}")

        # Thickness
        stroke_width = element.uutounit(stroke_width, to_unit="pt")
        if stroke_width - 1 > 1e-5:
            stroke_order = style("paint-order")
            if stroke_order == "normal":
                stroke_order = "fill stroke markers"

            stroke_order = stroke_order.split()
            stroke_index = stroke_order.index("stroke")
            fill_index = stroke_order.index("fill")
            if stroke_index < fill_index:
                stroke_width /= 2

            stroke_collection.append(f"thickness: {round(stroke_width, 2)}pt")

        # Cap
        cap = style("stroke-linecap")
        if cap != "butt":
            stroke_collection.append(f'cap: "{cap}"')

        # Join
        join = style("stroke-linejoin")
        if join != "miter":
            stroke_collection.append(f'join: "{join}"')

        # Miter Limit
        miter_limit = style("stroke-miterlimit")
        if miter_limit != "4":
            stroke_collection.append(f"miter-limit: {miter_limit}")

        # Dash
        dash = [
            f"{round(element.uutounit(i, to_unit="pt"), 2)}pt"
            for i in style("stroke-dasharray")
        ]
        if len(dash) > 0:
            dash_offset = round(
                element.uutounit(style("stroke-dashoffset"), to_unit="pt"), 2
            )
            if dash_offset == 0.0:
                stroke_collection.append(f"dash: ({", ".join(dash)})")
            else:
                stroke_collection.append(
                    f"dash: (array: ({", ".join(dash)}), phase: {dash_offset}pt)"
                )

        res.append(f"stroke: ({", ".join(stroke_collection)})")
    else:
        res.append("stroke: none")

    # Markers
    if include_markers:
        marker_map = {
            "Wide arrow": {"symbol": "straight", "fill": None},
            "Wide, rounded arrow": {"symbol": "straight", "fill": None},
            "Wide, heavy arrow": {"symbol": "straight", "fill": None},
            "Triangle arrow": {"symbol": "triangle", "fill": "black"},
            "Colored triangle": {"symbol": "triangle", "fill": None},
            "Dart arrow": {"symbol": "triangle", "fill": "black"},
            "Concave triangle arrow": {"symbol": "stealth", "fill": "black"},
            "Rounded arrow": {"symbol": "triangle", "fill": "black"},
            "Dot": {"symbol": "circle", "fill": "black"},
            "Colored dot": {"symbol": "circle", "fill": None},
            "Square": {"symbol": "rect", "fill": "black"},
            "Colored square": {"symbol": "rect", "fill": None},
            "Diamond": {"symbol": "diamond", "fill": "black"},
            "Colored diamond": {"symbol": "diamond", "fill": None},
            "Stop": {"symbol": "bar", "fill": None},
            "X": {"symbol": "x", "fill": None},
            "Empty semicircle": {"symbol": "hook", "fill": None},
            "Stylized triangle arrow": {"symbol": "barbed", "fill": None},
        }
        mark = ""
        if marker_start := process_marker(style, marker_map, marker_type="start"):
            mark += marker_start

        if marker_end := process_marker(style, marker_map, marker_type="end"):
            mark += marker_end

        if mark != "":
            res.append(f"mark: ({mark})")

    # Text Info
    if include_text_info:
        font_size = style("font-size")
        font_weight = style("font-weight")
        font_style = style("font-style")

        # Font Family
        if info["ignore_font"] is False:
            font_family = style("font-family")
            generic_font_family = [
                "serif",
                "sans-serif",
                "monospace",
                "cursive",
                "fantasy",
                "system-ui",
                "ui-serif",
                "ui-sans-serif",
                "ui-monospace",
                "ui-rounded",
                "math",
                "emoji",
                "fangsong",
            ]
            if font_family in generic_font_family:
                font_family = info["default_font"]
            res.append(f"font: {font_family}")

        # Font-size
        font_size = round_number(element.uutounit(font_size, to_unit="pt"), 0)
        res.append(f"size: {font_size}pt")

        # Font Weight
        font_weight_map = {
            "normal": "regular",
            "bold": "bold",
            "100": "thin",
            "200": "extralight",
            "300": "light",
            "400": "regular",
            "500": "medium",
            "600": "semibold",
            "700": "bold",
            "800": "extrabold",
            "900": "black",
        }
        if weight := font_weight_map[font_weight]:
            if weight != "regular":
                res.append(f'weight: "{weight}"')
        else:
            res.append(f'weight: "{font_weight}"')

        # Font Style
        if font_style != "normal":
            res.append(f'style: "{font_style}"')

    return res


def find_circle_center_radius(
    x1: int | float,
    y1: int | float,
    x2: int | float,
    y2: int | float,
    x3: int | float,
    y3: int | float,
) -> tuple[int | float, int | float, int | float]:
    """
    Find center and radius of the circle that passes through three points

    Parameters:
    x1, y1 (int | float): First point that the circle passes through
    x2, y2 (int | float): Second point that the circle passes through
    x3, y3 (int | float): Third point that the circle passes through

    Returns:
    tuple[int | float]: Center x, Center y and Radius of the circle
    """
    # https://codegolf.stackexchange.com/a/2396

    x = complex(x1, y1)
    y = complex(x2, y2)
    z = complex(x3, y3)

    w = (z - x) / (y - x)
    c = (x - y) * (w - abs(w) ** 2) / 2j / w.imag - x

    return -c.real, -c.imag, abs(c + x)


def rect2cetz(rect_element: inkex.Rectangle, info: dict) -> str:
    """
    Convert rectangle element to cetz

    Parameters:
    rect_element (inkex.Rectangle): Rectangle element to convert
    info (dict): Various infos like bounding_box, scale

    Returns:
    str: Properly formatted rect element with its coordinate and style
    """
    tolerance = 1e-5

    transform = rect_element.transform
    if abs(transform.b) >= tolerance or abs(transform.c) >= tolerance:
        return path2cetz(rect_element, info)

    # We disable the corner radii here in a copy of the rectangle element
    # to get actual coordinate of the rectangle path which has been normalized.
    rect_element_copy = rect_element.copy()
    rect_element_copy.set("rx", 0)
    rect_element_copy.set("ry", 0)
    path_element = normalize_path(rect_element_copy, info["scale"])

    if len(path_element) != 5:
        inkex.errormsg("Error processing a rectangle element.")
        sys.exit()

    left, top = path_element[0].args
    right, bottom = path_element[2].args

    left, top = shift_origin(left, top, rect_element, info)
    right, bottom = shift_origin(right, bottom, rect_element, info)

    style = ", ".join(process_style(rect_element, info))

    # Grid
    output_type = "rect"
    if rect_element.label == "grid":
        output_type = "grid"

    radius_x = rect_element.rx
    radius_y = rect_element.ry
    if radius_x > tolerance or radius_y > tolerance:
        rx = round((radius_x / rect_element.width) * 100)
        ry = round((radius_y / rect_element.height) * 100)

        return f"{output_type}(({left}, {bottom}), ({right}, {top}), radius: (rest: ({rx}%, {ry}%)), {style})"
    else:
        return f"{output_type}(({left}, {bottom}), ({right}, {top}), {style})"


def circle2cetz(circle_element: inkex.Circle, info: dict) -> str:
    """
    Convert circle element to cetz

    Parameters:
    circle_element (inkex.Circle): Circle element to convert
    info (dict): Various infos like bounding_box, scale

    Returns:
    str: Properly formatted circle element with its coordinate and style
    """
    path_element = normalize_path(circle_element, info["scale"])

    # Find any three points in the normalized path of the circle
    x1, y1 = path_element[1].args[4], path_element[1].args[5]
    x2, y2 = path_element[2].args[4], path_element[2].args[5]
    x3, y3 = path_element[3].args[4], path_element[3].args[5]

    center_x, center_y, radius = find_circle_center_radius(x1, y1, x2, y2, x3, y3)
    center_x, center_y = shift_origin(center_x, center_y, circle_element, info)
    radius = round_number(
        circle_element.to_dimensional(radius, to_unit="cm"), info["precision"]
    )

    style = ", ".join(process_style(circle_element, info))
    return f"circle(({center_x}, {center_y}), radius: {radius}, {style})"


def ellipse2cetz(ellipse_element: inkex.Ellipse, info: dict) -> str:
    """
    Convert ellipse element to cetz

    Parameters:
    ellipse_element (inkex.Ellipse): Ellipse element to convert
    info (dict): Various infos like bounding_box, scale

    Returns:
    str: Properly formatted ellipse element with its coordinate and style
    """
    transform = ellipse_element.transform
    if not transform._is_URT() or transform.b >= 1e-5 or transform.c >= 1e-5:
        return path2cetz(ellipse_element, info)

    rx, ry = ellipse_element.rxry()

    # Cheat and make a copy of an ellipse and make it a circle
    ellipse_copy = ellipse_element.copy()
    ellipse_copy.set("ry", rx)

    path_element = normalize_path(ellipse_copy, info["scale"])

    # Find any three points in the normalized path of the circle
    x1, y1 = path_element[1].args[4], path_element[1].args[5]
    x2, y2 = path_element[2].args[4], path_element[2].args[5]
    x3, y3 = path_element[3].args[4], path_element[3].args[5]

    center_x, center_y, radius_x = find_circle_center_radius(x1, y1, x2, y2, x3, y3)
    center_x, center_y = shift_origin(center_x, center_y, ellipse_element, info)

    radius_y = radius_x * (ry / rx)
    radius_x = round_number(
        ellipse_element.to_dimensional(radius_x, to_unit="cm"), info["precision"]
    )
    radius_y = round_number(
        ellipse_element.to_dimensional(radius_y, to_unit="cm"), info["precision"]
    )

    style = ", ".join(process_style(ellipse_element, info))
    return (
        f"circle(({center_x}, {center_y}), radius: ({radius_x}, {radius_y}), {style})"
    )


def path2cetz(
    shape_elem: inkex.PathElement
    | inkex.Line
    | inkex.Polygon
    | inkex.Polyline
    | inkex.Rectangle
    | inkex.Ellipse,
    info: dict,
) -> str:
    """
    Convert path, line, polygon, polyline and optionally rectangle and ellipse with skew/rotation to cetz

    Parameters:
    ShapeElement (inkex.PathElement | inkex.Line | inkex.Polygon | inkex.Polyline | inkex.Rectangle | inkex.ellipse): Element to convert
    info (dict): Various infos like bounding_box, scale

    Returns:
    str: Properly formatted element with its coordinate and style
    """
    path_element = normalize_path(shape_elem, info["scale"])

    collection = []
    start_position = []
    current_position = []
    previous_command = None

    # Here, collection is a list of dictionaries
    # Each dictionary represents a shape and has two keys: paths (list of coordinates) and merge_path (boolean if path should be closed)

    for segment in path_element:
        command = segment.letter
        args = segment.args

        point = []
        for i in range(0, len(args), 2):
            x, y = shift_origin(args[i], args[i + 1], shape_elem, info)
            point.extend([x, y])

        if command == "M":
            current_position = point
            start_position = point
            collection.append({"path": []})

        elif command == "L":
            current_shape = collection[-1]
            if previous_command == "M":
                current_shape["path"].extend([*current_position, *point])
                current_shape["type"] = "line"

            elif previous_command == command:
                current_shape["path"].extend(point)

            else:
                collection.append(
                    {
                        "path": [*current_position, *point],
                        "type": "line",
                    }
                )
            current_position = point

        elif command == "C":
            bezier = [
                current_position[0],
                current_position[1],
                point[4],
                point[5],
                point[0],
                point[1],
                point[2],
                point[3],
            ]
            current_shape = collection[-1]
            if previous_command == "M":
                current_shape["path"] = bezier
                current_shape["type"] = "bezier"
            else:
                collection.append({"path": bezier, "type": "bezier"})
            current_position = [point[4], point[5]]

        elif command == "Z":
            current_shape = collection[-1]
            if current_position == start_position:
                pass
            elif previous_command == "L":
                current_shape["path"].extend(start_position)
            else:
                collection.append(
                    {
                        "path": [*current_position, *start_position],
                        "type": "line",
                    }
                )
        previous_command = command

    def create_line(shape):
        points = shape["path"]
        pairs = list(zip(points[::2], points[1::2]))
        return ", ".join(f"({x}, {y})" for x, y in pairs)

    if len(collection) == 1:
        style = ", ".join(process_style(shape_elem, info, include_markers=True))
        path = collection[0]
        path_type = collection[0]["type"]
        return f"{path_type}({create_line(path)}, {style})"
    else:
        result = []
        style = ", ".join(process_style(shape_elem, info, include_markers=False))
        for shape in collection:
            result.append(
                "%s(%s)" % (shape["type"], create_line(shape)),
            )
        return "merge-path(%s, {\n        %s\n})" % (
            style,
            "\n".join(result),
        )


def text2cetz(text_element: inkex.TextElement, info: dict, bounding_box: dict) -> str:
    """
    Convert text to cetz

    Parameters:
    text_element (inkex.TextElement): Text element to convert
    info (dict): Various infos like bounding_box, scale
    bounding_box (dict): Bounding box of current text element only

    Returns:
    str: Properly formatted text element with its coordinate and style
    """
    text = text_element.get_text()
    result = []
    for item in text.split("\n\n"):
        result.append(item.replace("\n", ""))

    style = ", ".join(process_style(text_element, info, False, True))

    x = bounding_box["left"] + (bounding_box["width"]) / 2
    y = bounding_box["top"] + (bounding_box["height"]) / 2
    x, y = shift_origin(x, y, text_element, info)

    transform = text_element.transform
    angle = 360 - round(math.degrees(math.atan2(transform.b, transform.a)))
    if angle - 1 >= 1e-5:
        return f"content(({x}, {y}), angle: {angle}deg, text({style})[{"#linebreak()".join(result)}])"
    else:
        return f"content(({x}, {y}), text({style})[{"#linebreak()".join(result)}])"


class ConvertToCetz(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument("--precision", type=int, help="rounding precision")
        pars.add_argument("--wrap", type=str, help="environment to wrap the result to")
        pars.add_argument(
            "--ignore_font", type=inkex.Boolean, help="ignore font used in svg"
        )
        pars.add_argument("--default_font", type=str, help="default font to use")
        pars.add_argument("--marker", type=str, help="handle unknown marker")

    def collect_elements(self, element: inkex.ShapeElement) -> list[inkex.ShapeElement]:
        """
        Collect svg elements by recursing inside a group.

        Parameters:
        element (inkex.ShapeElement): Any visible element in inkscape

        Returns:
        list: list of elements
        """
        collected = []

        if isinstance(element, inkex.Group):
            element.bake_transforms_recursively()
            for child in element:
                collected.append(self.collect_elements(child))
        else:
            return element

        return collected

    def get_bounding_box(
        self, selection_list: list[inkex.ShapeElement]
    ) -> tuple[list, dict]:
        """
        Collect bounding box of all selected elements

        Parameters:
        selection_list (list[inkex.ShapeElement]): List of selected elements

        Returns:
        list: List of elements along with their individual bounding box
        dict: Dictionary that has the left bottom coordinate of bounding box of all elements
        """
        # https://gitlab.com/inklinea/simple-registration/-/blob/main/simple_registration.py?ref_type=heads
        # https://github.com/Shriinivas/inkscapeboundingbox/blob/main/bound_box.py

        collected_elements = []
        for elem in selection_list:
            collection = self.collect_elements(elem)
            if isinstance(collection, list):
                collected_elements.extend(collection)
            else:
                collected_elements.append(collection)

        bounding_box = {"left": float("inf"), "bottom": 0}
        initial_state = bounding_box.copy()
        elements_id = [elem.get_id() for elem in collected_elements]

        elements_list = []

        with tempfile.NamedTemporaryFile(mode="r+", suffix=".svg") as temp_svg_file:
            cmd = [
                "--query-id=" + ",".join(elements_id),
                "--query-x",
                "--query-y",
                "--query-width",
                "--query-height",
            ]

            temp_svg_file.write(self.svg.root.tostring().decode("utf-8"))
            temp_svg_file.read()
            my_query = inkex.command.inkscape(temp_svg_file.name, *cmd)  # pyright: ignore [reportAttributeAccessIssue]
            bboxVals = [line.split(",") for line in my_query.strip().split("\n")]

            for i, (x, y, w, h) in enumerate(zip(*bboxVals)):
                x, y, w, h = map(
                    lambda v: self.svg.to_dimensional(float(v), to_unit="px"),
                    (x, y, w, h),
                )
                bounding_box["left"] = min(x, bounding_box["left"])
                bounding_box["bottom"] = max(y + h, bounding_box["bottom"])

                elements_list.append(
                    {
                        "element": collected_elements[i],
                        "bounding_box": {
                            "left": x,
                            "top": y,
                            "right": x + w,
                            "bottom": y + h,
                            "width": w,
                            "height": h,
                        },
                    }
                )

        if bounding_box == initial_state:
            inkex.errormsg("Could not determine the bounding box of selected objects.")
            sys.exit()

        return elements_list, bounding_box

    def effect(self):
        """
        Main function that runs everything and displays cetz output
        """
        # This grabs selected objects by z-order, ordered from bottom to top
        selection_list = self.svg.selection.rendering_order()
        if not selection_list:
            inkex.errormsg("No object was selected!")
            return

        element_list, bounding_box = self.get_bounding_box(selection_list)

        info = {
            "bounding_box": bounding_box,
            "scale": self.svg.scale,
            "precision": self.options.precision,
            "ignore_font": self.options.ignore_font,
            "default_font": self.options.default_font,
            "marker": self.options.marker,
        }

        result = []

        for item in element_list:
            element = item["element"]
            info["bbx"] = item["bounding_box"]
            if isinstance(element, inkex.Rectangle):
                result.append(rect2cetz(element, info))

            elif isinstance(element, inkex.Circle):
                result.append(circle2cetz(element, info))

            elif isinstance(element, inkex.Ellipse):
                result.append(ellipse2cetz(element, info))

            elif isinstance(element, inkex.TextElement):
                result.append(text2cetz(element, info, item["bounding_box"]))

            elif (
                isinstance(element, inkex.PathElement)
                or isinstance(element, inkex.Line)
                or isinstance(element, inkex.Polygon)
                or isinstance(element, inkex.Polyline)
            ):
                result.append(path2cetz(element, info))

            else:
                inkex.errormsg("Unsupported object selected!")
                return

        # Output
        space_count = 1
        if self.options.wrap == "figure":
            inkex.errormsg("#figure(")
            inkex.errormsg("    cetz.canvas({")
            space_count = 8
        elif self.options.wrap == "align":
            inkex.errormsg("#align(")
            inkex.errormsg("    center,")
            inkex.errormsg("    cetz.canvas({")
            space_count = 8
        else:
            inkex.errormsg("#cetz.canvas({")
            space_count = 4

        inkex.errormsg(" " * space_count + "import cetz.draw: *")
        for res in result:
            inkex.errormsg(" " * space_count + res)
        space_count -= 4
        inkex.errormsg(" " * space_count + "})")

        if self.options.wrap in ["figure", "align"]:
            inkex.errormsg(")")


if __name__ == "__main__":
    ConvertToCetz().run()
