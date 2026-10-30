"""Text-to-SQL in one file: an LLM tool loop that answers questions with validated, read-only SQL.
Knowledge lives in semantic.yaml (tables, metrics, rules, example queries). This file reads it, checks every query, runs it, loops.
Run: python agent.py "Which country has the highest revenue?"   (no argument starts a prompt loop)"""
import contextlib
import json
import os
import sqlite3
import sys
from pathlib import Path

import sqlglot
import yaml
from openai import OpenAI
from sqlglot import expressions as exp

HERE = Path(__file__).resolve().parent
DB = HERE / "shop.db"
SEMANTIC = yaml.safe_load((HERE / "semantic.yaml").read_text(encoding="utf-8"))
TABLES = {t["name"] for t in SEMANTIC["tables"]}
MODEL = os.getenv("MODEL", "gpt-4o-mini")
MAX_ROWS, SHOW_ROWS, MAX_STEPS = 200, 20, 5
TOOLS = [{"type": "function", "function": {
    "name": "run_sql", "description": "Run one read-only SQLite SELECT. Returns the row count and the first rows.",
    "parameters": {"type": "object", "properties": {"sql": {"type": "string"}}, "required": ["sql"]}}}]


def context() -> str:
    """The semantic file as plain text for the system prompt."""
    s, parts = SEMANTIC, [SEMANTIC["description"]]
    for t in s["tables"]:
        cols = "\n".join(f"  - {c['name']} ({c['type']}): {c['description']}" for c in t["columns"])
        parts.append(f"TABLE {t['name']}: {t['description']}\n{cols}")
    parts.append("JOINS:\n" + "\n".join(f"  - {j}" for j in s["joins"]))
    parts.append("METRICS (paste the expression inline):\n" + "\n".join(f"  - {m['name']}: {m['expr']}  -- {m['description']}" for m in s["metrics"]))
    parts.append("RULES:\n" + "\n".join(f"  - {r}" for r in s["rules"]))
    parts.append("EXAMPLES:\n" + "\n\n".join(f"Q: {q['question']}\nSQL: {q['sql']}" for q in s["examples"]))
    return "\n\n".join(parts)


def validate(sql: str) -> str:
    """The safety gate: one SELECT, known tables only, row limit added. Returns the SQL to run or raises ValueError."""
    try:
        trees = sqlglot.parse(sql.strip().rstrip(";"), read="sqlite")
    except sqlglot.errors.SqlglotError as e:
        raise ValueError(f"could not parse: {str(e)[:120]}") from e
    tree = trees[0] if len(trees) == 1 else None
    if not isinstance(tree, (exp.Select, exp.SetOperation)):
        raise ValueError("only a single SELECT statement is allowed")  # noqa: TRY004
    ctes = {c.alias_or_name for c in tree.find_all(exp.CTE)}
    for t in tree.find_all(exp.Table):
        if t.name not in TABLES and t.name not in ctes:
            raise ValueError(f"table {t.name!r} is not available")
    limit = tree.args.get("limit")
    if limit is None or not limit.expression.name.isdigit() or int(limit.expression.name) > MAX_ROWS:
        tree = tree.limit(MAX_ROWS, copy=False)
    return tree.sql(dialect="sqlite")


def run_sql(sql: str) -> str:
    """Validate, run on a read-only connection, return the text the model sees. Errors go back to the model so it can retry."""
    try:
        checked = validate(sql)
        with contextlib.closing(sqlite3.connect(f"file:{DB}?mode=ro", uri=True)) as con:
            cur = con.execute(checked)
            cols, rows = [d[0] for d in cur.description], cur.fetchall()
    except (ValueError, sqlite3.Error) as e:
        return f"SQL ERROR: {e}"
    print(f"  sql> {checked}")
    shown = "\n".join(" | ".join(map(str, r)) for r in rows[:SHOW_ROWS])
    return f"{len(rows)} rows (first {SHOW_ROWS} shown). Columns: {' | '.join(cols)}\n{shown}"


def ask(question: str) -> str:
    """The loop: model -> run_sql -> model ... -> plain-English answer."""
    client = OpenAI()   # reads OPENAI_API_KEY, and OPENAI_BASE_URL for any OpenAI-compatible provider
    system = "You answer analytics questions about a shop with SQL. Call run_sql, then answer in plain English using only numbers from the results.\n\n" + context()
    messages = [{"role": "system", "content": system}, {"role": "user", "content": question}]
    for _ in range(MAX_STEPS):
        msg = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS).choices[0].message
        if not msg.tool_calls:
            return msg.content or ""
        messages.append(msg.model_dump(exclude_none=True))
        for call in msg.tool_calls:
            result = run_sql(json.loads(call.function.arguments or "{}").get("sql", ""))
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
    return "Stopped: too many steps without an answer. Try a more specific question."


if __name__ == "__main__":
    if not DB.exists():
        import seed
        seed.build(DB)
    if len(sys.argv) > 1:
        print(ask(" ".join(sys.argv[1:])))
    else:
        while (q := input("question> ").strip()):
            print(ask(q))
