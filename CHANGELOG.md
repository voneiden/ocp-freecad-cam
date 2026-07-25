# Changelog

## [2.0.2](https://github.com/voneiden/ocp-freecad-cam/compare/v2.0.1...v2.0.2) (2026-07-25)


### Bug Fixes

* Add missing return types for some operations ([4c9aec4](https://github.com/voneiden/ocp-freecad-cam/commit/4c9aec463896fbd705264f79fa697e3fc133700e))

## [2.0.1](https://github.com/voneiden/ocp-freecad-cam/compare/v2.0.0...v2.0.1) (2026-07-25)


### Bug Fixes

* Reset tool controllers in _build ([baff6c8](https://github.com/voneiden/ocp-freecad-cam/commit/baff6c8c06b149762405a3d17da1257615e90280))

## [2.0.0](https://github.com/voneiden/ocp-freecad-cam/compare/v1.1.0...v2.0.0) (2026-05-10)


### ⚠ BREAKING CHANGES

* add AutoUnitKey to Op params
* add FreeCAD 1.1.0 support

### Features

* Add FreeCAD 1.1.0 support ([5ed8fdb](https://github.com/voneiden/ocp-freecad-cam/commit/5ed8fdb9a01b32fa173919763a93dea28e6f4c01)), closes [#51](https://github.com/voneiden/ocp-freecad-cam/issues/51)
* Add missing params to operations ([acaaf36](https://github.com/voneiden/ocp-freecad-cam/commit/acaaf36efa53493482a02d4b5fae44b9c6cbe212))


### Bug Fixes

* Add AutoUnitKey to Op params ([0cc0a58](https://github.com/voneiden/ocp-freecad-cam/commit/0cc0a58ac05ca4f989af861362f1be3991f8cce3)), closes [#40](https://github.com/voneiden/ocp-freecad-cam/issues/40)
* Add clear error message for invalid post processor ([ffabcb7](https://github.com/voneiden/ocp-freecad-cam/commit/ffabcb76b585703dd1e58ec785372daa52e80cff))
* Helix visualization issues ([ba9e3d0](https://github.com/voneiden/ocp-freecad-cam/commit/ba9e3d005fb32c65f4a43233af6e0f4a0f667ba2))
* Incorrect ClearingPattern value for grid ([77e63da](https://github.com/voneiden/ocp-freecad-cam/commit/77e63daff2e45e2758ba2134dcf2cc43e826c406))
* Profile return type missing ([28c6295](https://github.com/voneiden/ocp-freecad-cam/commit/28c6295351b0b423ad4e6ee98060c6493174eb30))
* Relax arc coordinate requirements in visualizer ([61897ce](https://github.com/voneiden/ocp-freecad-cam/commit/61897cececf0741d632cf1a3dea318c45195caa3))
* Require post_processor for job ([c41677a](https://github.com/voneiden/ocp-freecad-cam/commit/c41677a4fd08b63377e823f00721c134587d5fa1))
* Set ToolController in RampEntry dressup ([370df84](https://github.com/voneiden/ocp-freecad-cam/commit/370df84de0ac64b0877d0f2b51b43f4449cc110e))


### Documentation

* Document a know issue/limitation with offset patterns ([203c7e0](https://github.com/voneiden/ocp-freecad-cam/commit/203c7e0c124a9251be82ba22dd2c1058ae28d261))
* Update readme ([7b7a34c](https://github.com/voneiden/ocp-freecad-cam/commit/7b7a34c2ba48f929dc42e3cb0a5c9cedfcead57d))

## [1.1.0](https://github.com/voneiden/ocp-freecad-cam/compare/ocp-freecad-cam-v1.0.0...ocp-freecad-cam-v1.1.0) (2025-12-16)


### Features

* Add angle support to AutoUnit ([3372dab](https://github.com/voneiden/ocp-freecad-cam/commit/3372dabed25f8e1b365cefbc88ff45735760070d))
* Add literals for coolant mode ([add8839](https://github.com/voneiden/ocp-freecad-cam/commit/add8839477ce1a206e8fe0ebfee7bc1c8cafe013))
* Add Ramp dressup ([1de37a5](https://github.com/voneiden/ocp-freecad-cam/commit/1de37a5b805ac9fda1e90714bf0aef3950445fa2))
* Allow use of compounds/solids as operation targets ([f151a71](https://github.com/voneiden/ocp-freecad-cam/commit/f151a7149057f83fa4fffc28a177af51e1387bbf)), closes [#41](https://github.com/voneiden/ocp-freecad-cam/issues/41)


### Bug Fixes

* Add build123d Edges as valid shapes ([2bf37e6](https://github.com/voneiden/ocp-freecad-cam/commit/2bf37e60426598f0d7d347f612d98af330c00a20)), closes [#42](https://github.com/voneiden/ocp-freecad-cam/issues/42)
* Incorrect ParamMapping type ([949ae05](https://github.com/voneiden/ocp-freecad-cam/commit/949ae05c327b1112ece29cb06ce6a17a0ee6940a))
* Use apply_params in dressups ([1b8ddf8](https://github.com/voneiden/ocp-freecad-cam/commit/1b8ddf8e5663e98e7613c9f5748f1961e9e890e9))


### Dependencies

* **dev:** Add pytest-freezer ([e87238a](https://github.com/voneiden/ocp-freecad-cam/commit/e87238a3bf67274084ad306f961f567778e4a019))
* Replace black, isort, flake8 with ruff ([66655d8](https://github.com/voneiden/ocp-freecad-cam/commit/66655d8c628fdf0e9a03c5c02401a30bd81c601f))


### Documentation

* Fix typo in appimage setup example ([8e5086e](https://github.com/voneiden/ocp-freecad-cam/commit/8e5086e68687c281edd77627b231aaf50c476af0))
* Update readme on pre-commit and ruff ([fe2346d](https://github.com/voneiden/ocp-freecad-cam/commit/fe2346d0c03ac319396e631dfc16fc7fd89ebcde))
