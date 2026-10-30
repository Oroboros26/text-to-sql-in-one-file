.PHONY: run test lint
run:
	python agent.py

test:
	python -m pytest -q

lint:
	ruff check .
