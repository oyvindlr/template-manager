from setuptools import setup
from pathlib import Path
import markdown

long_description = Path("README.md").read_text()

markdown.Markdown().convertFile("README.md", "%project%/README.html")

setup(
    name='%project%',    
    packages=['%project%'],
    package_data={'%project%': ['README.html']},
    long_description=long_description,
    long_description_content_type='text/markdown',
)
