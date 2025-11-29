PYTHON ?= python

.PHONY: install
install:
	uv sync

.PHONY: start
start:
	uv run $(PYTHON) run.py
