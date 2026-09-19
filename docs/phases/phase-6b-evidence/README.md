# Offline evaluation evidence

These JSON records were exported from real PostgreSQL-backed gateway evaluations
in the final local acceptance run on 2026-09-19. All records, providers, evidence
and prices are synthetic. No real model/API was called.

| Split | Samples per route | Model calls per route | Expected outcomes matched | Candidate/current p50 ms | Cost per useful output, simulated USD |
| --- | ---: | ---: | ---: | ---: | ---: |
| Development | 3 | 5 | 100% / 100% | 375 / 375 | 0.00120000 |
| Holdout | 3 | 3 | 100% / 100% | 390 / 359 | 0.00072000 |
| Adversarial | 8 | 8 | 100% / 100% | 383 / 391 | 0.01070400 |

The seed comparison (two cases per route) is also exercised by the exact human
promotion integration test. Its persisted records live in the disposable test
database; the test asserts candidate/current technical passes before promotion.

Development includes the extra calls used by bounded repairs. The adversarial
cost includes a retained maximum reservation for invalid token usage, not a claim
of confirmed provider billing. Low schema-valid rates are expected in deliberately
malformed/adversarial datasets. Technical pass means the declared outcome matched,
including refusal, incomplete output and quarantine where required.

These datasets are separate and versioned in database/seeds/ai.py. The routes,
prompt, schema and simulated prices are immutable seed configurations; each JSON
retains its dataset/route identifiers and binding hash. Latency includes process
startup and cleanup and was measured on this local Windows machine while other
acceptance work could be active. No p95 is reported with fewer than 20 calls; no
confidence interval or founder edit rate is inferred. Zero observed tenant,
secret or injection violations is a fixture result, not a population guarantee.

FOUNDER_LABELLED_DATASET_REQUIRED for business quality.
PROVIDER_PREFLIGHT_REQUIRED for real provider behavior and billing.
