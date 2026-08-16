# 🤝 Contributing to polyglot-relay

We welcome contributions to polyglot-relay! To make sure the process goes smoothly, please follow these guidelines:

## 📋 Code of Conduct

Please note that all participants in our project are expected to follow our [Code of Conduct](#-code-of-conduct). Make sure to review it before contributing.

## 🛠 How to Contribute

1. **Fork the repository**:
   Fork the project to your GitHub account using the GitHub interface.

2. **Create a new branch**:
   Use a descriptive branch name for your feature or bugfix:

   git checkout -b feature/your-feature-name

3. **Make your changes**:
   Implement your feature or fix the bug in your branch. Make sure to include tests where applicable and follow coding standards.

4. **Test your changes**:
   Run the test suite to ensure your changes don’t break any functionality (the `bot` image only ships production dependencies, so run tests from your local venv, not inside the container):

   pytest

   Changes under `nllb/` need its own venv (heavy ML deps: ctranslate2/transformers/torch, kept separate from the bot's):

   cd nllb && python -m venv venv && source venv/bin/activate && pip install -r requirements.txt -r requirements-dev.txt && pytest

5. **Commit your changes**:
   Use meaningful commit messages that explain what you have done:

   git commit -m "Add feature/fix: Description of changes"

6. **Push your changes**:
   Push your changes to your fork:

   git push origin feature/your-feature-name

7. **Submit a Pull Request**:
   Create a pull request on the main repository, detailing the changes you’ve made. Link any issues your changes resolve and provide context.

## 📑 Guidelines for Contributions

- **Lint your code** before submitting a pull request. We use [pylint](https://www.pylint.org/) and [black](https://black.readthedocs.io/) for linting/formatting.
- Ensure **test coverage** for your code. Uncovered code may delay the approval process.
- Write clear, concise **commit messages**.

Thank you for helping improve!

---

## 📜 License

2026 - This project is licensed under the [GNU General Public License v3.0](https://www.gnu.org/licenses/gpl-3.0.en.html). You are free to use, modify, and distribute this software under the terms of the GPL-3.0 license. For more details, please refer to the [LICENSE](LICENSE) file included in this repository.
