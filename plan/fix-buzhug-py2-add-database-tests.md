# Plan: Fix buzhug Py2 type aliases & add comprehensive database tests

## Context

The quicknxsv1 application was migrated from Python 2 to Python 3 on the `feature/pixi_py3_qt5` branch. The production database at `/SNS/REF_M/shared/quicknxs_database/` was created by Python 2 and its `__info__` file contains `file_path:unicode`. When the Python 3 code tries to open this database, `buzhug.Base._open()` fails with `KeyError: 'unicode'` because `self.types` only maps Python 3 type names (`'str'`, `'int'`, `'float'`, etc.). No database tests exist in the project.

## Part 1: Bug Fix — Python 2 type aliases in buzhug

### File: `quicknxs/buzhug/buzhug.py`

**Change:** In `Base.__init__()` (after line 322 where `types_map` is registered), add aliases for Python 2 type names that may appear in legacy `__info__` files:

```python
# After the types_map registration loop (line 321-322):
# Python 2 compatibility: alias legacy type names to Python 3 equivalents
self.types['unicode'] = str       # Python 2 unicode → Python 3 str
self.types['long'] = int          # Python 2 long → Python 3 int
```

This maps the string `'unicode'` to the `str` class and `'long'` to `int`, so when `_open()` reads `file_path:unicode` from `__info__`, `self.types['unicode']` resolves to `str` and picks up `StringFile` from `file_types`.

No changes needed to `buzhug_files.py` — `UnicodeFile` already subclasses `StringFile` and is functionally identical in Python 3.

## Part 2: Comprehensive test suite

### New file: `tests/database_test.py`

Follow existing project conventions: unittest classes, `suite` variable at bottom, pytest-compatible naming (`*_test.py`).

### Test Class 1: `BuzhugFileTypesTest`
Unit tests for `buzhug_files.py` encoding/decoding round-trips.

| Test | What it verifies |
|------|-----------------|
| `test_string_file_roundtrip` | `StringFile.to_block()` → `from_block()` for normal strings, unicode, empty string |
| `test_string_file_escaping` | Strings with `\n`, `\r`, `\\` survive round-trip |
| `test_string_file_none` | `None` encodes to `b'!\n'` and decodes back to `None` |
| `test_unicode_file_roundtrip` | `UnicodeFile` round-trips identically to `StringFile` in Python 3 |
| `test_integer_file_roundtrip` | `IntegerFile` encodes/decodes 0, positive, negative, large values |
| `test_float_file_roundtrip` | `FloatFile` encodes/decodes 0.0, positive, negative, very small/large |
| `test_float_file_ordering` | Encoded floats preserve sort order (key property of buzhug's float encoding) |
| `test_bool_file_roundtrip` | `BooleanFile` encodes/decodes True, False, None |

### Test Class 2: `BuzhugLegacyTypeAliasTest`
Tests that Python 2 type names resolve correctly.

| Test | What it verifies |
|------|-----------------|
| `test_unicode_type_registered` | `Base.types['unicode']` is `str` |
| `test_long_type_registered` | `Base.types['long']` is `int` |
| `test_open_info_with_unicode_field` | Create a temp DB dir with `__info__` containing `unicode` type, verify `Base.open()` succeeds and field resolves to `str` |
| `test_open_info_with_long_field` | Same but with `long` type, verify field resolves to `int` |

### Test Class 3: `BuzhugDatabaseRoundtripTest`
End-to-end create → insert → close → reopen → read tests.

| Test | What it verifies |
|------|-----------------|
| `test_create_insert_reopen` | Create DB with (int, float, str) fields, insert records, close, reopen, verify all values |
| `test_select_by_int_equality` | Query by integer field returns correct records |
| `test_select_by_float_range` | Query by float range `[lo, hi]` returns correct records |
| `test_select_by_string` | Query by string field returns correct records |
| `test_insert_none_defaults` | Insert with missing fields, verify defaults are `None` |
| `test_delete_and_cleanup` | Insert, delete, cleanup, verify deleted records gone |
| `test_thread_safe_base` | Same operations via `TS_Base` wrapper |

### Test Class 4: `ProductionDatabaseTest`
Integration tests against the real production database (read-only). Skipped if database path doesn't exist.

| Test | What it verifies |
|------|-----------------|
| `test_open_production_database` | `Base(path).open()` succeeds without `KeyError` |
| `test_field_types_resolved` | All fields in `db.fields` map to valid Python 3 types |
| `test_read_first_record` | First record has correct field types (int, float, str) |
| `test_file_path_is_str` | `file_path` field returns Python 3 `str`, not `bytes` |
| `test_select_by_file_id` | `db(file_id=18081)` returns records |
| `test_select_by_float_range` | `db.select(None, ai=[0.0, 1.0])` returns records |
| `test_record_count` | `len(db())` returns expected ~9752 records |

### Test Class 5: `DatabaseHandlerTest`
Integration tests for the `DatabaseHandler` wrapper. Skipped if production database path doesn't exist.

| Test | What it verifies |
|------|-----------------|
| `test_load_db` | `DatabaseHandler.load_db()` succeeds |
| `test_query_by_file_id` | `handler(file_id=18081)` returns results |
| `test_record_field_types` | Returned records have correct Python 3 types |

### Configuration changes

**File: `pyproject.toml`** — Add a `test-db` task:
```
test-db = { cmd = "pytest tests/database_test.py -v", description = "Run database tests" }
```

**File: `Makefile`** — Add a `test-db` target:
```
test-db: install
	pixi run test-db
```

## Implementation order

1. Fix `buzhug.py` — add type aliases (2 lines)
2. Create `tests/database_test.py` with all 5 test classes
3. Add `test-db` task to `pyproject.toml` and `Makefile`
4. Run `make test` to verify all existing + new tests pass
5. Commit with descriptive message

## Verification

```bash
make test-db    # Run just the new database tests
make test       # Run the full suite (55 existing + ~25 new tests)
```
