# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import unicode_literals
import re

from sqlalchemy.engine import reflection
from sqlalchemy.engine.default import DefaultDialect
from sqlalchemy.sql.compiler import IdentifierPreparer, SQLCompiler
from sqlalchemy.sql.sqltypes import (BIGINT, BINARY, BOOLEAN, DATE, DECIMAL, FLOAT,
                                     INTEGER, NULLTYPE, STRINGTYPE, TIMESTAMP)

import pyathenajdbc


class UniversalSet(object):
    """UniversalSet

    https://github.com/dropbox/PyHive/blob/master/pyhive/common.py"""
    def __contains__(self, item):
        return True


class AthenaIdentifierPreparer(IdentifierPreparer):
    """PrestoIdentifierPreparer

    https://github.com/dropbox/PyHive/blob/master/pyhive/sqlalchemy_presto.py"""
    reserved_words = UniversalSet()


class AthenaCompiler(SQLCompiler):
    """PrestoCompiler

    https://github.com/dropbox/PyHive/blob/master/pyhive/sqlalchemy_presto.py"""
    def visit_char_length_func(self, fn, **kw):
        return 'length{0}'.format(self.function_argspec(fn, **kw))


_TYPE_MAPPINGS = {
    'DOUBLE': FLOAT,
    'SMALLINT': INTEGER,
    'BOOLEAN': BOOLEAN,
    'INTEGER': INTEGER,
    'VARCHAR': STRINGTYPE,
    'TINYINT': INTEGER,
    'DECIMAL': DECIMAL,
    'ARRAY': STRINGTYPE,
    'ROW': STRINGTYPE,  # StructType
    'VARBINARY': BINARY,
    'MAP': STRINGTYPE,
    'BIGINT': BIGINT,
    'DATE': DATE,
    'TIMESTAMP': TIMESTAMP,
    'STRING': STRINGTYPE
}


class AthenaDialect(DefaultDialect):

    name = 'awsathena'
    driver = 'jdbc'
    preparer = AthenaIdentifierPreparer
    statement_compiler = AthenaCompiler
    default_paramstyle = pyathenajdbc.paramstyle
    supports_alter = False
    supports_pk_autoincrement = False
    supports_default_values = False
    supports_empty_insert = False
    supports_unicode_statements = True
    supports_unicode_binds = True
    returns_unicode_strings = True
    description_encoding = None
    supports_native_boolean = True

    @classmethod
    def dbapi(cls):
        return pyathenajdbc

    def _get_default_schema_name(self, connection):
        return connection.connection.schema_name

    def create_connect_args(self, url):
        # Connection string format:
        #   awsathena+jdbc://
        #   {access_key}:{secret_key}@athena.{region_name}.amazonaws.com:443/
        #   {schema_name}?s3_staging_dir={s3_staging_dir}&driver_path={driver_path}&...
        opts = {
            'access_key': url.username,
            'secret_key': url.password,
            'region_name': re.sub(r'^athena\.([a-z0-9-]+)\.amazonaws\.com$', r'\1', url.host),
            'schema_name': url.database if url.database else 'default'
        }
        opts.update(url.query)
        return [[], opts]

    @reflection.cache
    def get_schema_names(self, connection, **kw):
        query = """
                SELECT schema_name
                FROM information_schema.schemata
                WHERE schema_name NOT IN ('information_schema')
                """
        return [row.schema_name for row in connection.execute(query).fetchall()]

    @reflection.cache
    def get_table_names(self, connection, schema=None, **kw):
        schema = schema if schema else connection.connection.schema_name
        query = """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = '{0}'
                """.format(schema)
        return [row.table_name for row in connection.execute(query).fetchall()]

    def has_table(self, connection, table_name, schema=None):
        table_names = self.get_table_names(connection, schema)
        if table_name in table_names:
            return True
        return False

    @reflection.cache
    def get_columns(self, connection, table_name, schema=None, **kw):
        # information_schema.columns fails when filtering with table_schema or table_name,
        # if specifying a name that does not exist in table_schema or table_name.
        schema = schema if schema else connection.connection.schema_name
        query = 'SHOW CREATE TABLE {}.{}'.format(schema, table_name)

        res = connection.execute(query).fetchall()
        columns = []
        ordinal = 0
        for r in res:
            row = r[0].upper().strip()
            row_comment = None
            if row.endswith(',') or row.endswith(')'):
                row = row[:-1]

            if 'COMMENT' in row:
                row_split = row.split('COMMENT')
                row_comment = row_split[-1]
                row = row_split[0]

            m = re.search(r'\`(.+)\`\s+(.+)\s*', row)
            if not m:
                continue

            column_name = m.group(1).lower()
            print(m.group(2))
            column_type = _TYPE_MAPPINGS.get(m.group(2), NULLTYPE)
            ordinal += 1
            columns.append(dict(
                name=column_name.lower(),
                type=column_type,
                ordinal_position=ordinal,
                comment=row_comment,
                nullable=None,
                default=None))

        return columns


    def get_foreign_keys(self, connection, table_name, schema=None, **kw):
        # Athena has no support for foreign keys.
        return []

    def get_pk_constraint(self, connection, table_name, schema=None, **kw):
        # Athena has no support for primary keys.
        return []

    def get_indexes(self, connection, table_name, schema=None, **kw):
        # Athena has no support for indexes.
        return []

    def do_rollback(self, dbapi_connection):
        # No transactions for Athena
        pass

    def _check_unicode_returns(self, connection, additional_tests=None):
        # Requests gives back Unicode strings
        return True

    def _check_unicode_description(self, connection):
        # Requests gives back Unicode strings
        return True
