# Maintaining the public repository

The complete application is published at https://github.com/Cipher-Sheild/OpenThreat. The repository includes the frontend, both backend services, Docker setup, training and evaluation code, regression tests, architecture, screenshots and MIT license. Clone or download the whole repository to run it.

## Before an update

Keep `.env`, model weights, caches, external corpora, uploaded reports, databases and academic deliverables out of Git. `.gitignore` excludes these files. Existing Hugging Face checkpoint namespaces are intentionally retained so automatic model setup can download the deployed models. Third-party resources retain their own terms.

Review the changes and scan the staged snapshot before committing:

```sh
git add .
python scripts/check_repository.py
git diff --cached --stat
git status
git commit -m "Describe the application change"
git push origin main
```

The checker reads staged files and flags common credential patterns and private file types. It does not inspect ignored operational files or guarantee that every possible secret has been detected. Run the relevant service tests and frontend build as described in the root README. Never force-push over someone else's work.

## Starting a downloaded copy

Install and start Docker with Compose, extract or clone the complete repository, then run `start.ps1` on Windows or `start.sh` on Linux/macOS. The script preserves an existing environment file and generates a password for a new setup. See [quickstart](quickstart.md) for the complete procedure.
