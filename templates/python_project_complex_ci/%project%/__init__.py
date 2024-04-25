"""
%project%

%description%
"""
from importlib.metadata import version, PackageNotFoundError

try:
    __version__ =  version("%project%")
except PackageNotFoundError:
    __version__ = "Unknown. Not installed via pip?"


__author__ = "%author%"
