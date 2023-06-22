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
ocp-freecad-cam does not attempt to install runtime dependencies. Your environment must have available
CadQuery and/or Build123d, or just OCP if you're feeling raw.

ocp-freecad-cam is available on pypi: https://pypi.org/project/ocp-freecad-cam/

ocp-freecad-cam requires currently a relatively fresh build of FreeCAD, ie. weekly build from
https://github.com/FreeCAD/FreeCAD-Bundle/releases/tag/weekly-builds

The Path module of FreeCAD has seen major refactorings in 2023 so older versions are not compatible.

## Runtime dependencies summary
* FreeCAD weekly 2023-06-04 or newer
* [OCP](https://github.com/CadQuery/OCP)
  * [CadQuery](https://github.com/CadQuery/cadquery)
  * [Build123d](https://github.com/gumyr/build123d)

## Dev dependecies

Dev dependencies are listed in requirements-dev.txt, generated from requirements-dev.in with `pip-compile`

## Using FreeCAD AppImage

Weekly AppImage is an easy way to get started. Download the AppImage, place it in a suitable empty folder
and extract it.

```bash
mkdir ~/freecad
cp ~/Downloads/FreeCAD_weekly-builds-33345-2023-06-04-conda-Linux-x86_64-py310.AppImage ~/freecad
cd ~/freecad
chmod +x ./FreeCAD_weekly-builds-33345-2023-06-04-conda-Linux-x86_64-py310.AppImage
./FreeCAD_weekly-builds-33345-2023-06-04-conda-Linux-x86_64-py310.AppImage --appimage-extract
```

## Configuring FreeCAD paths
For this module to work, it needs to be able to find 

1) FreeCAD C libraries
2) FreeCAD Path python libraries
3) (AppImage only?) Some other Python modules located in FreeCAD's site-packages

This can be done by updating your virtual environment PYTHONPATH or by creating a pth file in site-packages.

The three paths (also contents of the .pth file) for the above AppImage example are

```bash
/home/user/freecad/squashfs-root/usr/lib
/home/user/freecad/squashfs-root/usr/Mod/Path
/home/user/freecad/squashfs-root/usr/lib/python3.10/site-packages/
```

in a file like 

`/home/user/miniconda3/envs/cq/lib/python3.10/site-packages/freecad.pth`


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
