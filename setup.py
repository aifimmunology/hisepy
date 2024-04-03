import os

from setuptools import setup, find_packages
# read the contents of your README file
from pathlib import Path
this_directory = os.path.dirname(os.path.realpath('__file__'))

desc_path = Path(this_directory + "/" + "README.rst")
long_description = desc_path.read_text()

setup(
    name='hisepy',
    version='v0.2.1',  # You can change the version as needed
    author='Paul Mariz',
    author_email='paul.mariz@alleninstitute.org',
    description='A brief description of hisepy',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/aifimmunology/fake_hisepy',  # Replace with your own URL
    packages=find_packages(),
    install_requires=[
        # List your project dependencies here
        # e.g., 'numpy', 'pandas'
        'google-cloud-storage',
        'h5py',
        'isort',
        'numpy',
        'pandas==2.1.0',
        'plotly==5.12.0',
        'pyreadr',
        'pytest',
        'PyYAML',
        'requests',
        'termcolor',
        'toml',
    ],
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        # Indicate who your project is intended for
        'Immunology', 'Statistical Regression',
        'Intended Audience :: Developers',
        'Topic :: Scientific/Engineering',

        # Pick your license as you wish (see also "license" above)
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.10",
        # "Programming Language :: Python :: 3.11",
        # "Programming Language :: Python :: 3 :: Only",
        # Add more classifiers as appropriate
        # See https://pypi.org/classifiers/ for a list
    ],
    python_requires='>=3.10',  # Adjust the Python version as needed
)
