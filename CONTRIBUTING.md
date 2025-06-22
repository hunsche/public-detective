# Contributing to Public Detective

First off, thank you for considering contributing to Public Detective! We love to receive contributions from our community — you!

Public Detective is a civic tech project that aims to bring more transparency to public procurement in Brazil. Your help is essential to making this tool more effective and impactful. By contributing, you're helping to build a more accountable government.

## How Can I Contribute?

There are many ways to contribute, and many of them don't involve writing a single line of code.

### 🐛 Reporting Bugs
If you find a bug—something isn't working as expected—please [open a bug report issue](https://github.com/hunsche/public-detective/issues/new?template=bug_report.md). Be sure to include as much detail as possible, including steps to reproduce the bug, the expected outcome, and the actual outcome.

### 💡 Suggesting Enhancements
Have an idea for a new feature or an improvement to an existing one? We'd love to hear it. [Open a feature request issue](https://github.com/hunsche/public-detective/issues/new?template=feature_request.md) to start the discussion. This is a great way to contribute your ideas and domain expertise.

### 📖 Improving Documentation
Good documentation is key to a successful open-source project. If you find typos, unclear sentences, or areas in the `README.md` or other documents that could be improved, please don't hesitate to open an issue or submit a pull request with your suggested changes.

### 💻 Writing Code
If you're ready to jump into the code, we're excited to have you. You can help by:
- Picking up an existing issue labeled `help wanted` or `good first issue`.
- Implementing a new feature you've discussed with the team.
- Adding or improving tests.

## Your First Code Contribution

Ready to submit code? Here’s our workflow.

### 1. Fork the Repository
Fork the project to your own GitHub account by clicking the "Fork" button at the top right of the main repository page.

### 2. Create a Branch
Create a new branch from `main` in your fork for your feature or bug fix. Use a descriptive name.
```sh
git checkout -b feature/my-new-amazing-feature
````

### 3. Set Up Your Environment

Make sure your development environment is set up by following the instructions in the `README.md`.

```sh
# Install dependencies
poetry install
```

### 4. Make Your Changes

Implement your feature or fix the bug. Make sure your code is clean, and follows the project's style.

### 5. Commit Your Changes

Commit your changes with a clear and descriptive commit message. We follow the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) specification.

```sh
# Example of a commit message
git commit -m "feat: Add new detector for overly restrictive deadlines"
```

Common prefixes include:

  - `feat`: A new feature
  - `fix`: A bug fix
  - `docs`: Documentation only changes
  - `style`: Changes that do not affect the meaning of the code (white-space, formatting, etc.)
  - `refactor`: A code change that neither fixes a bug nor adds a feature
  - `test`: Adding missing tests or correcting existing tests

### 6. Push to Your Branch

Push your new branch to your forked repository.

```sh
git push origin feature/my-new-amazing-feature
```

### 7. Open a Pull Request

Go to the `hunsche/public-detective` repository on GitHub and open a new Pull Request.

  - Make sure your PR is against the `main` branch of the original repository.
  - Provide a clear title and a detailed description of your changes. Explain *what* you changed and *why*.
  - If your PR addresses an open issue, link to it in the description (e.g., `Fixes #123`).

Once your PR is open, a project maintainer will review it. We may ask for changes, but we'll work with you to get your contribution merged. We appreciate your effort!

## Style Guides

### Python Code

This project uses [`pre-commit`](https://pre-commit.com/) to automatically manage code formatting and quality checks. The configuration is defined in the `.pre-commit-config.yaml` file at the root of the project.

After you run `pre-commit install` once, these hooks will be active. Now, every time you run `git commit`, `pre-commit` will automatically run tools like:

  - **[Black](https://github.com/psf/black):** for consistent code formatting.
  - **[Flake8](https://flake8.pycqa.org/en/latest/):** for identifying programming errors and style violations.
  - **[isort](https://pycqa.github.io/isort/):** for automatically sorting imports.

If any of these checks fail, your commit will be aborted. Simply review the error messages (some tools like Black will fix the files for you automatically), `git add` the changes, and try to commit again. This process ensures that all code committed to the repository maintains a high standard of quality and a consistent style.

### Git Commit Messages

As mentioned above, we use the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) standard. This helps us automate changelogs and makes the project history more readable.

-----

Thank you again for your interest in contributing to **Public Detective**!
