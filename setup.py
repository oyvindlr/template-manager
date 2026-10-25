from setuptools import setup

setup(
    name='template_manager',    
    packages=['template_manager'],
    package_data={'template_manager': ['settings.toml', 'skills/*/SKILL.md']},
)
