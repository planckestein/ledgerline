PYTHON ?= python

.PHONY: install lint format test test-postgres coverage run

install:
	$(PYTHON) -m pip install -r requirements-dev.txt

lint:
	$(PYTHON) -m flake8 ledgerline tests *.py
	$(PYTHON) -m black --check ledgerline tests *.py
	$(PYTHON) -m isort --check-only ledgerline tests *.py

format:
	$(PYTHON) -m isort ledgerline tests *.py
	$(PYTHON) -m black ledgerline tests *.py

test:
	$(PYTHON) -m pytest tests

test-postgres:
	TEST_DATABASE_URL=postgresql://ledgerline:ledgerline@localhost:5432/ledgerline_test $(PYTHON) -m pytest tests

coverage:
	$(PYTHON) -m pytest --cov=ledgerline --cov-report=term-missing tests

run:
	FLASK_APP=wsgi.py FLASK_ENV=development $(PYTHON) -m flask run
