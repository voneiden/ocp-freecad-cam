![image](https://github.com/voneiden/ocp-freecad-cam/assets/437576/79a0247a-c28c-43b0-b324-b71881ba3d96)


# Overview

oc-freecad-cam exposes FreeCAD's Path workbench in a fluent python API that takes
OCP TopoDS_Shape objects and their wrappers from CadQuery and Build123d to enable generating
parametric tool paths from the comfort of your keyboard.

![image](https://github.com/voneiden/ocp-freecad-cam/assets/437576/48264cf9-6155-4f24-8094-0bb9aab00777)


⚠ NOTE ⚠
--------

This project is fairly experimental at this stage. Expect bugs and always
double-check the generated gcode for naughty surprises.
# Usage

See documentation at 
https://ocp-freecad-cam.readthedocs.io/en/latest/

# Installation

ocp-freecad-cam is available on pypi: https://pypi.org/project/ocp-freecad-cam/
ocp-freecad-cam does not attempt to install runtime dependencies since it's designed to run with
any combination of these three:

* [CadQuery](https://github.com/CadQuery/cadquery)
* [Build123d](https://github.com/gumyr/build123d)
* [OCP](https://github.com/CadQuery/OCP)

Additionally, FreeCAD module needs to be available.

## General guideline for hooking on FreeCAD

There are at least three options to approach this

1) Using the FreeCAD Python interpreter
2) Using system interpreter with the same major version as the FreeCAD Python interpreter
3) Compiling FreeCAD to use the system interpreter

Number one is now the recommended way and will be documented below

## Acquiring FreeCAD

Again, three options. Please use at least version 0.21.

1) Official distributions https://www.freecad.org/downloads.php
2) Official portable packages https://github.com/FreeCAD/FreeCAD-Bundle/releases
   * includes weekly packages
3) voneiden's fork of portable packages https://github.com/voneiden/FreeCAD-Bundle/releases
   * uses an older version of OpenSSL and there are also some python 3.11 packages

## Linux AppImage installation example using a venv

This is fairly straightforward. Download the AppImage, extract it, create a virtual environment
from the included interpreter, include lib, activate it and install your preferred packages. 

* https://docs.python.org/3/library/venv.html

```bash 
mkdir freecad
cd freecad 
wget https://github.com/voneiden/FreeCAD-Bundle/releases/download/0.21.2/FreeCAD_0.21.2-2023-12-26-conda-Linux-x86_64-py311.AppImage
chmod +x FreeCAD_0.21.2-2023-12-26-conda-Linux-x86_64-py311.AppImage
./FreeCAD_0.21.2-2023-12-26-conda-Linux-x86_64-py311.AppImage --appimage-extract
./squashfs-root/usr/bin/python -m venv --system-site-packages fcvenv
echo "$PWD/squashfs-root/usr/lib" > fcvenv/lib/python3.11/site-packages/freecad.pth
source fcenv/bin/activate
pip install cadquery build123d ocp-freecad-cam 
```

Test that your interpreter works by running

```bash 
python -c "import FreeCAD"
```

## Windows 7z installation example
While I would suggest using WLS, if you want to stick to pure windows, the general idea is the same 
as above in the linux example with two exceptions. 

1) Instead of `"$PWD/squashfs-root/usr/lib" > fcvenv/lib/python3.11/site-packages/freecad.pth` use 

```shell
"$($PWD)\..\src" | Out-File -FilePath "fcvenv\Lib\site-packages\ocp_freecad_cam.pth"
```

or create the pth file manually somehow. Just note that the venv file structure is a bit different on Windows.

2) Instead of `source` you activate the venv with just

```shell
.\fcvenv\Scripts\activate
```


## Dev dependecies

Dev dependencies are listed in requirements-dev.txt, generated from requirements-dev.in with `pip-compile`

# Limitations

Pocket3D does not work, possibly related to https://github.com/FreeCAD/FreeCAD/issues/6815 - shouldn't be a big loss
though, Surface3D can get the same things done IMO.

VCarve can produce unstable toolpaths, but that is probably a bug in the underlying openvoronoi library. Tweaking the 
job params may help.

# Contributing

Contributions are welcome.

* Missing params, fixes
* Tests
* Documentation

## PR's

Apply black and isort and ensure that tests pass. Preferably also include test coverage for new code.
