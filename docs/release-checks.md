# Verification after the service reorganization

The active source tree uses `services/nlp`, `services/platform` and `frontend`. Shared contracts remain in `docs/contracts`. These checks cover the renamed working tree.

| Check | Result | Scope |
|---|---|---|
| NLP regression suite | 58 passed, 1 module skipped | Isolated hash embedding configuration and in-process FastAPI client. The optional torch/transformers model-test module was unavailable in this test environment. |
| Platform regression suite | 13 passed | Isolated in-memory SQLite database. No operational database was queried. |
| Frontend TypeScript and production build | Passed | Existing installed dependencies, TypeScript check and Vite build. |
| Compose configuration | Passed | `.env.example` and a temporary validation password. |
| Public snapshot | Checked before commit | Staged credential/exclusion scan and repository path review. |

The earlier recorded container run passed 65 NLP and 13 platform tests, including the tiny locally initialized transformer tests. That historical result is separate from this fresh 58-test NLP run. No new trained-model benchmark or training run was performed. Saved benchmark results remain under `services/nlp/evaluation` and `docs/evaluation`.

Docker Desktop did not provide a usable engine during this verification session, so a fresh complete application launch after the rename was not confirmed. Runtime data, environment settings and cached weights were preserved. Start Docker and follow the README before the demo.

Remaining non-fatal warnings include a large frontend bundle chunk, test-client deprecation and naive UTC datetime deprecations. Hosting, load testing and production security remain outside these checks. Regression tests and saved task benchmarks do not establish real-world end-to-end extraction accuracy.
