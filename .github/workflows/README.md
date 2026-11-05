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
- 66 total tests across multiple test classes:
  - CompetitionFlowTests (34 tests)
  - LegacyImportTests (9 tests)
  - SeasonStandingsHistoryTests (7 tests)
  - AboutPageTests (1 test)
  - DatabaseSnapshotTests (2 tests)
  - ScheduleTests (13 tests)

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
