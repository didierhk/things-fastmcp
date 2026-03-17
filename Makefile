.PHONY: setup run test lint freeze clean preflight

VENV   := .venv
PYTHON := $(VENV)/bin/python3
PIP    := $(VENV)/bin/pip

setup:
	python3 -m venv $(VENV)
	$(PIP) install -e ".[dev]"
	$(PIP) install pytest
	@echo "Setup complete. Run 'make run' to start server."

run: preflight
	$(PYTHON) things_fast_server.py

preflight:
	$(PYTHON) -c "from src.things_mcp.preflight import check; check()"

test:
	$(PYTHON) -m pytest tests/ -v

lint:
	$(VENV)/bin/ruff check .

freeze:
	$(PIP) freeze | grep -v "^-e " > requirements.txt
	@echo "requirements.txt updated"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf dist build *.egg-info
