"""
Create unix package:    python setup.py sdist
Upload to pypi:         python setup.py sdist upload
"""

import subprocess
import os
from distutils.version import LooseVersion
from setuptools import setup, find_packages, Command
# To use a consistent encoding
from codecs import open
from os import path

try:
    from pysqlite2 import dbapi2 as sqlite3
    print('using pysqlite2, sqlite3 version {}'.format(sqlite3.sqlite_version))
except ImportError:
    import sqlite3
    print('using sqlite3, sqlite3 version {}'.format(sqlite3.sqlite_version))


# min_sqlite3_version = '3.8.3'
# if LooseVersion(sqlite3.sqlite_version) < LooseVersion(min_sqlite3_version):
#     raise ImportError(('the sqlite3 library version for this python interpreter is '
#                        '{}, but a version >= {} is required; '
#                        'see https://github.com/fhcrc/taxtastic#installing').format(
#                            sqlite3.sqlite_version, min_sqlite3_version))


subprocess.call(
    ('mkdir -p taxtastic/data && '
     'git describe --tags --dirty > taxtastic/data/ver.tmp'
     '&& mv taxtastic/data/ver.tmp taxtastic/data/ver '
     '|| rm -f taxtastic/data/ver.tmp'),
    shell=True, stderr=open(os.devnull, "w"))

# must import __version__ *after* running 'git describe' above
from taxtastic import __version__

# Get the long description from the README file
here = path.abspath(path.dirname(__file__))
with open(path.join(here, 'README.rst'), encoding='utf-8') as fi:
    long_description = fi.read()


class run_audit(Command):
    """Audits source code using PyFlakes for following issues:
        - Names which are used but not defined or used before they are defined.
        - Names which are redefined without having been used.
    """
    description = "Audit source code with PyFlakes"
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        import os
        import sys
        try:
            import pyflakes.scripts.pyflakes as flakes
        except ImportError:
            print("Audit requires PyFlakes installed in your system.")
            sys.exit(-1)

        warns = 0
        # Define top-level directories
        dirs = ['taxtastic']
        for dir in dirs:
            for root, _, files in os.walk(dir):
                for file in files:
                    if file != '__init__.py' and file.endswith('.py'):
                        warns += flakes.checkPath(os.path.join(root, file))
        if warns > 0:
            print("Audit finished with total %d warnings." % warns)
        else:
            print("No problems found in sourcecode.")


params = {'name': 'taxtastic',
          'author': 'Noah Hoffman',
          'author_email': 'ngh2@uw.edu',
          'maintainer': 'Chris Rosenthal',
          'maintainer_email': 'crosenth@uw.edu',
          'description': 'Tools for taxonomic naming and annotation',
          'long_description': long_description,
          'packages': find_packages(
              exclude=['tests', 'testfiles', 'devtools', 'docs']),
          'url': 'https://github.com/fhcrc/taxtastic',
          'version': __version__,
          'license': 'GPL',
          'classifiers': [
              'License :: OSI Approved :: GNU General Public License (GPL)',
              'Development Status :: 3 - Alpha',
              'Programming Language :: Python :: 2.7',
              'Topic :: Scientific/Engineering :: Bio-Informatics'],
          'download_url': 'https://github.com/fhcrc/taxtastic',
          'package_data': {
              'taxtastic': ['data/*']},
          'entry_points': {'console_scripts': ['taxit = taxtastic.scripts.taxit:main']},
          'test_suite': 'tests',
          'install_requires': [
              'decorator>=4.1.2',
              'fastalite>=0.3',
              'DendroPy>=4.3.0',
              'jinja2>=2.9',
              'sqlalchemy>=1.0',
              'PyYAML>=3.12',
              'psycopg2>=2.7.3.1',
              'six'
          ]}

setup(**params)
