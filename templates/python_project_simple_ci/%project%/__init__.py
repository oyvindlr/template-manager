"""
%project%

%description%
"""
from pathlib import Path
import os

try:
    __version__ = (Path(__file__).parent / "VERSION").read_text()
except:
    __version__ = "Unknown"
    
__author__ = "%author%"


