PYTHON ?= python

.PHONY: install lint format test test-postgres coverage compat migrate run worker

install:
	$(PYTHON) -m pip install -r requirements-dev.txt

lint:
	$(PYTHON) -m flake8 ledgerline tests migrations scripts *.py
	$(PYTHON) -m black --check ledgerline tests migrations scripts *.py
	$(PYTHON) -m isort --check-only ledgerline tests migrations scripts *.py

format:
	$(PYTHON) -m isort ledgerline tests migrations scripts *.py
	$(PYTHON) -m black ledgerline tests migrations scripts *.py

test:
	$(PYTHON) -m pytest tests

test-postgres:
	TEST_DATABASE_URL=postgresql://ledgerline:ledgerline@localhost:5432/ledgerline_test $(PYTHON) -m pytest tests

compat:
	$(PYTHON) scripts/check_2020_compat.py --pypi

coverage:
	$(PYTHON) -m pytest --cov=ledgerline --cov-report=term-missing tests

migrate:
	FLASK_APP=wsgi.py $(PYTHON) -m flask db upgrade

run:
	FLASK_APP=wsgi.py FLASK_ENV=development $(PYTHON) -m flask run

worker:
	celery -A celery_worker.celery worker -B -l info
