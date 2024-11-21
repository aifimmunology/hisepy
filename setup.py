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
        'pandas==2.2.3', 'numpy==1.26.4', 'PyYAML==6.0.2', 'plotly==5.24.1',
        'dash==2.18.2', 'kaleido==0.2.1', 'google-cloud-storage==2.18.2',
        'requests==2.32.3', 'h5py==3.12.0', 'google==3.0.0', 'pipreqs==0.4.12',
        'pip-tools==7.4.1', 'pyreadr==0.5.2', 'termcolor==2.5.0',
        'pathlib==1.0.1'
    ],
    scripts=['hisepy/config.yaml'],
    include_package_data=True,
    classifiers=[
        'Immunology', 'Statistical Regression',
        'Programming Language :: Python :: 3.7'
    ],
)
