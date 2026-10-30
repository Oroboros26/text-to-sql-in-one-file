import pytest

from agent import SEMANTIC, validate


@pytest.mark.parametrize("q", SEMANTIC["examples"], ids=lambda q: q["question"])
def test_example_queries_pass(q):
    assert validate(q["sql"]).upper().startswith("SELECT")


@pytest.mark.parametrize("sql", [
    "DROP TABLE orders",
    "DELETE FROM orders",
    "SELECT 1 FROM orders; DROP TABLE orders",
    "SELECT * FROM sqlite_master",
    "WITH x AS (SELECT 1) DELETE FROM orders",
])
def test_unsafe_sql_is_refused(sql):
    with pytest.raises(ValueError):
        validate(sql)


def test_limit_is_added_and_capped():
    assert "LIMIT 200" in validate("SELECT * FROM orders")
    assert "LIMIT 200" in validate("SELECT * FROM orders LIMIT 100000")
    assert "LIMIT 5" in validate("SELECT * FROM orders LIMIT 5")
