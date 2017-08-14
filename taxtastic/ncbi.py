# This file is part of taxtastic.
#
#    taxtastic is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    taxtastic is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with taxtastic.  If not, see <http://www.gnu.org/licenses/>.
"""
Methods and variables specific to the NCBI taxonomy.
"""

import itertools
import logging
import os
import re
import urllib
import zipfile
import random
import string
from operator import itemgetter

import sqlalchemy
from sqlalchemy import (Column, Integer, String, Boolean,
                        ForeignKey, Index, MetaData)
from sqlalchemy.orm import relationship
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.declarative import declarative_base


log = logging.getLogger(__name__)


DATA_URL = 'ftp://ftp.ncbi.nih.gov/pub/taxonomy/taxdmp.zip'

# For rank order: https://en.wikipedia.org/wiki/Taxonomic_rank
RANKS = [
    'forma',
    'varietas',
    'subspecies',
    'species',
    'species_subgroup',
    'species_group',
    'subgenus',
    'genus',
    'subtribe',
    'tribe',
    'subfamily',
    'family',
    'superfamily',
    'parvorder',
    'infraorder',
    'suborder',
    'order',
    'superorder',
    'cohort',
    'infraclass',
    'subclass',
    'class',
    'superclass',
    'subphylum',
    'phylum',
    'superphylum',
    'subkingdom',
    'kingdom',
    'superkingdom',
    'root',
    'no_rank',
]


# Components of a regex to apply to all names. Names matching this regex are
# marked as invalid.
UNCLASSIFIED_REGEX_COMPONENTS = [r'-like\b',
                                 r'\bactinomycete\b',
                                 r'\bcrenarchaeote\b',
                                 r'\bculture\b',
                                 r'\bchimeric\b',
                                 r'\bcyanobiont\b',
                                 r'degrading',
                                 r'\beuryarchaeote\b',
                                 r'disease',
                                 r'\b[cC]lone',
                                 r'\bmethanogen(ic)?\b',
                                 r'\bplanktonic\b',
                                 r'\bplanctomycete\b',
                                 r'\bsymbiote\b',
                                 r'\btransconjugant\b',
                                 # starts with lower-case char (except root)
                                 r'^(?!root$)[a-z]',
                                 r'^\W+\s+[a-zA-Z]*\d',  # Digit in second word
                                 r'\d\d',
                                 r'atypical',
                                 r'^cf\.',
                                 r'acidophile',
                                 r'\bactinobacterium\b',
                                 r'aerobic',
                                 r'.+\b[Al]g(um|a)\b',
                                 r'\b[Bb]acteri(um|al)\b',
                                 r'.+\b[Bb]acteria\b',
                                 r'Barophile',
                                 r'cyanobacterium',
                                 r'Chloroplast',
                                 r'Cloning',
                                 r'\bclone\b',
                                 r'cluster',
                                 r'^diazotroph',
                                 r'\bcoccus\b',
                                 r'archaeon',
                                 r'-containing',
                                 r'epibiont',
                                 # 'et al',
                                 r'environmental samples',
                                 r'eubacterium',
                                 # r'\b[Gg]roup\b',
                                 r'halophilic',
                                 r'hydrothermal\b',
                                 r'isolate',
                                 r'\bmarine\b',
                                 r'methanotroph',
                                 r'microorganism',
                                 r'mollicute',
                                 r'pathogen',
                                 r'[Pp]hytoplasma',
                                 r'proteobacterium',
                                 r'putative',
                                 r'\bsp\.',
                                 r'species',
                                 r'spirochete',
                                 r'str\.',
                                 r'strain',
                                 r'symbiont',
                                 r'\b[Tt]axon\b',
                                 r'unicellular',
                                 r'uncultured',
                                 r'unclassified',
                                 r'unidentified',
                                 r'unknown',
                                 r'vector\b',
                                 r'vent\b',
                                 ]

# provides criteria for defining matching tax_ids as "unclassified"
UNCLASSIFIED_REGEX = re.compile('|'.join(UNCLASSIFIED_REGEX_COMPONENTS))


def define_schema(Base):
    class Node(Base):
        __tablename__ = 'nodes'
        tax_id = Column(String, primary_key=True, nullable=False)

        # TODO: temporarily remove foreign key constratint on parent
        # TODO: (creates order depencence during insertion); may need to
        # TODO: add constraint after table has been populated.

        # parent_id = Column(String, ForeignKey('nodes.tax_id'))
        parent_id = Column(String, index=True)
        rank = Column(String, ForeignKey('ranks.rank'))
        embl_code = Column(String)
        division_id = Column(String)
        source_id = Column(Integer, ForeignKey('source.id'))
        is_valid = Column(Boolean, default=True)
        names = relationship('Name')
        ranks = relationship('Rank', back_populates='nodes')
        sources = relationship('Source', back_populates='nodes')

    class Name(Base):
        __tablename__ = 'names'
        id = Column(Integer, primary_key=True)
        tax_id = Column(String, ForeignKey('nodes.tax_id', ondelete='CASCADE'))
        node = relationship('Node', back_populates='names')
        tax_name = Column(String)
        unique_name = Column(String)
        name_class = Column(String)
        source_id = Column(Integer, ForeignKey('source.id'))
        is_primary = Column(Boolean)
        is_classified = Column(Boolean)
        sources = relationship('Source', back_populates='names')

    Index('ix_names_tax_id_is_primary', Name.tax_id, Name.is_primary)

    class Merge(Base):
        __tablename__ = 'merged'
        old_tax_id = Column(String, primary_key=True, index=True)
        new_tax_id = Column(String, ForeignKey(
            'nodes.tax_id', ondelete='CASCADE'))

    class Rank(Base):
        __tablename__ = 'ranks'
        rank = Column(String, primary_key=True)
        height = Column(Integer, unique=True, nullable=False)
        no_rank = Column(Boolean)
        nodes = relationship('Node')

    class Source(Base):
        __tablename__ = 'source'
        id = Column(Integer, primary_key=True)
        name = Column(String, unique=True)
        description = Column(String)
        nodes = relationship('Node')
        names = relationship('Name')


def db_connect(engine, schema=None, clobber=False):
    """
    Create a connection object to a database. Attempt to establish a
    schema. If there are existing tables, delete them if clobber is
    True and return otherwise. Returns a sqlalchemy engine object.
    """
    if schema is None:
        base = declarative_base()
    else:
        try:
            engine.execute(sqlalchemy.schema.CreateSchema(schema))
        except sqlalchemy.exc.ProgrammingError as err:
            logging.warn(err)
        base = declarative_base(metadata=MetaData(schema=schema))

    define_schema(base)

    if clobber:
        logging.info('Clobbering database tables')
        base.metadata.drop_all(bind=engine)

    logging.info('Creating database tables')
    base.metadata.create_all(bind=engine)

    return base


def read_merged(rows):

    yield ('old_tax_id', 'new_tax_id')
    for row in rows:
        yield tuple(row)


def read_nodes(rows, source_id=1):
    """
    Return an iterator of rows ready to insert into table "nodes".

    * rows - iterator of lists (eg, output from read_archive or read_dmp)
    """

    ncbi_keys = ['tax_id', 'parent_id', 'rank', 'embl_code', 'division_id']
    extra_keys = ['source_id', 'is_valid']
    is_valid = 1

    ncbi_cols = len(ncbi_keys)

    rank = ncbi_keys.index('rank')
    parent_id = ncbi_keys.index('parent_id')

    # assumes the first row is the root
    row = next(rows)
    row[rank] = 'root'
    # parent must be None for termination of recursive CTE for
    # calculating lineages
    row[parent_id] = None
    rows = itertools.chain([row], rows)

    yield ncbi_keys + extra_keys

    for row in rows:
        # replace whitespace in "rank" with underscore
        row[rank] = '_'.join(row[rank].split())
        # provide default values for source_id and is_valid
        yield row[:ncbi_cols] + [source_id, is_valid]


def read_names(rows, source_id=1):
    """Return an iterator of rows ready to insert into table
    "names". Adds columns "is_primary" (identifying the primary name
    for each tax_id with a vaule of 1) and "is_classified" (always None).

    * rows - iterator of lists (eg, output from read_archive or read_dmp)
    * unclassified_regex - a compiled re matching "unclassified" names

    """

    ncbi_keys = ['tax_id', 'tax_name', 'unique_name', 'name_class']
    extra_keys = ['source_id', 'is_primary', 'is_classified']

    # is_classified applies to species only; we will set this value
    # later
    is_classified = None

    name_class = ncbi_keys.index('name_class')
    tax_id = ncbi_keys.index('tax_id')

    yield ncbi_keys + extra_keys

    for tid, grp in itertools.groupby(rows, itemgetter(tax_id)):
        # confirm that each tax_id has exactly one scientific name
        num_primary = 0
        for r in grp:
            is_primary = int(r[name_class] == 'scientific name')
            num_primary += is_primary
            yield (r + [source_id, is_primary, is_classified])

        assert num_primary == 1


def load_sqlite(conn, table, rows, colnames=None, limit=None):
    cur = conn.cursor()

    colnames = colnames or next(rows)

    cmd = 'insert into {table} ({colnames}) values ({fstr})'.format(
        table=table,
        colnames=', '.join(colnames),
        fstr=', '.join(['?'] * len(colnames)))

    cur.executemany(cmd, itertools.islice(rows, limit))
    conn.commit()


def set_classified(conn, unclassified_regex):
    cur = conn.cursor()

    cmd = """
    select tax_id, tax_name
    from names
    join nodes using(tax_id)
    where is_primary
    and rank = 'species'
    """

    print cmd
    cur.execute(cmd)

    primary_species_names = cur.fetchall()

    print 'checking names'
    unclassified_taxids = [(tax_id,) for tax_id, tax_name in primary_species_names
                           if unclassified_regex.search(tax_name)]
    print len(unclassified_taxids)

    # insert tax_ids into a temporary table
    temptab = ''.join([random.choice(string.ascii_letters) for n in xrange(12)])
    cmd = 'CREATE TEMPORARY TABLE "{}" (old_tax_id text)'.format(temptab)
    cur.execute(cmd)

    print('inserting tax_ids into temporary table')

    # TODO: couldn't find an equivalent of "executemany" - does one exist?

    cmd = 'INSERT INTO "{temptab}" VALUES (?)'.format(temptab=temptab)
    cur.executemany(cmd, unclassified_taxids)

    cmd = """
    update names
    set is_classified = 0
    where tax_id in
    (select * from "{}")
    """.format(temptab)
    print cmd

    cur.execute(cmd)

    conn.commit()


def db_load(engine, archive, schema=None, ranks=RANKS):
    """Load data from zip archive into database identified by con.

    """

    conn = engine.raw_connection()
    db_engine = engine.driver  # 'pysqlite' or '?'

    if db_engine == 'pysqlite':
        db_loader = load_sqlite
    else:
        raise NotImplementedError('database driver {} is not supported'.format(db_engine))

    # source
    db_loader(
        conn, 'source',
        rows=[('ncbi', DATA_URL)],
        colnames=['name', 'description'],
    )

    source_id = conn.cursor().execute(
        "select id from source where name = 'ncbi'").fetchone()[0]

    # ranks
    log.info('loading ranks')
    # TODO: remove ranks.no_rank
    ranks_rows = [('rank', 'height', 'no_rank')]
    ranks_rows += [(rank, i, 0) for i, rank in enumerate(RANKS)]
    db_loader(conn, 'ranks', rows=iter(ranks_rows))

    # nodes
    logging.info('loading nodes')
    nodes_rows = read_nodes(read_archive(archive, 'nodes.dmp'), source_id=source_id)
    db_loader(conn, 'nodes', rows=nodes_rows)

    # names
    logging.info('loading names')
    names_rows = read_names(read_archive(archive, 'names.dmp'), source_id=source_id)
    db_loader(conn, 'names', rows=names_rows)

    # merged
    logging.info('loading merged')
    merged_rows = read_merged(read_archive(archive, 'merged.dmp'))
    db_loader(conn, 'merged', rows=merged_rows)


def fetch_data(dest_dir='.', clobber=False, url=DATA_URL):
    """
    Download data from NCBI required to generate local taxonomy
    database. Default url is ncbi.DATA_URL

    * dest_dir - directory in which to save output files (created if necessary).
    * clobber - don't download if False and target of url exists in dest_dir
    * url - url to archive; default is ncbi.DATA_URL

    Returns (fname, downloaded), where fname is the name of the
    downloaded zip archive, and downloaded is True if a new files was
    downloaded, false otherwise.

    see ftp://ftp.ncbi.nih.gov/pub/taxonomy/taxdump_readme.txt
    """

    dest_dir = os.path.abspath(dest_dir)
    try:
        os.mkdir(dest_dir)
    except OSError:
        pass

    fout = os.path.join(dest_dir, os.path.split(url)[-1])

    if os.access(fout, os.F_OK) and not clobber:
        downloaded = False
        logging.info(fout + ' exists; not downloading')
    else:
        downloaded = True
        logging.info('downloading {} to {}'.format(url, fout))
        urllib.urlretrieve(url, fout)

    return (fout, downloaded)


def read_archive(archive, fname):
    """
    Return an iterator of rows from a zip archive.

    * archive - path to the zip archive.
    * fname - name of the compressed file within the archive.
    """

    zfile = zipfile.ZipFile(archive, 'r')
    for line in zfile.read(fname).splitlines():
        yield line.rstrip('\t|\n').split('\t|\t')


def read_dmp(fname):
    for line in open(fname, 'rU'):
        yield line.rstrip('\t|\n').split('\t|\t')

