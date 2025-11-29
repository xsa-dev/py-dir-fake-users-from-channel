PYTHON ?= python

.PHONY: install
install:
	uv sync

.PHONY: start
start:
	uv run $(PYTHON) run.py

.PHONY: test
test:
	uv run $(PYTHON) -m unittest discover -s test
