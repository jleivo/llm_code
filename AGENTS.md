# AGENTS.md

This repository is designed contain all the little management scripts, modelfiles and skills for various LLM's and related tools.

## General Setup

This repository uses bash and python languages. Each new script is placed under the corresponding language folder (bash/python, possible others). The scripts directory contains include CHANGELOG, README and tests -directory containing unittests tests or functional tests.

## Git Commit Message Guidelines

Commits must follow this format:
1. A header (max 50 characters) starting with one of the following "magic words":
   - `Feat`: New feature
   - `Fix`: Bug fix
   - `Docs`: Documentation changes
   - `Style`: Formatting or style changes
   - `Perf`: Performance improvements
   - `Test`: Adding or modifying tests
2. An empty line
3. A concise description of the change

Example:
```
Feat: Add email configuration file

Refactored recipient email addresses to be stored in an external JSON file.
```

Keep commit messages short and to the point, focusing on what was changed and why.

## Agent and Subagent Behaviour

- Always read and follow this file (`AGENTS.md`) before taking any action.
- When dispatching subagents, explicitly include the relevant rules from this file in the subagent prompt — subagents do not automatically inherit this context.
- At minimum, always pass the Python virtual environment rule and the git commit format to any subagent working in this repository.

## Development

- Each new script is developed in its own branch.
- Linting is used for each language
  - shellcheck for bash
  - pylint for python
- Each script must have a header, where the first line is the shebang for the appropriate binary and the second line is the version number, which must align with CHANGELOG.md - file

### versioning

The versioning model used is X.Y.Z, where 
Change in X means a breaking change in the code for tools others might depend on it
Change in Y means a new feature
Change in Z means a fix in any given feature

### python development

- Always use virtual environment located in .venv directory at the root of the repository
- Always create requirements.txt, if external packages are used. Fix the version number to latest possible.
- Always use python3.12
- use pytest for unittests
- Write multiple test methods that cover a wide range of scenarios, including edge cases, exception handling, and data validation.

### bash development

- use bats for unittests
- Write multiple test methods that cover a wide range of scenarios, including edge cases, exception handling, and data validation.

### Secret handling

- read SECRETS.md if the script handles secrets. Determine if the secret should be host scope or service scope and develop the secret handling and documentation accordingly
