"""Synchronous Phase 3 commands shared by all trusted entry points."""

import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError

from company_os.application.business_ports import DocumentStore
from company_os.application.identity import IdentityService
from company_os.application.scoring import current_input, evaluate
from company_os.business_contracts import (
    AccountInput,
    CommandResult,
    ContactInput,
    CorrectionInput,
    DocumentInput,
    EmploymentInput,
    EvidenceInput,
    ICPVersionInput,
    LeadInput,
    MergeInput,
    NamedInput,
    OfferVersionInput,
    PersonInput,
    ReasonInput,
    ResearchInput,
    RetractionInput,
    ReversalInput,
    ScoreInput,
    SignalInput,
)
from company_os.contracts import Model
from company_os.domain.identity import AccessDenied, SessionIdentity
from company_os.domain.scoring import canonical_hash
from company_os.persistence.business import (
    BusinessError,
    document_allowed,
    get,
    insert,
    invalid_reasons,
    require_source,
    update,
)
from company_os.persistence.database import rows, transaction
from company_os.policy.access import require_permission, require_recent_mfa


class CoreCommands:
    def __init__(self, engine: Engine, identity: IdentityService, documents: DocumentStore) -> None:
        self.engine = engine
        self.identity = identity
        self.documents = documents

    def execute(
        self,
        actor: SessionIdentity,
        workspace_id: UUID,
        command: str,
        body: Model,
        key: str,
        *,
        target: UUID | None = None,
        version: int | None = None,
        request_id: UUID | None = None,
    ) -> CommandResult:
        workspace = self.identity.workspace(actor, workspace_id)
        if workspace is None:
            raise BusinessError("NOT_FOUND", 404)
        handlers = {
            "account.create": self.account,
            "person.create": self.person,
            "employment.create": self.employment,
            "contact.create": self.contact,
            "evidence.create": self.evidence,
            "evidence.retract": self.retract,
            "signal.create": self.signal,
            "icp.create": self.icp,
            "icp.version": self.icp_version,
            "offer.create": self.offer,
            "offer.version": self.offer_version,
            "lead.create": self.lead,
            "score.calculate": self.score,
            "account.correct": self.correction,
            "identity.merge": self.merge,
            "identity.reverse": self.reverse,
            "document.register": self.document,
            "signal.accept": self.accept_signal,
            "lead.begin-research": self.begin_research,
            "lead.complete-research": self.complete_research,
            "lead.disqualify": self.disqualify,
            "lead.archive": self.archive,
        }
        if command not in handlers or not 8 <= len(key) <= 128:
            raise BusinessError("INVALID_REQUEST", 400)
        rid = request_id or uuid4()
        try:
            require_permission(
                workspace["permissions"],
                "identity.review" if command.startswith("identity.") else "business.write",
            )
            if command.startswith("identity."):
                require_recent_mfa(actor)
            if target is not None and version is None:
                raise BusinessError("VERSION_REQUIRED", 400)
            payload = body.model_dump(mode="json")
            request_hash = canonical_hash(
                {"body": payload, "target": str(target), "version": version}
            )
            with transaction(
                self.engine, actor.principal_id, workspace_id, workspace["authz_epoch"]
            ) as conn:
                # All graph/command writers take the same workspace lock before row locks.
                conn.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:w,31))"),
                    {"w": str(workspace_id)},
                )
                previous = rows(
                    conn,
                    "SELECT * FROM app.command_receipts WHERE actor_id=:actor AND command_type=:command AND idempotency_key=:key",
                    {"actor": actor.principal_id, "command": command, "key": key},
                )
                if previous:
                    receipt = previous[0]
                    if receipt["request_hash"] != request_hash:
                        raise BusinessError("IDEMPOTENCY_CONFLICT")
                    return CommandResult(
                        command_id=receipt["id"],
                        result_id=receipt["result_id"],
                        record_version=receipt["result_version"],
                    )
                result = handlers[command](conn, payload, target, version)
                receipt = insert(
                    conn,
                    "command_receipts",
                    {
                        "actor_id": actor.principal_id,
                        "command_type": command,
                        "idempotency_key": key,
                        "request_hash": request_hash,
                        "result_id": result["id"],
                        "result_version": result.get("record_version"),
                    },
                )
                self.audit(
                    conn,
                    actor,
                    rid,
                    receipt["id"],
                    command,
                    result["id"],
                    request_hash,
                    "allow",
                    "committed",
                )
                return CommandResult(
                    command_id=receipt["id"],
                    result_id=result["id"],
                    record_version=result.get("record_version"),
                )
        except (BusinessError, AccessDenied, IntegrityError) as exc:
            with transaction(
                self.engine, actor.principal_id, workspace_id, workspace["authz_epoch"]
            ) as conn:
                self.audit(
                    conn,
                    actor,
                    rid,
                    rid,
                    command,
                    target or workspace_id,
                    "0" * 64,
                    "deny",
                    "rejected",
                )
            if isinstance(exc, IntegrityError):
                raise BusinessError("INVALID_REFERENCE_OR_CONFLICT") from None
            raise

    @staticmethod
    def audit(
        conn: Connection,
        actor: SessionIdentity,
        request_id: UUID,
        command_id: UUID,
        action: str,
        target: UUID,
        payload_hash: str,
        decision: str,
        outcome: str,
    ) -> None:
        conn.execute(
            text(
                """INSERT INTO app.audit_entries(id,workspace_id,created_by,actor_id,actor_type,action_type,target_type,target_id,request_id,correlation_id,command_id,decision,outcome,change_summary,payload_hash,policy_version) VALUES(:id,app.current_workspace_id(),:actor,:actor,'user',:action,'phase3',:target,:request,:request,:command,:decision,:outcome,'Phase 3 synchronous command',:hash,'phase-3')"""
            ),
            {
                "id": uuid4(),
                "actor": actor.principal_id,
                "action": action,
                "target": target,
                "request": request_id,
                "command": command_id,
                "decision": decision,
                "outcome": outcome,
                "hash": payload_hash,
            },
        )

    @staticmethod
    def account(
        conn: Connection, data: dict[str, Any], target: UUID | None, version: int | None
    ) -> dict[str, Any]:
        values = AccountInput.model_validate(data).model_dump()
        require_source(conn, values["source_id"], ["account.identity"])
        if values["parent_id"]:
            get(conn, "accounts", values["parent_id"])
        return insert(conn, "accounts", {**values, "status": "active"})

    @staticmethod
    def person(
        conn: Connection, data: dict[str, Any], target: UUID | None, version: int | None
    ) -> dict[str, Any]:
        values = PersonInput.model_validate(data).model_dump()
        require_source(conn, values["source_id"], ["person.identity"])
        return insert(conn, "people", {**values, "status": "active"})

    @staticmethod
    def employment(
        conn: Connection, data: dict[str, Any], target: UUID | None, version: int | None
    ) -> dict[str, Any]:
        values = EmploymentInput.model_validate(data).model_dump()
        support = get(conn, "evidence", values["evidence_id"])
        if invalid_reasons(conn, support):
            raise BusinessError("STALE_EVIDENCE", 423)
        get(conn, "people", values["person_id"])
        get(conn, "accounts", values["account_id"])
        return insert(conn, "employments", values)

    @staticmethod
    def contact(
        conn: Connection, data: dict[str, Any], target: UUID | None, version: int | None
    ) -> dict[str, Any]:
        values = ContactInput.model_validate(data).model_dump()
        require_source(conn, values["source_id"], ["contact.identity"])
        original = values.pop("value")
        normalized = original.strip()
        kind = values["kind"]
        if kind == "email":
            if normalized.count("@") != 1 or any(c.isspace() for c in normalized):
                raise BusinessError("INVALID_CONTACT", 422)
            local, domain = normalized.rsplit("@", 1)
            if not local or not domain or "." not in domain:
                raise BusinessError("INVALID_CONTACT", 422)
            normalized = local + "@" + domain.lower()
            match = normalized.casefold()  # No plus-tag/dot removal.
        elif kind == "url":
            parsed = urlsplit(normalized)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise BusinessError("INVALID_CONTACT", 422)
            match = normalized
        else:
            if (
                not normalized.startswith("+")
                or not normalized[1:].isdigit()
                or not 8 <= len(normalized) <= 16
            ):
                raise BusinessError("INVALID_CONTACT", 422)
            match = normalized
        for field, table in [("person_id", "people"), ("account_id", "accounts")]:
            if values[field]:
                owner = get(conn, table, values[field])
                if owner["status"] != "active":
                    raise BusinessError("IDENTITY_HOLD", 423)
        result = insert(
            conn,
            "contact_points",
            {
                **values,
                "value_original": original,
                "value_normalized": normalized,
                "match_key": match,
                "status": "active",
            },
        )
        if kind == "email":
            insert(
                conn,
                "permission_assessments",
                {
                    "contact_point_id": result["id"],
                    "purpose": "outreach",
                    "channel": "email",
                    "result": "unknown",
                    "reason_codes": ["phase_3_no_outreach_permission"],
                    "expires_at": datetime.now(UTC),
                },
            )
        return result

    @staticmethod
    def evidence(
        conn: Connection, data: dict[str, Any], target: UUID | None, version: int | None
    ) -> dict[str, Any]:
        body = EvidenceInput.model_validate(data)
        values = body.model_dump()
        source = require_source(conn, body.source_id, [body.fact_key])
        subject = get(conn, "resources", body.subject_id)
        if subject["deleted_at"] is not None:
            raise BusinessError("IDENTITY_HOLD", 423)
        if body.observed_at > datetime.now(UTC):
            raise BusinessError("FUTURE_OBSERVATION", 422)
        if (
            source["retention_days"]
            and (body.expires_at - body.observed_at).total_seconds()
            > source["retention_days"] * 86400
        ):
            raise BusinessError("SOURCE_RETENTION_LIMIT", 423)
        if body.supersedes_id:
            previous = get(conn, "evidence", body.supersedes_id)
            if previous["subject_id"] != body.subject_id or previous["fact_key"] != body.fact_key:
                raise BusinessError("INVALID_SUPERSESSION", 422)
        if body.document_version_id:
            document = get(conn, "document_versions", body.document_version_id)
            if not document_allowed(conn, document["document_id"]):
                raise BusinessError("NOT_FOUND", 404)
        fact = values.pop("fact_value")
        values["fact_type"] = fact["type"]
        values["unit"] = fact["unit"]
        if fact["type"] != "unknown":
            values[f"{fact['type']}_value"] = fact["value"]
        values["content_sha256"] = canonical_hash(body.model_dump(mode="json"))
        return insert(conn, "evidence", values)

    @staticmethod
    def retract(
        conn: Connection, data: dict[str, Any], target: UUID | None, version: int | None
    ) -> dict[str, Any]:
        assert target is not None
        evidence = get(conn, "evidence", target)
        if version != 1:
            raise BusinessError("VERSION_CONFLICT")
        body = RetractionInput.model_validate(data)
        if body.replacement_id:
            replacement = get(conn, "evidence", body.replacement_id)
            if (
                replacement["subject_id"] != evidence["subject_id"]
                or replacement["fact_key"] != evidence["fact_key"]
            ):
                raise BusinessError("INVALID_REPLACEMENT", 422)
        return insert(conn, "evidence_retractions", {"evidence_id": target, **body.model_dump()})

    @staticmethod
    def signal(
        conn: Connection, data: dict[str, Any], target: UUID | None, version: int | None
    ) -> dict[str, Any]:
        body = SignalInput.model_validate(data)
        evidence = get(conn, "evidence", body.evidence_id)
        if (
            invalid_reasons(conn, evidence)
            or evidence["fact_kind"] != "observed"
            or evidence["subject_id"] != body.subject_id
            or evidence["fact_key"] not in {"observed_trigger", f"signal.{body.kind}"}
            or (
                evidence["fact_key"] == "observed_trigger" and evidence["boolean_value"] is not True
            )
        ):
            raise BusinessError("UNSUPPORTED_OBSERVATION", 422)
        if body.observed_at > datetime.now(UTC) or body.observed_at < evidence["observed_at"]:
            raise BusinessError("INVALID_OBSERVATION_TIME", 422)
        return insert(
            conn,
            "signals",
            {
                **body.model_dump(),
                "status": "candidate",
                "fingerprint": canonical_hash(
                    {
                        "evidence": str(body.evidence_id),
                        "kind": body.kind,
                        "event_at": str(body.event_at),
                    }
                ),
            },
        )

    @staticmethod
    def icp(
        conn: Connection, data: dict[str, Any], target: UUID | None, version: int | None
    ) -> dict[str, Any]:
        return insert(conn, "icps", NamedInput.model_validate(data).model_dump())

    @staticmethod
    def offer(
        conn: Connection, data: dict[str, Any], target: UUID | None, version: int | None
    ) -> dict[str, Any]:
        return insert(conn, "offers", NamedInput.model_validate(data).model_dump())

    @staticmethod
    def icp_version(
        conn: Connection, data: dict[str, Any], target: UUID | None, version: int | None
    ) -> dict[str, Any]:
        assert target is not None and version is not None
        parent = get(conn, "icps", target, lock=True)
        if parent["record_version"] != version:
            raise BusinessError("VERSION_CONFLICT")
        body = ICPVersionInput.model_validate(data)
        values = body.model_dump(mode="json")
        excluded = values["exclusions"].pop("account_ids")
        number = conn.execute(
            text("SELECT coalesce(max(version),0)+1 FROM app.icp_versions WHERE icp_id=:id"),
            {"id": target},
        ).scalar_one()
        result = insert(
            conn,
            "icp_versions",
            {
                **values,
                "icp_id": target,
                "version": number,
                "content_hash": canonical_hash(body.model_dump(mode="json")),
            },
        )
        for account in excluded:
            get(conn, "accounts", UUID(account))
            insert(
                conn,
                "icp_excluded_accounts",
                {"icp_version_id": result["id"], "account_id": UUID(account)},
            )
        update(conn, "icps", target, version, {"name": parent["name"]})
        return result

    @staticmethod
    def offer_version(
        conn: Connection, data: dict[str, Any], target: UUID | None, version: int | None
    ) -> dict[str, Any]:
        assert target is not None and version is not None
        parent = get(conn, "offers", target, lock=True)
        if parent["record_version"] != version:
            raise BusinessError("VERSION_CONFLICT")
        body = OfferVersionInput.model_validate(data)
        values = body.model_dump()
        proofs = values.pop("proof_document_version_ids")
        for identifier in [
            *proofs,
            *([body.rate_card_document_version_id] if body.rate_card_document_version_id else []),
        ]:
            document = get(conn, "document_versions", identifier)
            if not document_allowed(conn, document["document_id"]):
                raise BusinessError("NOT_FOUND", 404)
        number = conn.execute(
            text("SELECT coalesce(max(version),0)+1 FROM app.offer_versions WHERE offer_id=:id"),
            {"id": target},
        ).scalar_one()
        result = insert(
            conn,
            "offer_versions",
            {
                **values,
                "offer_id": target,
                "version": number,
                "content_hash": canonical_hash(body.model_dump(mode="json")),
            },
        )
        for identifier in proofs:
            insert(
                conn,
                "offer_proofs",
                {"offer_version_id": result["id"], "document_version_id": identifier},
            )
        update(conn, "offers", target, version, {"name": parent["name"]})
        return result

    @staticmethod
    def lead(
        conn: Connection, data: dict[str, Any], target: UUID | None, version: int | None
    ) -> dict[str, Any]:
        values = LeadInput.model_validate(data).model_dump()
        for field, table in [
            ("account_id", "accounts"),
            ("person_id", "people"),
            ("contact_point_id", "contact_points"),
            ("icp_version_id", "icp_versions"),
            ("offer_version_id", "offer_versions"),
        ]:
            if values[field]:
                record = get(conn, table, values[field])
                if record.get("status", "active") != "active":
                    raise BusinessError("IDENTITY_HOLD", 423)
        account = get(conn, "accounts", values["account_id"])
        require_source(conn, account["source_id"], ["account.identity"])
        return insert(
            conn,
            "leads",
            {
                **values,
                "state": "discovered",
                "owner_principal_id": conn.execute(
                    text("SELECT app.current_principal_id()")
                ).scalar_one(),
            },
        )

    @staticmethod
    def score(
        conn: Connection, data: dict[str, Any], target: UUID | None, version: int | None
    ) -> dict[str, Any]:
        body = ScoreInput.model_validate(data)
        evaluated = evaluate(conn, body)
        result, input_hash, used, lead = (
            evaluated.result,
            evaluated.input_hash,
            evaluated.used,
            evaluated.lead,
        )
        prior = rows(
            conn,
            "SELECT * FROM app.scores WHERE subject_id=:subject AND icp_version_id=:icp AND policy_hash=:policy AND input_hash=:input",
            {
                "subject": body.subject_id,
                "icp": body.icp_version_id,
                "policy": result.policy_hash,
                "input": input_hash,
            },
        )
        if prior:
            return prior[0]
        record = insert(
            conn,
            "scores",
            {
                "subject_id": body.subject_id,
                "icp_version_id": body.icp_version_id,
                "policy_hash": result.policy_hash,
                "known_points": result.known_points,
                "maximum_known_points": result.maximum_known_points,
                "missing_keys": list(result.missing_keys),
                "hard_exclusions": list(result.hard_exclusions),
                "priority": result.priority,
                "input_hash": input_hash,
                "dependency_version": 1,
            },
        )
        for item in evaluated.evidence:
            insert(
                conn, "score_input_evidence", {"score_id": record["id"], "evidence_id": item["id"]}
            )
        for item in evaluated.signals:
            insert(
                conn,
                "score_signals",
                {
                    "score_id": record["id"],
                    "signal_id": item["id"],
                    "signal_version": item["record_version"],
                    "status": item["status"],
                    "expires_at": item["expires_at"],
                    "evidence_id": item["evidence_id"],
                },
            )
        for key, component_result in result.components.items():
            row = insert(
                conn,
                "score_components",
                {
                    "score_id": record["id"],
                    "component": key,
                    "points": component_result.points,
                    "max_points": component_result.max_points,
                    "reason_codes": list(component_result.reasons),
                },
            )
            for identifier in sorted({item["id"] for item in used[key]}, key=str):
                insert(
                    conn,
                    "score_evidence",
                    {"score_component_id": row["id"], "evidence_id": identifier},
                )
        if lead:
            update(
                conn, "leads", lead["id"], lead["record_version"], {"latest_score_id": record["id"]}
            )
        return record

    @staticmethod
    def accept_signal(
        conn: Connection, data: dict[str, Any], target: UUID | None, version: int | None
    ) -> dict[str, Any]:
        assert target is not None and version is not None
        reason = ReasonInput.model_validate(data).reason
        signal = get(conn, "signals", target, lock=True)
        if (
            signal["status"] != "candidate"
            or signal["expires_at"] <= datetime.now(UTC)
            or invalid_reasons(conn, get(conn, "evidence", signal["evidence_id"]))
        ):
            raise BusinessError("UNSUPPORTED_OBSERVATION", 423)
        return update(
            conn, "signals", target, version, {"status": "accepted", "acceptance_reason": reason}
        )

    @staticmethod
    def begin_research(
        conn: Connection, data: dict[str, Any], target: UUID | None, version: int | None
    ) -> dict[str, Any]:
        assert target is not None and version is not None
        reason = ReasonInput.model_validate(data).reason
        lead = get(conn, "leads", target, lock=True)
        if lead["state"] != "discovered":
            raise BusinessError("INVALID_TRANSITION")
        account = get(conn, "accounts", lead["account_id"])
        if account["status"] != "active":
            raise BusinessError("IDENTITY_HOLD", 423)
        require_source(conn, account["source_id"], ["account.identity"])
        return update(
            conn, "leads", target, version, {"state": "researching", "reason_code": reason}
        )

    @staticmethod
    def complete_research(
        conn: Connection, data: dict[str, Any], target: UUID | None, version: int | None
    ) -> dict[str, Any]:
        assert target is not None and version is not None
        lead = get(conn, "leads", target, lock=True)
        if lead["state"] != "researching":
            raise BusinessError("INVALID_TRANSITION")
        evidence = [
            get(conn, "evidence", identifier)
            for identifier in ResearchInput.model_validate(data).evidence_ids
        ]
        if any(
            item["subject_id"] != lead["account_id"]
            or set(invalid_reasons(conn, item)) - {"unknown_value"}
            for item in evidence
        ):
            raise BusinessError("STALE_EVIDENCE", 423)
        policy = get(conn, "icp_versions", lead["icp_version_id"])
        if not set(policy["criteria"]["required_evidence_keys"]) <= {
            item["fact_key"] for item in evidence
        }:
            raise BusinessError("REQUIRED_EVIDENCE_MISSING", 422)
        return update(
            conn,
            "leads",
            target,
            version,
            {"state": "researched", "reason_code": "manual_research_recorded"},
        )

    @staticmethod
    def disqualify(
        conn: Connection, data: dict[str, Any], target: UUID | None, version: int | None
    ) -> dict[str, Any]:
        assert target is not None and version is not None
        reason = ReasonInput.model_validate(data).reason
        lead = get(conn, "leads", target, lock=True)
        if lead["state"] not in {"discovered", "researched"} or not lead["latest_score_id"]:
            raise BusinessError("INVALID_TRANSITION")
        score = get(conn, "scores", lead["latest_score_id"])
        if not score["hard_exclusions"]:
            raise BusinessError("EXCLUSION_REQUIRED", 423)
        if not current_input(conn, score):
            raise BusinessError("STALE_EVIDENCE", 423)
        return update(
            conn, "leads", target, version, {"state": "disqualified", "reason_code": reason}
        )

    @staticmethod
    def archive(
        conn: Connection, data: dict[str, Any], target: UUID | None, version: int | None
    ) -> dict[str, Any]:
        assert target is not None and version is not None
        reason = ReasonInput.model_validate(data).reason
        lead = get(conn, "leads", target, lock=True)
        if lead["state"] == "archived":
            raise BusinessError("INVALID_TRANSITION")
        return update(conn, "leads", target, version, {"state": "archived", "reason_code": reason})

    @staticmethod
    def correction(
        conn: Connection, data: dict[str, Any], target: UUID | None, version: int | None
    ) -> dict[str, Any]:
        assert target is not None and version is not None
        account = get(conn, "accounts", target, lock=True)
        if account["status"] == "merged":
            raise BusinessError("IDENTITY_HOLD", 423)
        body = CorrectionInput.model_validate(data)
        for identifier in body.evidence_ids:
            item = get(conn, "evidence", identifier)
            if item["subject_id"] != target or invalid_reasons(conn, item):
                raise BusinessError("UNSUPPORTED_CORRECTION", 422)
        values = body.model_dump(mode="json", exclude_unset=True)
        values.pop("evidence_ids")
        values.pop("reason")
        if not values:
            raise BusinessError("EMPTY_CORRECTION", 422)
        result = insert(
            conn,
            "identity_conflicts",
            {"subject_id": target, "proposed_changes": values, "reason": body.reason},
        )
        for identifier in body.evidence_ids:
            insert(
                conn,
                "identity_conflict_evidence",
                {"conflict_id": result["id"], "evidence_id": identifier},
            )
        update(conn, "accounts", target, version, {"status": "identity_hold"})
        return result

    def document(
        self, conn: Connection, data: dict[str, Any], target: UUID | None, version: int | None
    ) -> dict[str, Any]:
        body = DocumentInput.model_validate(data)
        try:
            title, content = self.documents.read_fixture(body.external_file_id)
        except ValueError:
            raise BusinessError("UNKNOWN_LOCAL_DOCUMENT", 422) from None
        return self.register_document(
            conn, body.external_file_id, title, body.classification, content
        )

    def register_document(
        self, conn: Connection, reference: str, title: str, classification: str, content: bytes
    ) -> dict[str, Any]:
        snapshot = self.documents.save_snapshot(content)
        document = insert(
            conn,
            "documents",
            {
                "store_key": "fake_local",
                "external_file_id": reference,
                "title": title,
                "classification": classification,
                "state": "active",
            },
        )
        insert(
            conn,
            "document_versions",
            {
                "document_id": document["id"],
                "version": 1,
                "export_sha256": snapshot,
                "media_type": "application/json"
                if reference.startswith("merge:")
                else "text/plain",
                "byte_count": len(content),
                "snapshot_file_id": snapshot,
                "observed_at": datetime.now(UTC),
                "is_final": True,
            },
        )
        insert(
            conn,
            "document_grants",
            {
                "document_id": document["id"],
                "principal_id": document["created_by"],
                "permission": "read",
            },
        )
        return document

    @staticmethod
    def decision(
        conn: Connection, subject: UUID, kind: str, reason: str, evidence_ids: list[UUID]
    ) -> dict[str, Any]:
        actor = conn.execute(text("SELECT app.current_principal_id()")).scalar_one()
        result = insert(
            conn,
            "decisions",
            {
                "subject_id": subject,
                "decision_type": kind,
                "outcome": "approve",
                "summary": reason,
                "alternatives": ["retain separate identities"],
                "decided_by": actor,
            },
        )
        for identifier in evidence_ids:
            get(conn, "evidence", identifier)
            insert(
                conn, "decision_evidence", {"decision_id": result["id"], "evidence_id": identifier}
            )
        return result

    def merge(
        self, conn: Connection, data: dict[str, Any], target: UUID | None, version: int | None
    ) -> dict[str, Any]:
        body = MergeInput.model_validate(data)
        resources = [
            get(conn, "resources", identifier) for identifier in [body.survivor_id, body.retired_id]
        ]
        if (
            body.survivor_id == body.retired_id
            or resources[0]["resource_type"] != resources[1]["resource_type"]
            or resources[0]["resource_type"] not in {"account", "person"}
        ):
            raise BusinessError("TYPE_MISMATCH")
        table = "accounts" if resources[0]["resource_type"] == "account" else "people"
        locked = {
            identifier: get(conn, table, identifier, lock=True)
            for identifier in sorted([body.survivor_id, body.retired_id], key=str)
        }
        survivor, retired = locked[body.survivor_id], locked[body.retired_id]
        if (
            survivor["record_version"] != body.survivor_version
            or retired["record_version"] != body.retired_version
        ):
            raise BusinessError("VERSION_CONFLICT")
        if any(item["status"] not in {"active", "identity_hold"} for item in [survivor, retired]):
            raise BusinessError("IDENTITY_HOLD", 423)
        if rows(
            conn,
            f"SELECT id FROM app.{table} WHERE merged_into_id=ANY(:ids)",
            {"ids": [body.survivor_id, body.retired_id]},
        ):
            raise BusinessError("MERGE_CHAIN_REVIEW_REQUIRED", 423)
        for identifier in body.evidence_ids:
            evidence = get(conn, "evidence", identifier)
            if evidence["subject_id"] not in locked or invalid_reasons(conn, evidence):
                raise BusinessError("UNSUPPORTED_MERGE", 422)
        snapshots = {
            "schema_version": 1,
            "type": resources[0]["resource_type"],
            "survivor": survivor,
            "retired": retired,
        }
        # Relationships retain their original UUIDs. Snapshot their IDs for review.
        field = "account_id" if table == "accounts" else "person_id"
        snapshots["relationships"] = {
            name: rows(
                conn,
                f"SELECT id,{field},record_version FROM app.{name} WHERE {field}=ANY(:ids) ORDER BY id",
                {"ids": [body.survivor_id, body.retired_id]},
            )
            for name in ["employments", "contact_points", "leads"]
        }
        document = self.register_document(
            conn,
            "merge:" + str(uuid4()),
            "Synthetic identity review snapshot",
            "restricted",
            json.dumps(snapshots, sort_keys=True, default=str).encode(),
        )
        decision = self.decision(
            conn, body.retired_id, "identity_merge", body.reason, body.evidence_ids
        )
        update(
            conn,
            table,
            body.retired_id,
            body.retired_version,
            {"status": "merged", "merged_into_id": body.survivor_id},
        )
        update(conn, table, body.survivor_id, body.survivor_version, {"status": "identity_hold"})
        self.hold_contacts(conn, field, [body.survivor_id, body.retired_id])
        return insert(
            conn,
            "identity_merges",
            {
                "survivor_id": body.survivor_id,
                "retired_id": body.retired_id,
                "before_document_id": document["id"],
                "decision_id": decision["id"],
                "retired_version": body.retired_version + 1,
                "survivor_version": body.survivor_version + 1,
            },
        )

    @staticmethod
    def hold_contacts(conn: Connection, field: str, identities: list[UUID]) -> None:
        for contact in rows(
            conn, f"SELECT * FROM app.contact_points WHERE {field}=ANY(:ids)", {"ids": identities}
        ):
            update(
                conn,
                "contact_points",
                contact["id"],
                contact["record_version"],
                {"status": "conflicted"},
            )
            insert(
                conn,
                "suppressions",
                {
                    "contact_point_id": contact["id"],
                    "scope": "workspace",
                    "reason": "identity_conflict",
                    "state": "review_required",
                },
            )

    def reverse(
        self, conn: Connection, data: dict[str, Any], target: UUID | None, version: int | None
    ) -> dict[str, Any]:
        assert target is not None
        if version != 1:
            raise BusinessError("VERSION_CONFLICT")
        body = ReversalInput.model_validate(data)
        merge = get(conn, "identity_merges", target)
        resource = get(conn, "resources", merge["retired_id"])
        table = "accounts" if resource["resource_type"] == "account" else "people"
        locked = {
            identifier: get(conn, table, identifier, lock=True)
            for identifier in sorted([merge["survivor_id"], merge["retired_id"]], key=str)
        }
        survivor, retired = locked[merge["survivor_id"]], locked[merge["retired_id"]]
        if (
            survivor["record_version"] != body.survivor_version
            or retired["record_version"] != body.retired_version
            or retired["record_version"] != merge["retired_version"]
            or survivor["record_version"] != merge["survivor_version"]
        ):
            raise BusinessError("VERSION_CONFLICT")
        for identifier in body.evidence_ids:
            evidence = get(conn, "evidence", identifier)
            if evidence["subject_id"] not in locked or invalid_reasons(conn, evidence):
                raise BusinessError("UNSUPPORTED_REVERSAL", 422)
        if not document_allowed(conn, merge["before_document_id"]):
            raise BusinessError("NOT_FOUND", 404)
        snapshot = rows(
            conn,
            "SELECT snapshot_file_id FROM app.document_versions WHERE document_id=:id",
            {"id": merge["before_document_id"]},
        )[0]
        before = json.loads(self.documents.read_snapshot(snapshot["snapshot_file_id"]))
        if before["schema_version"] != 1 or before["retired"]["id"] != str(retired["id"]):
            raise BusinessError("SNAPSHOT_MISMATCH", 423)
        decision = self.decision(
            conn, retired["id"], "identity_reversal", body.reason, body.evidence_ids
        )
        result = insert(
            conn,
            "identity_merge_reversals",
            {"merge_id": target, "decision_id": decision["id"], "reason": body.reason},
        )
        update(
            conn,
            table,
            retired["id"],
            retired["record_version"],
            {"status": "identity_hold", "merged_into_id": None},
        )
        update(conn, table, survivor["id"], survivor["record_version"], {"status": "identity_hold"})
        return result
