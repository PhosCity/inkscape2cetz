# inkscape2cetz

Inkscape extension to export selected objects to cetz (Typst) format.
![GUI](https://raw.githubusercontent.com/PhosCity/inkscape2cetz/refs/heads/main/assets/gui.png)

## Showcase

https://github.com/user-attachments/assets/82fa3216-382a-4bc6-9e12-48d73f42d474

## This sucks and you shouldn't use it

There are many reasons why you should not use this. The first being it simply
does not work in all cases. There will always be cases where the export will
look different than how it looks in inkscape. When it does that it's because
of either of the cases:

1. Cetz does not support what svg does.
1. Cetz supports it but I didn't know about it.
1. Cetz supports it but I couldn't figure out how to export it.
1. I messed up exporting something somewhere (of which I'm sure are many).

You will find yourself fixing a lot of things manually after exporting it to typst.
The output by this extension is also very verbose.
You might not like how dirty cetz code exported by this looks like.

It is also always better to write cetz code yourself. You can write a lot of clever cetz code. You also cannot make dynamic cetz code with this that makes use of Typst scripting power. This extension is preventing you from the catharsis you'll feel after successfully making a
figure by yourself.

I'm also not a programmer. I just code for fun so the code will not be pretty to look at either.

## Installation

Copy extension files `inkscape2cetz.inx` and `inkscape2cetz.py` into your extension directory and restart Inkscape. This is the directory listed at `Edit > Preferences > System: User extensions.` in Inkscape.

## Prerequisites

There are some things you _need_ to do for proper export.

1. Set the size of the document in inkscape the same as your typst document. This will also give you an idea of how the shape will look in your typst document.
1. Set the units used to "cm" as the coordinates we will use in cetz will be centimeters.
1. Make sure that the scale is 1.
1. If precision is of any importance to you, enable grid and snap in inkscape.



https://github.com/user-attachments/assets/c31836e7-270c-44bb-a42b-79278bec94f2



## Supported SVG attributes

- attributes essential to the elements like rectangle, circle, ellipse, line, path etc.
- select presentation attributes and inline CSS style attributes
  - colors/alpha for fill and stroke
  - stroke width
  - stroke join
  - stroke cap
  - stroke dash
  - gradient
  - markers
- transform (translate, scale, rotate, skewX, skewY, matrix)

## Supported SVG Element

### Rectangle and Grids

Rectangle element along with its attributes is supported. If rectangle is skewed or rotated, it will be converted to paths. Scaled or translated rectangle however will remain a rectangle.

If you want to convert rectangle to grid, select a rectangle element, go to `Object -> Object Properties` and type `grid` in the label textbox. The stroke color of the rectangle will be used as the color of the grid. This means what looks like a rectangle in inkscape will be converted to grid in cetz if it is manually labelled as `grid` by the user.

![grid](https://raw.githubusercontent.com/PhosCity/inkscape2cetz/refs/heads/main/assets/grid.png)

### Circle and Ellipse

Circle and ellipse elements along with its attributes is supported. If the element is skewed or rotated, it will be converted to paths. Scaled or translated element however will remain a circle or ellipse.

### Line, Polygon, Path

All of them are treated as path. Markers are supported for these elements. For closed paths, `merge-path` function of cetz is used.

### Text

Some support of text is provided. It is always better to use the same font in both inkscape and typst document for accuracy. You can use inline math like `$A = pi r^2$` or typst markup `#underline[text]` as text which will be used in cetz. The position of the text in cetz is the center of the bounding box of text as seen in inkscape. So you should try to position the text with its center at the exact location where you want to position it in cetz. Complex transforms of text as well as many attributes of text element is simply ignored.

Gradients and rotation are also supported in text.

### Groups

Elements inside group in inkscape is processed recursively as individual elements.
