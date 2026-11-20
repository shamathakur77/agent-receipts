# CLAUDE.md

Rules for any agent or person changing this repository.

1. Evals first. The 5 checks in `evals/test_evals.py` come before code, and they must pass before anything visual is added.
2. Ugly version first. Plain JSONL, standard library only. No new dependency without a written reason.
3. Never store raw arguments, raw results, names, addresses or exception messages in a receipt.
4. Public content is synthetic only. No real personal, family or employer data in code, tests, demo data, docs or commit messages.
5. Every external fact gets a URL and a date in `FACTS.md`. If it cannot be verified, it does not ship.
6. Every new receipt field is added to the table in `COMPLIANCE.md`. A test fails if it is missing.
7. No em dashes. No rhetorical questions or hooks in public copy. Say so when unsure.
8. A failed scheduled run opens an issue. A schedule that stops entirely is only visible through the dashboard stale banner.
9. Secrets live in Actions secrets or environment variables, never in git. `scripts/secret_scan.py` runs in pre-commit and CI.
10. Test against the real third-party SDK, not only a fake. The fake hid a wrong error-flag name once.

Run everything: `python -m unittest discover -s evals -v`
