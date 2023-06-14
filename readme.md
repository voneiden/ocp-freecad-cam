# Installation

ocp-freecad-cam requires currently a relatively fresh build of FreeCAD, ie. weekly build from
https://github.com/FreeCAD/FreeCAD-Bundle/releases/tag/weekly-builds

The Path module of FreeCAD has seen major refactorings in 2023 so older versions are not compatible.

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

## Configuring FreeCAD
This library configures FreeCAD on the fly and attempts to
restore original configuration after it is done. The following 
settings are configured automatically:

* General -> Unit System
  * For metric using: `Metric Small Parts & CNC`
  * For imperial using: `Imperial Decimal` (or `Building US`) 
* Path -> Advanced -> Enable OCL dependent features


# Limitations

Pocket3D does not work, possibly related to https://github.com/FreeCAD/FreeCAD/issues/6815 - shouldn't be a big loss
though, Surface3D can get the same things done IMO.

VCarve can produce unstable toolpaths, but that is probably a bug in the underlying openvoronoi library. Tweaking the 
job params may help.