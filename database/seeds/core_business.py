"""Synthetic acceptance fixtures only. Never called at application startup.

Fixture provisioning uses the migration identity, as does the Phase 2 seed.
Production/API writes use CoreCommands. Tests separately prove runtime rejection.
"""

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from company_os.adapters.local_documents import FakeDocumentStore
from company_os.adapters.local_source import FakeSourceProvider
from company_os.application.business import CoreCommands
from company_os.business_contracts import ScoreInput
from company_os.domain.scoring import canonical_hash
from company_os.persistence.business import get, insert, update
from company_os.persistence.database import rows, transaction
from sqlalchemy import Engine

from database.seeds.synthetic import key


def seed_business(engine: Engine) -> None:
    fields = [
        "account.identity",
        "person.identity",
        "contact.identity",
        "industry_code",
        "country_code",
        "problem",
        "deal_capacity",
        "observed_trigger",
        "employment.account_id",
    ]
    now = datetime.now(UTC).replace(microsecond=0)
    store = FakeDocumentStore(Path(".local/documents"))
    for letter, count in [("a", 12), ("b", 10)]:
        with transaction(engine, key(f"user-{letter}"), key(f"workspace-{letter}"), 1) as conn:
            if rows(
                conn, "SELECT id FROM app.accounts WHERE id=:id", {"id": key(f"{letter}-account-0")}
            ):
                continue  # Preserve demo reviews, revocations and append-only history.
            doc = insert(
                conn,
                "documents",
                {
                    "store_key": "fake_local",
                    "external_file_id": f"fixture:{letter}-rights",
                    "title": f"Synthetic {letter.upper()} source rights",
                    "classification": "internal",
                    "state": "active",
                },
                identifier=key(f"{letter}-rights-document"),
            )
            content = f"Workspace {letter.upper()} synthetic research only; no sending permission.".encode()
            digest = store.save_snapshot(content)
            doc_version = insert(
                conn,
                "document_versions",
                {
                    "document_id": doc["id"],
                    "version": 1,
                    "export_sha256": digest,
                    "media_type": "text/plain",
                    "byte_count": len(content),
                    "snapshot_file_id": digest,
                    "observed_at": now,
                    "is_final": True,
                },
                identifier=key(f"{letter}-rights-version"),
            )
            insert(
                conn,
                "document_grants",
                {
                    "document_id": doc["id"],
                    "principal_id": key(f"user-{letter}"),
                    "permission": "read",
                },
            )
            for status in ["approved", "expired", "revoked", "pending"]:
                insert(
                    conn,
                    "data_sources",
                    {
                        "name": f"Synthetic {status} source",
                        "source_type": "human",
                        "rights_document_version_id": doc_version["id"],
                        "rights_status": status,
                        "permitted_purposes": ["research", "knowledge"],
                        "allowed_fields": fields,
                        "retention_days": 90,
                        "expires_at": now + timedelta(days=-1 if status == "expired" else 60),
                    },
                    identifier=key(f"{letter}-source-{status}"),
                )
            icp = insert(
                conn, "icps", {"name": "Synthetic core ICP"}, identifier=key(f"{letter}-icp")
            )
            criteria = {
                "industries": ["synthetic_services", "synthetic_excluded"],
                "countries": ["US"],
                "required_problem_fact_keys": ["problem"],
                "target_roles": ["Synthetic Operations Lead"],
                "required_evidence_keys": ["industry_code", "problem", "deal_capacity"],
            }
            exclusions = {"domains": [], "countries": [], "industry_codes": ["synthetic_excluded"]}
            policy = {
                "version": "synthetic-1",
                "contract": "DATA-026/binary-fixture-v1",
                "economics_fact_key": "deal_capacity",
                "trigger_fact_key": "observed_trigger",
            }
            icpv = insert(
                conn,
                "icp_versions",
                {
                    "icp_id": icp["id"],
                    "version": 1,
                    "criteria": criteria,
                    "exclusions": exclusions,
                    "score_policy": policy,
                    "content_hash": canonical_hash(
                        {"criteria": criteria, "exclusions": exclusions, "score_policy": policy}
                    ),
                },
                identifier=key(f"{letter}-icp-version"),
            )
            offer = insert(
                conn,
                "offers",
                {"name": "Synthetic operating review"},
                identifier=key(f"{letter}-offer"),
            )
            offerv = insert(
                conn,
                "offer_versions",
                {
                    "offer_id": offer["id"],
                    "version": 1,
                    "scope": "Synthetic internal operating review only",
                    "exclusions": "No external delivery or commercial commitment",
                    "capacity_limit": 2,
                    "content_hash": canonical_hash({"fixture": "synthetic-offer-1"}),
                },
                identifier=key(f"{letter}-offer-version"),
            )
            insert(
                conn,
                "offer_proofs",
                {"offer_version_id": offerv["id"], "document_version_id": doc_version["id"]},
            )
            for index in range(count):
                label = [
                    "Shared Parent",
                    "Shared Subsidiary",
                    "Missing Trigger",
                    "Excluded High Score",
                    "Retracted Fact",
                    "Expired Fact",
                    "Revoked Source",
                    "Expired Source",
                    "Merge Candidate",
                    "Merge Candidate",
                    "Unknown Size",
                    "Strong Fit",
                ][index]
                account = insert(
                    conn,
                    "accounts",
                    {
                        "display_name": f"Synthetic {letter.upper()} {label}",
                        "primary_domain": "shared.synthetic.example"
                        if index < 2
                        else f"unit-{index}.synthetic.example",
                        "identity_discriminator": f"unit-{index}",
                        "parent_id": key(f"{letter}-account-0") if index == 1 else None,
                        "country_code": "US",
                        "industry_code": "synthetic_excluded"
                        if index == 3
                        else "synthetic_services",
                        "size_min": None if index == 10 else 20,
                        "size_max": None if index == 10 else 50,
                        "status": "active",
                        "source_id": key(f"{letter}-source-approved"),
                    },
                    identifier=key(f"{letter}-account-{index}"),
                )
                evidence_ids = []
                for fact_key, fact_type, value in FakeSourceProvider.facts(
                    account["industry_code"]
                ):
                    if index == 2 and fact_key == "observed_trigger":
                        continue
                    source_status = (
                        "revoked" if index == 6 else "expired" if index == 7 else "approved"
                    )
                    expired = index == 5 and fact_key == "deal_capacity"
                    item = insert(
                        conn,
                        "evidence",
                        {
                            "subject_id": account["id"],
                            "source_id": key(f"{letter}-source-{source_status}"),
                            "provider_record_id": f"synthetic-{index}-{fact_key}",
                            "fact_key": fact_key,
                            "fact_type": fact_type,
                            f"{fact_type}_value": value,
                            "observed_at": now - timedelta(days=2),
                            "expires_at": now + timedelta(days=-1 if expired else 30),
                            "content_sha256": canonical_hash(
                                {"subject": str(account["id"]), "key": fact_key, "value": value}
                            ),
                            "entity_match": "confirmed",
                            "fact_kind": "observed",
                        },
                        identifier=key(f"{letter}-evidence-{index}-{fact_key}"),
                    )
                    evidence_ids.append(item["id"])
                    if index == 4 and fact_key == "problem":
                        insert(
                            conn,
                            "evidence_retractions",
                            {
                                "evidence_id": item["id"],
                                "reason": "Synthetic observation was withdrawn",
                            },
                        )
                    if fact_key == "observed_trigger":
                        insert(
                            conn,
                            "signals",
                            {
                                "subject_id": account["id"],
                                "kind": "hiring",
                                "observed_at": now - timedelta(days=2),
                                "expires_at": now + timedelta(days=30),
                                "evidence_id": item["id"],
                                "relevance_summary": "Observed synthetic job posting; buying intent unknown",
                                "status": "accepted",
                                "fingerprint": canonical_hash({"fixture_signal": str(item["id"])}),
                            },
                        )
                lead = insert(
                    conn,
                    "leads",
                    {
                        "account_id": account["id"],
                        "offer_version_id": offerv["id"],
                        "icp_version_id": icpv["id"],
                        "state": "discovered",
                        "owner_principal_id": key(f"user-{letter}"),
                    },
                    identifier=key(f"{letter}-lead-{index}"),
                )
                for subject_id in [account["id"], lead["id"]]:
                    CoreCommands.score(
                        conn,
                        ScoreInput(
                            subject_id=subject_id,
                            icp_version_id=icpv["id"],
                            evidence_ids=evidence_ids,
                        ).model_dump(mode="json"),
                        None,
                        None,
                    )
            for index, status in [
                (0, "current"),
                (1, "former"),
                (2, "uncertain"),
                (3, "current"),
                (8, "current"),
                (9, "current"),
            ]:
                person = insert(
                    conn,
                    "people",
                    {
                        "display_name": "Synthetic Alex Example"
                        if index in {0, 3}
                        else f"Synthetic Person {index}",
                        "status": "active",
                        "source_id": key(f"{letter}-source-approved"),
                    },
                    identifier=key(f"{letter}-person-{index}"),
                )
                ev = insert(
                    conn,
                    "evidence",
                    {
                        "subject_id": person["id"],
                        "source_id": key(f"{letter}-source-approved"),
                        "provider_record_id": f"synthetic-employment-{index}",
                        "fact_key": "employment.account_id",
                        "fact_type": "string",
                        "string_value": str(key(f"{letter}-account-{index}")),
                        "observed_at": now - timedelta(days=1),
                        "expires_at": now + timedelta(days=30),
                        "content_sha256": canonical_hash({"employment": str(person["id"])}),
                        "entity_match": "confirmed",
                        "fact_kind": "reported",
                    },
                )
                insert(
                    conn,
                    "employments",
                    {
                        "person_id": person["id"],
                        "account_id": key(f"{letter}-account-{index}"),
                        "title": "Synthetic Operations Lead",
                        "start_date": (now - timedelta(days=200)).date(),
                        "end_date": (now - timedelta(days=30)).date()
                        if status == "former"
                        else None,
                        "observed_at": now - timedelta(days=1),
                        "evidence_id": ev["id"],
                        "status": status,
                    },
                    identifier=key(f"{letter}-employment-{index}"),
                )
                contact = insert(
                    conn,
                    "contact_points",
                    {
                        "person_id": person["id"],
                        "account_id": key(f"{letter}-account-{index}"),
                        "kind": "email",
                        "value_original": f"synthetic-{letter}-{index}@example.test",
                        "value_normalized": f"synthetic-{letter}-{index}@example.test",
                        "match_key": f"synthetic-{letter}-{index}@example.test",
                        "status": "active",
                        "source_id": key(f"{letter}-source-approved"),
                    },
                    identifier=key(f"{letter}-contact-{index}"),
                )
                insert(
                    conn,
                    "permission_assessments",
                    {
                        "contact_point_id": contact["id"],
                        "purpose": "outreach",
                        "channel": "email",
                        "result": "unknown",
                        "reason_codes": ["phase_3_no_outreach_permission"],
                        "expires_at": now,
                    },
                )
                lead = get(conn, "leads", key(f"{letter}-lead-{index}"))
                update(
                    conn,
                    "leads",
                    lead["id"],
                    lead["record_version"],
                    {"person_id": person["id"], "contact_point_id": contact["id"]},
                )
            for status in ["approved", "stale", "revoked"]:
                content_text = f"Synthetic {letter.upper()} workspace-only {status} knowledge: provenance evidence and unknown facts."
                blob = content_text.encode()
                snapshot_hash = store.save_snapshot(blob)
                knowledge_doc = insert(
                    conn,
                    "documents",
                    {
                        "store_key": "fake_local",
                        "external_file_id": f"fixture:{letter}-knowledge-{status}",
                        "title": f"Synthetic {letter.upper()} {status} operating knowledge",
                        "classification": "internal",
                        "state": "revoked" if status == "revoked" else "active",
                    },
                    identifier=key(f"{letter}-knowledge-document-{status}"),
                )
                knowledge_version = insert(
                    conn,
                    "document_versions",
                    {
                        "document_id": knowledge_doc["id"],
                        "version": 1,
                        "export_sha256": snapshot_hash,
                        "media_type": "text/plain",
                        "byte_count": len(blob),
                        "snapshot_file_id": snapshot_hash,
                        "observed_at": now,
                        "is_final": True,
                    },
                )
                insert(
                    conn,
                    "document_grants",
                    {
                        "document_id": knowledge_doc["id"],
                        "principal_id": key(f"user-{letter}"),
                        "permission": "read",
                    },
                )
                decision = insert(
                    conn,
                    "decisions",
                    {
                        "subject_id": knowledge_doc["id"],
                        "decision_type": "knowledge_review",
                        "outcome": "approve",
                        "summary": "Explicitly synthetic seed review; no real human authorization claim",
                        "alternatives": [],
                        "decided_by": key(f"user-{letter}"),
                    },
                )
                knowledge = insert(
                    conn,
                    "knowledge_items",
                    {
                        "document_version_id": knowledge_version["id"],
                        "kind": "sop",
                        "approved_decision_id": decision["id"],
                        "valid_from": now - timedelta(days=10),
                        "review_due_at": now + timedelta(days=-1 if status == "stale" else 30),
                        "status": status,
                    },
                    identifier=key(f"{letter}-knowledge-{status}"),
                )
                insert(
                    conn,
                    "knowledge_chunks",
                    {
                        "knowledge_id": knowledge["id"],
                        "ordinal": 0,
                        "text": content_text,
                        "hash": hashlib.sha256(content_text.encode()).hexdigest(),
                    },
                )
    print("Phase 3 synthetic A/B business fixture ready (22 accounts); existing state preserved")
