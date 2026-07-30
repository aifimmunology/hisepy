from setuptools import setup
import os
import sys

_here = os.path.abspath(os.path.dirname(__file__))
about = {}
with open(os.path.join(_here, 'hisepy', 'version.py')) as f:
    exec(f.read(), about)
if sys.version_info[0] < 3:
    with open(os.path.join(_here, 'README.rst')) as f:
        long_description = f.read()
else:
    with open(os.path.join(_here, 'README.rst'), encoding='utf-8') as f:
        long_description = f.read()


setup(
    name='hisepy',
    description=('.'),
    long_description=long_description,
    author='Paul Mariz',
    author_email='paul.mariz@alleninstitute.org',
    url='https://github.com/aifimmunology/hisepy',
    packages=['hisepy'],
    install_requires=[],
    use_scm_version={
        "write_to": "hisepy/version.py",
    },
    #setup_requires=["setuptools_scm"],
    version=about['__version__']
    scripts=['hisepy/config.yaml'],
    include_package_data=True,
    classifiers=[
        'Immunology', 'Statistical Regression',
        'Programming Language :: Python :: 3.7'
    ],
)