from setuptools import setup
import os
import sys

_here = os.path.abspath(os.path.dirname(__file__))

if sys.version_info[0] < 3:
    with open(os.path.join(_here, 'README.rst')) as f:
        long_description = f.read()
else:
    with open(os.path.join(_here, 'README.rst'), encoding='utf-8') as f:
        long_description = f.read()

version = {}
with open(os.path.join(_here, 'hisepy', 'version.py')) as f:
    exec(f.read(), version)

setup(
    name='hisepy',
    version=version['__version__'],
    description=('.'),
    long_description=long_description,
    author='Paul Mariz',
    author_email='paul.mariz@alleninstitute.org',
    url='https://github.com/aifimmunology/hisepy',
    packages=['hisepy'],
    install_requires=[
        'pandas', 'numpy', 'PyYAML', 'scipy', 'anndata',
        'google-cloud-storage', 'importlib', 'Frozen-Flask', 'requests',
        'h5py', 'google', 'pipreqs', 'pip-tools', 'pyreadr', 'termcolor'
    ],
    scripts=['hisepy/config.yaml'],
    include_package_data=True,
    classifiers=[
        'Immunology', 'Statistical Regression',
        'Programming Language :: Python :: 3.7'
    ],
)
