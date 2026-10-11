# Publication copy verification

The curated source snapshot was checked on 11 October 2026.

| Check | Result | Scope |
|---|---|---|
| NLP regression suite | 65 passed | Copied source and shared contracts in a disposable container |
| Platform regression suite | 13 passed | Copied source; isolated in-memory SQLite database |
| Frontend TypeScript | Passed | Copied source using the existing installed dependency packages |
| Docker Compose configuration | Passed | Supplied a validation password without creating an environment file |
| Personal identifier scan | Passed | Student names, student IDs and private host paths; checkpoint namespace intentionally allowed in model links |
| Common credential patterns | Passed | Static publication checker; not an exhaustive secret-detection guarantee |
| Python syntax and structured data | Passed | All copied Python files and JSON; TypeScript configuration permits JSON comments |
| Notebook cleanup | Passed | Outputs, execution counts and transient metadata removed |
| Documentation links | Passed | Relative Markdown links and image targets |
| Screenshot review | Passed | Six application images checked for contributor identity and browser chrome |

NLP tests use mock/hash isolation where appropriate; trained-model benchmark results are saved historical artifacts. The tests did not query the operational database or recreate the training runs. One test-library deprecation warning remains. Public hosting and load behavior were not validated by these checks.

The download package adds generated environment setup scripts and an explicit Docker quickstart. Container names are project-scoped so an alternate Compose project name can be used without fixed container-name collisions.

Windows PowerShell and Linux/macOS startup scripts were exercised in temporary folders using their preparation-only options. Both generated a random 64-character hex database password, selected the trained checkpoint IDs and preserved existing environment settings. The updated Compose configuration validates. Runtime source and tests are byte-identical to the earlier tested copy. First-launch full model downloads and an end-to-end launch of this new stack were not repeated.
