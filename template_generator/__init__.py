"""
template_generator

A small program to generate templates by replacing key names  in files and file/folder names by specific values
"""
from pathlib import Path
import os

try:
    __version__ = (Path(__file__).parent / "VERSION").read_text()
except:
    __version__ = "Unknown"
    
__author__ = "Øyvind Rørtveit"
