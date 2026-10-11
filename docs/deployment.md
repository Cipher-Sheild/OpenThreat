# Hosting and operations

The included Compose configuration is a development stack. Service ports are bound to loopback. Publishing this repository does not expose a working hosted service and does not prove the application is ready for anonymous internet traffic.

Before shared hosting, provide authentication and role authorization, TLS, constrained uploads, resource limits, rate limiting, monitoring, backups and a tested restore process. Public PostgreSQL and Qdrant ports should remain private. Configure CORS for the actual frontend origin and use a secret store or deployment environment for passwords and API keys.

The application currently uses a bounded in-process extraction worker. Durable distributed jobs, multi-user load measurements and richer operational recovery are future work. CPU inference and first-start downloads can take time; model readiness is distinct from process health.

For a hosted build, configure the model checkpoints independently of Git. Pin image and model revisions for repeatable deployment. Migrations apply during platform startup; take a backup before an upgrade. `docker compose down` preserves persistent volumes; deleting volumes destroys stored intelligence. Destructive reset utilities require explicit flags and are maintenance tools, not deployment steps.

After hosting, add the verified public URL to the README. Do not include secrets, a real `.env`, database exports, source collections, model caches or raw logs in commits. Keep collected source content and its redistribution terms separate from the repository license.
