## ADDED Requirements

### Requirement: CI workflow SHALL run on push and pull requests
The GitHub Actions CI workflow SHALL trigger on push to `main` branch and on all pull requests targeting `main`.

#### Scenario: Push to main triggers CI
- **WHEN** code is pushed to the `main` branch
- **THEN** the CI workflow SHALL execute lint and test steps

#### Scenario: PR triggers CI
- **WHEN** a pull request is opened or updated targeting `main`
- **THEN** the CI workflow SHALL execute lint and test steps

### Requirement: CI workflow SHALL test on Python 3.11 and 3.12
The CI workflow SHALL use a matrix strategy to run tests on both Python 3.11 and Python 3.12.

#### Scenario: Matrix test execution
- **WHEN** the CI workflow is triggered
- **THEN** it SHALL run the full test suite on both Python 3.11 and Python 3.12 in parallel

### Requirement: CI workflow SHALL run linting with ruff
The CI workflow SHALL run `ruff check` as a linting step before running tests. The workflow SHALL fail if linting errors are found.

#### Scenario: Lint passes
- **WHEN** all source code passes ruff checks
- **THEN** the CI workflow SHALL proceed to the test step

#### Scenario: Lint fails
- **WHEN** source code has ruff violations
- **THEN** the CI workflow SHALL fail and report the violations

### Requirement: CI workflow SHALL run pytest with coverage
The CI workflow SHALL run `pytest` with coverage reporting. Tests SHALL pass with a minimum coverage threshold.

#### Scenario: All tests pass
- **WHEN** all unit tests pass
- **THEN** the CI workflow SHALL report success and display coverage summary

#### Scenario: Test failure
- **WHEN** one or more tests fail
- **THEN** the CI workflow SHALL fail and report which tests failed

### Requirement: Project SHALL include standard Git configuration
The project SHALL include `.gitignore` (Python template), `README.md` with project overview and setup instructions, and `LICENSE` file.

#### Scenario: Git repository initialized
- **WHEN** the project is set up
- **THEN** it SHALL contain `.gitignore`, `README.md`, `LICENSE`, and `pyproject.toml` at the repository root
