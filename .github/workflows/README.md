# GitHub Actions Workflows

This directory contains automated CI/CD workflows for The Stallion Bullets application.

## Available Workflows

### 1. Run Tests (`tests.yml`)
Runs the complete Django test suite on every push and pull request.

**Triggers:**
- Push to `main`, `master`, or `develop` branches
- Pull requests targeting `main`, `master`, or `develop` branches

**Configuration:**
- Tests run on Python 3.10, 3.11, and 3.12
- Installs dependencies from `config/requirements.txt`
- Runs: `python manage.py test bullets --verbosity=2`

**Test Coverage:**
- All tests in `bullets` are discovered automatically, including newly added tests.
- `ScheduleTests` covers unique opponents, reversed/stroman encounters, and the exception when there are too few players.
- `CompetitionFlowTests` covers the per-player duplicate-opponent audit and its total immediately after creating an evening, before any results are entered.
- Also includes legacy imports, season standings, application pages, and database snapshots.

### 2. Code Quality (`lint.yml`)
Runs flake8 linting checks to maintain code standards.

**Triggers:**
- Push to `main`, `master`, or `develop` branches
- Pull requests targeting `main`, `master`, or `develop` branches

**Configuration:**
- Runs on Python 3.11
- Checks for syntax errors and undefined names (strict mode)
- Provides warnings for complexity and line length (advisory mode)
- Max complexity: 10
- Max line length: 127 characters

## Local Testing

To run tests locally before pushing:

```bash
cd scripts
python manage.py test bullets --verbosity=2
```

To run linting locally:

```bash
pip install flake8
flake8 bullets scripts stallion_bullets
```

## Branch Protection

For production-grade protection, consider enabling branch protection rules that:
- Require status checks to pass before merging (both `Run Tests` and `Code Quality`)
- Require pull request reviews before merging
- Require branches to be up to date before merging
