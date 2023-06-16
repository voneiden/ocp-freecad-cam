import os
import sys

# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "ocp-freecad-cam"
copyright = "2023, Matti Eiden"
author = "Matti Eiden"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = ["sphinx.ext.autodoc", "sphinx_rtd_theme", "sphinx_tabs.tabs"]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "sphinx_rtd_theme"

html_static_path = ["_static"]

sys.path.append(os.path.join(os.getcwd(), "../src/"))

# autodoc_member_order = "bysource"

autodoc_typehints_format = "fully-qualified"
autodoc_mock_imports = [
    "Path",
    "FreeCAD",
    "Part",
    "OCP",
    "PathScripts",
    "cadquery",
    "build123d",
]
