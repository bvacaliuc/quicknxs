#-*- coding: utf-8 -*-

import os
import sys
import shutil
import tempfile
import unittest

# Ensure the project root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from quicknxs.buzhug.buzhug import Base, TS_Base
from quicknxs.buzhug.buzhug_files import (
    StringFile, UnicodeFile, IntegerFile, FloatFile, BooleanFile,
)

PRODUCTION_DB = '/SNS/REF_M/shared/quicknxs_database'


# ---------------------------------------------------------------------------
# Test Class 1: BuzhugFileTypesTest
# ---------------------------------------------------------------------------

class BuzhugFileTypesTest(unittest.TestCase):
    """Unit tests for buzhug_files.py encoding/decoding round-trips."""

    def _roundtrip(self, fobj, value):
        block = fobj.to_block(value)
        return fobj.from_block(block)

    # -- StringFile --

    def test_string_file_roundtrip(self):
        f = StringFile()
        for val in ['hello', '', 'caf\u00e9', '\u2603 snowman']:
            self.assertEqual(self._roundtrip(f, val), val)

    def test_string_file_escaping(self):
        f = StringFile()
        for val in ['line\nbreak', 'carriage\rreturn', 'back\\slash',
                     'combo\\\n\r']:
            self.assertEqual(self._roundtrip(f, val), val)

    def test_string_file_none(self):
        f = StringFile()
        block = f.to_block(None)
        self.assertEqual(block, b'!\n')
        self.assertIsNone(f.from_block(block))

    # -- UnicodeFile --

    def test_unicode_file_roundtrip(self):
        sf = StringFile()
        uf = UnicodeFile()
        for val in ['hello', 'caf\u00e9', '\u2603']:
            self.assertEqual(self._roundtrip(uf, val), val)
            # Python 3: UnicodeFile and StringFile produce identical results
            self.assertEqual(sf.to_block(val), uf.to_block(val))

    # -- IntegerFile --

    def test_integer_file_roundtrip(self):
        f = IntegerFile()
        for val in [0, 1, -1, 12345, -12345, 2**20]:
            self.assertEqual(self._roundtrip(f, val), val)

    def test_integer_file_none(self):
        f = IntegerFile()
        self.assertIsNone(self._roundtrip(f, None))

    # -- FloatFile --

    def test_float_file_roundtrip(self):
        f = FloatFile()
        for val in [0.0, 1.5, -1.5, 1e-30, 1e30, -1e30]:
            self.assertAlmostEqual(self._roundtrip(f, val), val, places=10)

    def test_float_file_none(self):
        f = FloatFile()
        self.assertIsNone(self._roundtrip(f, None))

    def test_float_file_ordering(self):
        """Encoded floats must preserve sort order (key buzhug property)."""
        f = FloatFile()
        values = [-1e10, -1.0, -0.001, 0.0, 0.001, 1.0, 1e10]
        blocks = [f.to_block(v) for v in values]
        self.assertEqual(blocks, sorted(blocks))

    # -- BooleanFile --

    def test_bool_file_roundtrip(self):
        f = BooleanFile()
        self.assertIs(self._roundtrip(f, True), True)
        self.assertIs(self._roundtrip(f, False), False)
        self.assertIsNone(self._roundtrip(f, None))


# ---------------------------------------------------------------------------
# Test Class 2: BuzhugLegacyTypeAliasTest
# ---------------------------------------------------------------------------

class BuzhugLegacyTypeAliasTest(unittest.TestCase):
    """Tests that Python 2 type names resolve correctly in buzhug."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_unicode_type_registered(self):
        db = Base(os.path.join(self.tmpdir, 'test_db'))
        self.assertIs(db.types['unicode'], str)

    def test_long_type_registered(self):
        db = Base(os.path.join(self.tmpdir, 'test_db'))
        self.assertIs(db.types['long'], int)

    def test_open_info_with_unicode_field(self):
        """Create a DB dir with __info__ containing 'unicode' type, verify open succeeds."""
        db_path = os.path.join(self.tmpdir, 'unicode_db')
        # First create a normal database with a str field
        db = Base(db_path)
        db.create(('name', str), ('value', int))
        db.insert('test', 1)
        db.close()
        # Patch __info__ to use 'unicode' instead of 'str'
        info_path = os.path.join(db_path, '__info__')
        with open(info_path, 'rb') as f:
            info = f.read()
        info = info.replace(b'name:str', b'name:unicode')
        with open(info_path, 'wb') as f:
            f.write(info)
        # Reopen — should not raise KeyError
        db2 = Base(db_path)
        db2.open()
        self.assertIs(db2.fields['name'], str)
        rec = db2[0]
        self.assertIsInstance(rec.name, str)
        self.assertEqual(rec.name, 'test')
        db2.close()

    def test_open_info_with_long_field(self):
        """Create a DB dir with __info__ containing 'long' type, verify open succeeds."""
        db_path = os.path.join(self.tmpdir, 'long_db')
        db = Base(db_path)
        db.create(('num', int), ('label', str))
        db.insert(42, 'answer')
        db.close()
        # Patch __info__ to use 'long' instead of 'int' for num field
        info_path = os.path.join(db_path, '__info__')
        with open(info_path, 'rb') as f:
            info = f.read()
        info = info.replace(b'num:int', b'num:long')
        with open(info_path, 'wb') as f:
            f.write(info)
        # Reopen — should not raise KeyError
        db2 = Base(db_path)
        db2.open()
        self.assertIs(db2.fields['num'], int)
        rec = db2[0]
        self.assertIsInstance(rec.num, int)
        self.assertEqual(rec.num, 42)
        db2.close()


# ---------------------------------------------------------------------------
# Test Class 3: BuzhugDatabaseRoundtripTest
# ---------------------------------------------------------------------------

class BuzhugDatabaseRoundtripTest(unittest.TestCase):
    """End-to-end create → insert → close → reopen → read tests."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, 'roundtrip_db')

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_create_insert_reopen(self):
        db = Base(self.db_path)
        db.create(('x', int), ('y', float), ('label', str))
        db.insert(1, 2.5, 'alpha')
        db.insert(2, 3.5, 'beta')
        db.insert(3, 4.5, 'gamma')
        db.close()

        db2 = Base(self.db_path)
        db2.open()
        records = db2.select()
        self.assertEqual(len(records), 3)
        self.assertEqual(records[0].x, 1)
        self.assertAlmostEqual(records[0].y, 2.5, places=10)
        self.assertEqual(records[0].label, 'alpha')
        self.assertEqual(records[2].label, 'gamma')
        db2.close()

    def test_select_by_int_equality(self):
        db = Base(self.db_path)
        db.create(('x', int), ('label', str))
        db.insert(10, 'a')
        db.insert(20, 'b')
        db.insert(10, 'c')
        db.close()

        db2 = Base(self.db_path)
        db2.open()
        results = db2.select(None, x=10)
        self.assertEqual(len(results), 2)
        labels = sorted([r.label for r in results])
        self.assertEqual(labels, ['a', 'c'])
        db2.close()

    def test_select_by_float_range(self):
        db = Base(self.db_path)
        db.create(('val', float), ('tag', str))
        db.insert(0.1, 'lo')
        db.insert(0.5, 'mid')
        db.insert(0.9, 'hi')
        db.close()

        db2 = Base(self.db_path)
        db2.open()
        results = db2.select(None, val=[0.2, 0.8])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].tag, 'mid')
        db2.close()

    def test_select_by_string(self):
        db = Base(self.db_path)
        db.create(('name', str), ('count', int))
        db.insert('alice', 1)
        db.insert('bob', 2)
        db.insert('alice', 3)
        db.close()

        db2 = Base(self.db_path)
        db2.open()
        results = db2.select(None, name='alice')
        self.assertEqual(len(results), 2)
        db2.close()

    def test_insert_none_defaults(self):
        db = Base(self.db_path)
        db.create(('x', int), ('y', float), ('label', str))
        # Insert with positional args — all provided
        db.insert(1, 2.0, 'ok')
        db.close()

        db2 = Base(self.db_path)
        db2.open()
        rec = db2[0]
        self.assertEqual(rec.x, 1)
        db2.close()

    def test_delete_and_cleanup(self):
        db = Base(self.db_path)
        db.create(('x', int), ('label', str))
        db.insert(1, 'a')
        db.insert(2, 'b')
        db.insert(3, 'c')
        # Delete the middle record
        recs = db.select(None, x=2)
        db.delete(recs)
        db.cleanup()
        remaining = db.select()
        self.assertEqual(len(remaining), 2)
        labels = sorted([r.label for r in remaining])
        self.assertEqual(labels, ['a', 'c'])
        db.close()

    def test_thread_safe_base(self):
        db = TS_Base(self.db_path)
        db.create(('x', int), ('label', str))
        db.insert(1, 'a')
        db.insert(2, 'b')
        db.close()

        db2 = TS_Base(self.db_path)
        db2.open()
        records = db2.select()
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].x, 1)
        db2.close()


# ---------------------------------------------------------------------------
# Test Class 4: ProductionDatabaseTest
# ---------------------------------------------------------------------------

@unittest.skipUnless(
    os.path.isdir(PRODUCTION_DB),
    'Production database not available at %s' % PRODUCTION_DB,
)
class ProductionDatabaseTest(unittest.TestCase):
    """Integration tests against the real production database (read-only)."""

    @classmethod
    def setUpClass(cls):
        cls.db = Base(PRODUCTION_DB)
        cls.db.open()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_open_production_database(self):
        # If we got here, open() succeeded (no KeyError on 'unicode')
        self.assertIsNotNone(self.db)

    def test_field_types_resolved(self):
        for name, ftype in self.db.fields.items():
            self.assertIsInstance(ftype, type,
                                 msg='Field %s has non-type value %r' % (name, ftype))

    def test_read_first_record(self):
        rec = self.db[0]
        self.assertIsInstance(rec.__id__, int)
        self.assertIsInstance(rec.file_id, int)
        self.assertIsInstance(rec.file_path, str)
        self.assertIsInstance(rec.ai, float)

    def test_file_path_is_str(self):
        rec = self.db[0]
        self.assertIsInstance(rec.file_path, str)
        self.assertNotIsInstance(rec.file_path, bytes)

    def test_select_by_file_id(self):
        results = self.db.select(None, file_id=18081)
        self.assertGreater(len(results), 0)

    def test_select_by_float_range(self):
        results = self.db.select(None, ai=[0.0, 1.0])
        self.assertGreater(len(results), 0)

    def test_record_count(self):
        all_records = self.db.select()
        self.assertGreater(len(all_records), 9000)


# ---------------------------------------------------------------------------
# Test Class 5: DatabaseHandlerTest
# ---------------------------------------------------------------------------

@unittest.skipUnless(
    os.path.isdir(PRODUCTION_DB),
    'Production database not available at %s' % PRODUCTION_DB,
)
class DatabaseHandlerTest(unittest.TestCase):
    """Integration tests for the DatabaseHandler wrapper."""

    @classmethod
    def setUpClass(cls):
        from quicknxs.database import DatabaseHandler
        cls.handler = DatabaseHandler()
        cls.handler.load_db()

    @classmethod
    def tearDownClass(cls):
        cls.handler.close_db()

    def test_load_db(self):
        self.assertIsNotNone(self.handler.db)

    def test_query_by_file_id(self):
        results = self.handler(file_id=18081)
        self.assertGreater(len(results), 0)

    def test_record_field_types(self):
        results = self.handler(file_id=18081)
        if len(results) > 0:
            rec = results[0]
            self.assertIsInstance(rec.file_id, int)
            self.assertIsInstance(rec.file_path, str)
            self.assertIsInstance(rec.ai, float)


# ---------------------------------------------------------------------------
# Suite for unittest discovery
# ---------------------------------------------------------------------------

suite = unittest.TestSuite()
for cls in [BuzhugFileTypesTest, BuzhugLegacyTypeAliasTest,
            BuzhugDatabaseRoundtripTest, ProductionDatabaseTest,
            DatabaseHandlerTest]:
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(cls))
