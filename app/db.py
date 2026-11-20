"""Fail-closed SQLite read-only execution with preflight and a watchdog.

The LLM is *never* given a database connection. Generated SQL is screened
before preparation; SQLite's independent read-only connection + authorizer
provide the second layer of enforcement.
"""
from __future__ import annotations
import re
import sqlite3
import time
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / 'data' / 'football.db'
MAX_SQL = 12000
ROW_LIMIT = 100
TIME_LIMIT = 2.5

FORBIDDEN = frozenset('''insert update delete drop alter create attach detach pragma
vacuum replace reindex analyze begin commit rollback savepoint release trigger
returning load_extension readfile writefile'''.split())
ALLOWED_FUNCS = frozenset('''count sum avg min max abs round coalesce ifnull nullif
lower upper trim ltrim rtrim substr substring length instr replace printf
strftime date datetime time julianday unixepoch total group_concat
row_number rank dense_rank lag lead first_value last_value nth_value
json_extract json_array_length like glob iif if ceil floor mod sign
'''.split())

class RejectedSQL(ValueError):
    pass


def scrub_noncode(sql: str) -> str:
    """Replace quoted string/identifier/comment contents with spaces, retaining punctuation elsewhere.

    Semicolons and dangerous verbs inside a literal are not executable syntax.
    Reject incomplete quotes and block comments instead of guessing.
    """
    chunks = []
    i, n = 0, len(sql)
    while i < n:
        c = sql[i]
        if sql.startswith('--', i):
            end = sql.find('\n', i+2)
            if end < 0: end = n
            chunks.append(' ' * (end-i))
            i = end
        elif sql.startswith('/*', i):
            end = sql.find('*/', i+2)
            if end < 0: raise RejectedSQL('Unclosed SQL block comment')
            chunks.append(' ' * (end+2-i)); i = end+2
        elif c in ("'", '"', '`', '['):
            closer = ']' if c == '[' else c
            j = i+1
            while j < n:
                if sql[j] == closer:
                    if closer != ']' and j+1 < n and sql[j+1] == closer:
                        j += 2; continue
                    break
                j += 1
            if j == n: raise RejectedSQL('Unclosed SQL string or identifier')
            chunks.append(' ' * (j+1-i)); i = j+1
        else:
            chunks.append(c); i += 1
    return ''.join(chunks)


def validate_sql(sql: str) -> str:
    if not isinstance(sql, str) or not sql.strip():
        raise RejectedSQL('No SQL was generated')
    if len(sql) > MAX_SQL:
        raise RejectedSQL('SQL exceeds length limit')
    sql = sql.strip()
    # A single optional trailing semicolon is fine. No second statement.
    clean = scrub_noncode(sql)
    semi = [m.start() for m in re.finditer(';', clean)]
    if len(semi) > 1 or (semi and clean[semi[0]+1:].strip()):
        raise RejectedSQL('Only one statement is permitted')
    words = [m.group().lower() for m in re.finditer(r'[A-Za-z_][A-Za-z_0-9]*', clean)]
    if not words or words[0] not in ('select', 'with'):
        raise RejectedSQL('Only SELECT or WITH ... SELECT is allowed')
    banned = FORBIDDEN.intersection(words)
    if banned:
        raise RejectedSQL('Disallowed SQL operation: ' + sorted(banned)[0].upper())
    if words[0] == 'with' and 'select' not in words:
        raise RejectedSQL('WITH must end in a SELECT')
    # SQLite read-only is also enforced by a separate authorizer and the database URI.
    return sql


def ro_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    uri = 'file:' + quote(str(db_path.resolve()), safe='/') + '?mode=ro&immutable=1'
    connection = sqlite3.connect(uri, uri=True, timeout=1, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.enable_load_extension(False)
    return connection


def allowed_relations(db_path: Path = DB_PATH) -> set[str]:
    con = ro_connection(db_path)
    try:
        return {r[0].lower() for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'"
        )}
    finally:
        con.close()


def execute_readonly(sql: str, db_path: Path = DB_PATH, row_limit: int = ROW_LIMIT,
                     time_limit: float = TIME_LIMIT) -> dict:
    checked = validate_sql(sql)  # BEFORE any SQL is prepared against the database.
    if row_limit < 1 or row_limit > ROW_LIMIT: raise RejectedSQL('Invalid row limit')
    if not 0 < time_limit <= 5: raise RejectedSQL('Invalid time limit')
    known = allowed_relations(db_path)
    began = time.monotonic()
    reads: set[tuple[str,str]] = set()
    tables: set[str] = set()
    con = ro_connection(db_path)
    def authorization(action, arg1, arg2, dbname, origin):
        if action == sqlite3.SQLITE_READ:
            table = (arg1 or '').lower()
            if table.startswith('sqlite_') or table not in known: return sqlite3.SQLITE_DENY
            tables.add(arg1)
            if arg2: reads.add((arg1,arg2))
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION:
            # sqlite3 callback: function name is arg2.
            if (arg2 or '').lower() not in ALLOWED_FUNCS:
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE):
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY
    def progress():
        return 1 if time.monotonic()-began > time_limit else 0
    try:
        con.set_authorizer(authorization)
        con.set_progress_handler(progress,1000)
        try:
            explain = con.execute('EXPLAIN QUERY PLAN ' + checked).fetchall()
        except sqlite3.Error as e:
            raise RejectedSQL('Dry-run failed: ' + str(e)) from e
        # A factual answer must actually depend on at least one known DB relation;
        # SELECT 'invented fact' without FROM would manufacture rows, not retrieve them.
        if not tables:
            raise RejectedSQL('Query does not read a recognized database relation')
        if time.monotonic()-began > time_limit:
            raise RejectedSQL('Dry-run exceeded the time limit')
        try:
            cursor = con.execute(checked)
            columns = [col[0] for col in (cursor.description or [])]
            fetched = cursor.fetchmany(row_limit+1)
        except sqlite3.Error as e:
            raise RejectedSQL('Execution failed or exceeded safety limit: ' + str(e)) from e
        elapsed = round((time.monotonic()-began)*1000)
        return {
            'columns':columns,
            'rows':[[v for v in row] for row in fetched[:row_limit]],
            'row_count':min(len(fetched),row_limit),
            'truncated':len(fetched)>row_limit,
            'tables':sorted(tables),
            'fields':sorted(f'{table}.{col}' for table,col in reads),
            'dry_run':'ok',
            'dry_run_plan':[r[3] for r in explain][:12],
            'validation':'passed',
            'execution_ms':elapsed,
        }
    finally:
        con.close()
