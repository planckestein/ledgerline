# Ledgerline

Ledgerline is a multi-tenant subscription billing service written in Python 3.8
with Flask and SQLAlchemy.

## Development

```bash
python3.8 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
make lint test
```
