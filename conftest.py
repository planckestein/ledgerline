# Shared fixtures live in tests/support so that both the main suite (tests/)
# and the assessment acceptance suites (tasks/*/tests/) can use them.
pytest_plugins = ["tests.support.fixtures"]
