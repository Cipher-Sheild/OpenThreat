# Publish this repository

Recommended repository name: `openthreat-nlp`. Use this directory as a new repository root so the existing development Git history is not uploaded. The public snapshot contains source, training and evaluation code, tests, screenshots, vector diagrams, sanitized setup and third-party notices. It excludes academic cover pages, student identifiers, credentials, caches, trained weights, raw corpora and operational databases.

Create an empty public repository on GitHub, initialize Git in this directory, and add only this directory's files. Review the staged changes before the first commit. Push to the new repository URL after confirming the account and visibility. No GitHub repository or remote is configured by this preparation step. Push every tracked file from this folder, including frontend, both services, diagrams and the README; do not push only the README. The trained-model namespace is intentionally retained in download links.

MIT permits reuse of original project code; external resources retain their own terms. Future commits can reintroduce sensitive material, so run `python scripts/check_public_release.py` before publishing updates. The check uses common secret patterns and excluded file types; it is an aid rather than a guarantee of perfect detection.

## First push

Create an empty public repository named `openthreat-nlp` on your GitHub account. Do not initialize its README or license remotely because both are already in this folder. Open a terminal inside this complete folder, replace the URL placeholder below with the repository URL, and run:

```sh
git init -b main
git add .
git status
git commit -m "Publish OpenThreat NLP application and documentation"
git remote add origin YOUR_PUBLIC_REPOSITORY_URL
git push -u origin main
```

Review `git status` before committing: frontend, NLP, platform, Docker files, scripts, documentation and images belong in the commit. `.env`, caches, downloaded weights and databases do not. Configure your preferred commit identity if Git requests one; GitHub account and commit attribution are separate from names in application documentation.

Visitors can choose **Code > Download ZIP**, extract the whole repository, install Docker and run `start.ps1` or `start.sh`. The README and linked quickstart describe these steps. Publish the entire source folder; the preparation ZIP itself does not need to be committed.
