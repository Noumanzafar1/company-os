"""Phase 3 sourced business state; no jobs, effects or approval runtime."""

from alembic import op

revision = "0003_core_business_state"
down_revision = "0002_identity_guards"
branch_labels = None
depends_on = None

# Frozen migration-local definitions. Never import mutable application models.
TABLES = {
    "resources": (
        False,
        "resource_type text NOT NULL CHECK(resource_type IN ('account','person','lead','document')), deleted_at timestamptz, UNIQUE(workspace_id,id,resource_type)",
    ),
    "documents": (
        False,
        "store_key text NOT NULL CHECK(store_key='fake_local'), external_file_id varchar(500) NOT NULL, title varchar(500) NOT NULL, classification text NOT NULL CHECK(classification IN ('public','internal','client_confidential','restricted')), permission_epoch bigint NOT NULL DEFAULT 1 CHECK(permission_epoch>0), state text NOT NULL CHECK(state IN ('active','revoked','deleted')), UNIQUE(workspace_id,store_key,external_file_id)",
    ),
    "document_versions": (
        True,
        "document_id uuid NOT NULL, version integer NOT NULL CHECK(version>0), provider_revision varchar(500), export_sha256 char(64) NOT NULL CHECK(export_sha256 ~ '^[a-f0-9]{64}$'), media_type varchar(100) NOT NULL, byte_count bigint NOT NULL CHECK(byte_count>=0), snapshot_file_id varchar(500) NOT NULL, observed_at timestamptz NOT NULL, is_final boolean NOT NULL, UNIQUE(workspace_id,document_id,version), UNIQUE(workspace_id,document_id,export_sha256)",
    ),
    "document_grants": (
        False,
        "document_id uuid NOT NULL, principal_id uuid NOT NULL REFERENCES app.principals(id), permission text NOT NULL CHECK(permission IN ('read','edit')), expires_at timestamptz, UNIQUE(workspace_id,document_id,principal_id,permission)",
    ),
    "data_sources": (
        False,
        "name varchar(500) NOT NULL, source_type text NOT NULL CHECK(source_type IN ('public_page','client_import','human')), rights_document_version_id uuid, rights_status text NOT NULL CHECK(rights_status IN ('pending','approved','expired','revoked')), permitted_purposes text[] NOT NULL, allowed_fields text[] NOT NULL, retention_days integer CHECK(retention_days>0), expires_at timestamptz, CHECK(rights_status<>'approved' OR (rights_document_version_id IS NOT NULL AND cardinality(permitted_purposes)>0 AND cardinality(allowed_fields)>0)), UNIQUE(workspace_id,name)",
    ),
    "accounts": (
        False,
        "display_name varchar(500) NOT NULL, legal_name varchar(500), primary_domain varchar(253), identity_discriminator varchar(500) NOT NULL, parent_id uuid, country_code char(2), industry_code varchar(100), size_min integer CHECK(size_min>=0), size_max integer CHECK(size_max>=0), status text NOT NULL CHECK(status IN ('active','identity_hold','merged','archived')), merged_into_id uuid, source_id uuid NOT NULL, CHECK(size_min IS NULL OR size_max IS NULL OR size_max>=size_min), CHECK((status='merged')=(merged_into_id IS NOT NULL)), CHECK(parent_id IS DISTINCT FROM id AND merged_into_id IS DISTINCT FROM id)",
    ),
    "people": (
        False,
        "display_name varchar(500) NOT NULL, given_name varchar(500), family_name varchar(500), status text NOT NULL CHECK(status IN ('active','identity_hold','merged','archived')), merged_into_id uuid, source_id uuid NOT NULL, CHECK((status='merged')=(merged_into_id IS NOT NULL)), CHECK(merged_into_id IS DISTINCT FROM id)",
    ),
    "evidence": (
        True,
        "subject_id uuid NOT NULL, source_id uuid NOT NULL, source_url text, provider_record_id varchar(500), fact_key varchar(100) NOT NULL, fact_type text NOT NULL CHECK(fact_type IN ('string','integer','decimal','date','boolean','unknown')), string_value varchar(20000), integer_value bigint, decimal_value numeric(20,6), date_value date, boolean_value boolean, unit varchar(100), excerpt varchar(20000), document_version_id uuid, observed_at timestamptz NOT NULL, event_at timestamptz, expires_at timestamptz NOT NULL, content_sha256 char(64) NOT NULL CHECK(content_sha256 ~ '^[a-f0-9]{64}$'), entity_match text NOT NULL CHECK(entity_match IN ('confirmed','uncertain','rejected')), fact_kind text NOT NULL CHECK(fact_kind IN ('observed','reported','inferred')), supersedes_id uuid, CHECK(source_url IS NOT NULL OR provider_record_id IS NOT NULL OR document_version_id IS NOT NULL), CHECK(expires_at>=observed_at), CHECK((fact_type='unknown' AND num_nonnulls(string_value,integer_value,decimal_value,date_value,boolean_value)=0) OR (num_nonnulls(string_value,integer_value,decimal_value,date_value,boolean_value)=1 AND ((fact_type='string' AND string_value IS NOT NULL) OR (fact_type='integer' AND integer_value IS NOT NULL) OR (fact_type='decimal' AND decimal_value IS NOT NULL) OR (fact_type='date' AND date_value IS NOT NULL) OR (fact_type='boolean' AND boolean_value IS NOT NULL)))), UNIQUE(workspace_id,source_id,subject_id,fact_key,content_sha256,observed_at)",
    ),
    "evidence_retractions": (
        True,
        "evidence_id uuid NOT NULL, reason varchar(500) NOT NULL, replacement_id uuid, CHECK(replacement_id IS DISTINCT FROM evidence_id), UNIQUE(workspace_id,evidence_id)",
    ),
    "employments": (
        False,
        "person_id uuid NOT NULL, account_id uuid NOT NULL, title varchar(500) NOT NULL, start_date date, end_date date, observed_at timestamptz NOT NULL, evidence_id uuid NOT NULL, status text NOT NULL CHECK(status IN ('current','former','uncertain')), CHECK(end_date IS NULL OR start_date IS NULL OR end_date>=start_date), CHECK(status<>'current' OR end_date IS NULL), UNIQUE NULLS NOT DISTINCT(workspace_id,person_id,account_id,title,start_date)",
    ),
    "contact_points": (
        False,
        "person_id uuid, account_id uuid, kind text NOT NULL CHECK(kind IN ('email','phone','url')), value_original varchar(2000) NOT NULL, value_normalized varchar(2000) NOT NULL, match_key varchar(2000) NOT NULL, status text NOT NULL CHECK(status IN ('active','invalid','conflicted','archived')), source_id uuid NOT NULL, CHECK(person_id IS NOT NULL OR account_id IS NOT NULL), UNIQUE(workspace_id,kind,match_key)",
    ),
    "signals": (
        False,
        "subject_id uuid NOT NULL, kind text NOT NULL CHECK(kind IN ('hiring','funding','technology_change','expansion','stated_need','other')), event_at timestamptz, observed_at timestamptz NOT NULL, expires_at timestamptz NOT NULL, evidence_id uuid NOT NULL, relevance_summary varchar(20000) NOT NULL, status text NOT NULL CHECK(status IN ('candidate','accepted','expired','rejected')), fingerprint char(64) NOT NULL, CHECK(expires_at>=observed_at), UNIQUE(workspace_id,fingerprint)",
    ),
    "icps": (
        False,
        "name varchar(500) NOT NULL, active_version_id uuid CHECK(active_version_id IS NULL), UNIQUE(workspace_id,name)",
    ),
    "icp_versions": (
        True,
        "icp_id uuid NOT NULL, version integer NOT NULL CHECK(version>0), criteria jsonb NOT NULL CHECK(jsonb_typeof(criteria)='object'), exclusions jsonb NOT NULL CHECK(jsonb_typeof(exclusions)='object'), score_policy jsonb NOT NULL CHECK(jsonb_typeof(score_policy)='object'), content_hash char(64) NOT NULL CHECK(content_hash ~ '^[a-f0-9]{64}$'), UNIQUE(workspace_id,icp_id,version)",
    ),
    "icp_excluded_accounts": (
        True,
        "icp_version_id uuid NOT NULL, account_id uuid NOT NULL, UNIQUE(workspace_id,icp_version_id,account_id)",
    ),
    "offers": (
        False,
        "name varchar(500) NOT NULL, active_version_id uuid CHECK(active_version_id IS NULL), UNIQUE(workspace_id,name)",
    ),
    "offer_versions": (
        True,
        "offer_id uuid NOT NULL, version integer NOT NULL CHECK(version>0), scope varchar(20000) NOT NULL, exclusions varchar(20000) NOT NULL, rate_card_document_version_id uuid, capacity_limit integer NOT NULL CHECK(capacity_limit>=0), content_hash char(64) NOT NULL CHECK(content_hash ~ '^[a-f0-9]{64}$'), UNIQUE(workspace_id,offer_id,version)",
    ),
    "offer_proofs": (
        True,
        "offer_version_id uuid NOT NULL, document_version_id uuid NOT NULL, UNIQUE(workspace_id,offer_version_id,document_version_id)",
    ),
    "leads": (
        False,
        "account_id uuid NOT NULL, person_id uuid, contact_point_id uuid, offer_version_id uuid NOT NULL, icp_version_id uuid NOT NULL, state text NOT NULL CHECK(state IN ('discovered','researching','researched','eligible','engaged','qualified','disqualified','archived')), reason_code varchar(500), latest_score_id uuid, owner_principal_id uuid NOT NULL REFERENCES app.principals(id)",
    ),
    "scores": (
        True,
        "subject_id uuid NOT NULL, icp_version_id uuid NOT NULL, policy_hash char(64) NOT NULL, known_points numeric(6,2) NOT NULL CHECK(known_points BETWEEN 0 AND 100), maximum_known_points numeric(6,2) NOT NULL CHECK(maximum_known_points BETWEEN 0 AND 100), missing_keys text[] NOT NULL, hard_exclusions text[] NOT NULL, priority text NOT NULL CHECK(priority IN ('excluded','priority','review','below_review')), computed_at timestamptz NOT NULL DEFAULT now(), input_hash char(64) NOT NULL, CHECK(known_points<=maximum_known_points), CHECK((cardinality(hard_exclusions)>0)=(priority='excluded')), UNIQUE(workspace_id,subject_id,icp_version_id,policy_hash,input_hash)",
    ),
    "score_components": (
        True,
        "score_id uuid NOT NULL, component text NOT NULL CHECK(component IN ('fit','economics','trigger','role','freshness')), points numeric(6,2), max_points numeric(6,2) NOT NULL, reason_codes text[] NOT NULL, CHECK(points IS NULL OR points BETWEEN 0 AND max_points), CHECK(max_points=CASE component WHEN 'fit' THEN 30 WHEN 'economics' THEN 20 WHEN 'trigger' THEN 20 ELSE 15 END), UNIQUE(workspace_id,score_id,component)",
    ),
    "score_evidence": (
        True,
        "score_component_id uuid NOT NULL, evidence_id uuid NOT NULL, UNIQUE(workspace_id,score_component_id,evidence_id)",
    ),
    "decisions": (
        True,
        "subject_id uuid NOT NULL, decision_type text NOT NULL CHECK(decision_type IN ('identity_merge','identity_reversal','knowledge_review')), outcome text NOT NULL CHECK(outcome IN ('approve','reject','revise','record')), summary varchar(20000) NOT NULL, alternatives text[] NOT NULL, decided_by uuid NOT NULL REFERENCES app.principals(id), decided_at timestamptz NOT NULL DEFAULT now(), review_at timestamptz, CHECK(decided_by=created_by)",
    ),
    "decision_evidence": (
        True,
        "decision_id uuid NOT NULL, evidence_id uuid NOT NULL, UNIQUE(workspace_id,decision_id,evidence_id)",
    ),
    "identity_conflicts": (
        True,
        "subject_id uuid NOT NULL, proposed_changes jsonb NOT NULL CHECK(jsonb_typeof(proposed_changes)='object'), reason varchar(500) NOT NULL",
    ),
    "identity_conflict_evidence": (
        True,
        "conflict_id uuid NOT NULL, evidence_id uuid NOT NULL, UNIQUE(workspace_id,conflict_id,evidence_id)",
    ),
    "identity_merges": (
        True,
        "survivor_id uuid NOT NULL, retired_id uuid NOT NULL, before_document_id uuid NOT NULL, decision_id uuid NOT NULL, retired_version bigint NOT NULL, survivor_version bigint NOT NULL, CHECK(survivor_id<>retired_id), UNIQUE(workspace_id,decision_id)",
    ),
    "identity_merge_reversals": (
        True,
        "merge_id uuid NOT NULL, decision_id uuid NOT NULL, reason varchar(500) NOT NULL, UNIQUE(workspace_id,merge_id), UNIQUE(workspace_id,decision_id)",
    ),
    "permission_assessments": (
        True,
        "contact_point_id uuid NOT NULL, purpose varchar(100) NOT NULL, channel text NOT NULL CHECK(channel='email'), result text NOT NULL CHECK(result IN ('unknown','ineligible')), reason_codes text[] NOT NULL, expires_at timestamptz NOT NULL",
    ),
    "suppressions": (
        True,
        "contact_point_id uuid NOT NULL, scope text NOT NULL CHECK(scope='workspace'), reason text NOT NULL CHECK(reason IN ('identity_conflict','manual','privacy')), received_at timestamptz NOT NULL DEFAULT now(), state text NOT NULL CHECK(state IN ('active','review_required'))",
    ),
    "knowledge_items": (
        False,
        "document_version_id uuid NOT NULL, kind text NOT NULL CHECK(kind IN ('strategy','sop','policy','proof','rate_card','template','report')), approved_decision_id uuid NOT NULL, valid_from timestamptz NOT NULL, review_due_at timestamptz NOT NULL, status text NOT NULL CHECK(status IN ('approved','stale','revoked')), CHECK(review_due_at>valid_from)",
    ),
    "knowledge_chunks": (
        True,
        "knowledge_id uuid NOT NULL, ordinal integer NOT NULL CHECK(ordinal>=0), text varchar(20000) NOT NULL, search_vector tsvector GENERATED ALWAYS AS (to_tsvector('english'::regconfig,text)) STORED, hash char(64) NOT NULL, UNIQUE(workspace_id,knowledge_id,ordinal)",
    ),
    "command_receipts": (
        True,
        "actor_id uuid NOT NULL REFERENCES app.principals(id), command_type varchar(100) NOT NULL, idempotency_key varchar(128) NOT NULL, request_hash char(64) NOT NULL, result_id uuid NOT NULL, result_version bigint, UNIQUE(workspace_id,actor_id,command_type,idempotency_key), CHECK(actor_id=created_by)",
    ),
}

REFS = {
    "document_versions": {"document_id": "documents"},
    "document_grants": {"document_id": "documents"},
    "data_sources": {"rights_document_version_id": "document_versions"},
    "accounts": {
        "parent_id": "accounts",
        "merged_into_id": "accounts",
        "source_id": "data_sources",
    },
    "people": {"merged_into_id": "people", "source_id": "data_sources"},
    "evidence": {
        "subject_id": "resources",
        "source_id": "data_sources",
        "document_version_id": "document_versions",
        "supersedes_id": "evidence",
    },
    "evidence_retractions": {"evidence_id": "evidence", "replacement_id": "evidence"},
    "employments": {"person_id": "people", "account_id": "accounts", "evidence_id": "evidence"},
    "contact_points": {
        "person_id": "people",
        "account_id": "accounts",
        "source_id": "data_sources",
    },
    "signals": {"subject_id": "resources", "evidence_id": "evidence"},
    "icp_versions": {"icp_id": "icps"},
    "icp_excluded_accounts": {"icp_version_id": "icp_versions", "account_id": "accounts"},
    "offer_versions": {"offer_id": "offers", "rate_card_document_version_id": "document_versions"},
    "offer_proofs": {
        "offer_version_id": "offer_versions",
        "document_version_id": "document_versions",
    },
    "leads": {
        "account_id": "accounts",
        "person_id": "people",
        "contact_point_id": "contact_points",
        "offer_version_id": "offer_versions",
        "icp_version_id": "icp_versions",
        "latest_score_id": "scores",
    },
    "scores": {"subject_id": "resources", "icp_version_id": "icp_versions"},
    "score_components": {"score_id": "scores"},
    "score_evidence": {"score_component_id": "score_components", "evidence_id": "evidence"},
    "decisions": {"subject_id": "resources"},
    "decision_evidence": {"decision_id": "decisions", "evidence_id": "evidence"},
    "identity_conflicts": {"subject_id": "resources"},
    "identity_conflict_evidence": {"conflict_id": "identity_conflicts", "evidence_id": "evidence"},
    "identity_merges": {
        "survivor_id": "resources",
        "retired_id": "resources",
        "before_document_id": "documents",
        "decision_id": "decisions",
    },
    "identity_merge_reversals": {"merge_id": "identity_merges", "decision_id": "decisions"},
    "permission_assessments": {"contact_point_id": "contact_points"},
    "suppressions": {"contact_point_id": "contact_points"},
    "knowledge_items": {
        "document_version_id": "document_versions",
        "approved_decision_id": "decisions",
    },
    "knowledge_chunks": {"knowledge_id": "knowledge_items"},
}
RESOURCE_TABLES = {
    "account": "accounts",
    "person": "people",
    "lead": "leads",
    "document": "documents",
}


def upgrade() -> None:
    op.execute("ALTER TABLE app.role_permissions DROP CONSTRAINT role_permissions_permission_check")
    op.execute(
        "ALTER TABLE app.role_permissions ADD CONSTRAINT role_permissions_permission_check CHECK(permission IN ('workspace.read','system.read','approval.grant','business.read','business.write','identity.review'))"
    )
    for table, (append_only, fields) in TABLES.items():
        mutable = (
            ""
            if append_only
            else ", updated_at timestamptz NOT NULL DEFAULT now(), record_version bigint NOT NULL DEFAULT 1 CHECK(record_version>0), updated_by uuid NOT NULL REFERENCES app.principals(id)"
        )
        op.execute(
            f"CREATE TABLE app.{table} (id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES app.workspaces(id), created_at timestamptz NOT NULL DEFAULT now(), schema_version smallint NOT NULL DEFAULT 1 CHECK(schema_version>0), created_by uuid NOT NULL REFERENCES app.principals(id){mutable}, {fields}, UNIQUE(workspace_id,id))"
        )
        stamp = "created_at" if append_only else "updated_at"
        op.execute(f"CREATE INDEX {table}_chronology ON app.{table}(workspace_id,{stamp},id)")
        op.execute(
            f"ALTER TABLE app.{table} ENABLE ROW LEVEL SECURITY; ALTER TABLE app.{table} FORCE ROW LEVEL SECURITY"
        )
        op.execute(
            f"CREATE POLICY tenant_scope ON app.{table} TO company_api USING(workspace_id=app.current_workspace_id() AND app.has_active_membership(app.current_principal_id(),workspace_id)) WITH CHECK(workspace_id=app.current_workspace_id() AND created_by=app.current_principal_id() AND app.has_active_membership(app.current_principal_id(),workspace_id))"
        )
        op.execute(
            f"GRANT SELECT,INSERT{'' if append_only else ',UPDATE'} ON app.{table} TO company_api"
        )
    for table, refs in REFS.items():
        for column, target in refs.items():
            op.execute(
                f"ALTER TABLE app.{table} ADD FOREIGN KEY(workspace_id,{column}) REFERENCES app.{target}(workspace_id,id) DEFERRABLE INITIALLY IMMEDIATE"
            )
            op.execute(f"CREATE INDEX {table}_{column}_fk ON app.{table}(workspace_id,{column})")
    for kind, table in RESOURCE_TABLES.items():
        op.execute(
            f"ALTER TABLE app.{table} ADD resource_type text GENERATED ALWAYS AS ('{kind}'::text) STORED"
        )
        op.execute(
            f"ALTER TABLE app.{table} ADD FOREIGN KEY(workspace_id,id,resource_type) REFERENCES app.resources(workspace_id,id,resource_type) DEFERRABLE INITIALLY DEFERRED"
        )
    op.execute("""
    CREATE UNIQUE INDEX accounts_identity ON app.accounts(workspace_id,primary_domain,identity_discriminator) WHERE primary_domain IS NOT NULL AND status<>'merged';
    CREATE INDEX accounts_domain ON app.accounts(workspace_id,primary_domain);
    CREATE INDEX accounts_status ON app.accounts(workspace_id,status);
    CREATE INDEX accounts_search ON app.accounts(workspace_id,lower(display_name));
    CREATE INDEX people_search ON app.people(workspace_id,lower(display_name));
    CREATE INDEX sources_expiry ON app.data_sources(workspace_id,rights_status,expires_at);
    CREATE INDEX evidence_current ON app.evidence(workspace_id,subject_id,fact_key,expires_at);
    CREATE INDEX signals_expiry ON app.signals(workspace_id,status,expires_at);
    CREATE INDEX leads_state ON app.leads(workspace_id,state);
    CREATE UNIQUE INDEX leads_identity ON app.leads(workspace_id,account_id,person_id,offer_version_id,icp_version_id) NULLS NOT DISTINCT WHERE state<>'archived';
    CREATE INDEX knowledge_fts ON app.knowledge_chunks USING gin(search_vector);

    CREATE FUNCTION app.core_row_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    BEGIN
      IF TG_OP='DELETE' OR TG_ARGV[0]='append' THEN
        RAISE EXCEPTION 'Immutable history' USING ERRCODE='23514';
      END IF;
      IF NEW.id<>OLD.id OR NEW.workspace_id<>OLD.workspace_id OR NEW.created_by<>OLD.created_by OR NEW.created_at<>OLD.created_at OR NEW.schema_version<>OLD.schema_version THEN
        RAISE EXCEPTION 'Immutable identity' USING ERRCODE='23514';
      END IF;
      IF NEW.record_version<>OLD.record_version+1 THEN
        RAISE EXCEPTION 'Expected next version' USING ERRCODE='40001';
      END IF;
      IF current_user='company_api' AND NEW.updated_by<>app.current_principal_id() THEN
        RAISE EXCEPTION 'Actor mismatch' USING ERRCODE='23514';
      END IF;
      NEW.updated_at=clock_timestamp();
      RETURN NEW;
    END $$;

    CREATE FUNCTION app.core_resource_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    DECLARE found boolean;
    BEGIN
      CASE NEW.resource_type
        WHEN 'account' THEN SELECT EXISTS(SELECT 1 FROM app.accounts WHERE workspace_id=NEW.workspace_id AND id=NEW.id) INTO found;
        WHEN 'person' THEN SELECT EXISTS(SELECT 1 FROM app.people WHERE workspace_id=NEW.workspace_id AND id=NEW.id) INTO found;
        WHEN 'lead' THEN SELECT EXISTS(SELECT 1 FROM app.leads WHERE workspace_id=NEW.workspace_id AND id=NEW.id) INTO found;
        WHEN 'document' THEN SELECT EXISTS(SELECT 1 FROM app.documents WHERE workspace_id=NEW.workspace_id AND id=NEW.id) INTO found;
        ELSE found=false;
      END CASE;
      IF NOT found THEN RAISE EXCEPTION 'Missing typed aggregate' USING ERRCODE='23514'; END IF;
      RETURN NULL;
    END $$;
    CREATE CONSTRAINT TRIGGER typed_resource AFTER INSERT OR UPDATE ON app.resources DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION app.core_resource_guard();

    CREATE FUNCTION app.core_identity_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    DECLARE cycle_found boolean;
    BEGIN
      -- Serialize graph edits within each workspace, including concurrent inserts.
      PERFORM pg_advisory_xact_lock(hashtextextended(NEW.workspace_id::text, 31));
      IF TG_TABLE_NAME='accounts' THEN
        WITH RECURSIVE ancestors(id,parent_id,path) AS (
          SELECT id,parent_id,ARRAY[id] FROM app.accounts WHERE workspace_id=NEW.workspace_id AND id=NEW.parent_id
          UNION ALL SELECT a.id,a.parent_id,x.path||a.id FROM app.accounts a JOIN ancestors x ON a.id=x.parent_id
          WHERE a.workspace_id=NEW.workspace_id AND NOT a.id=ANY(x.path)
        ) SELECT EXISTS(SELECT 1 FROM ancestors WHERE id=NEW.id) INTO cycle_found;
        IF cycle_found THEN RAISE EXCEPTION 'Parent cycle' USING ERRCODE='23514'; END IF;
      END IF;
      IF TG_OP='UPDATE' THEN
        IF OLD.status='merged' AND (NEW.status<>OLD.status OR NEW.merged_into_id IS DISTINCT FROM OLD.merged_into_id) AND NOT EXISTS(
          SELECT 1 FROM app.identity_merges m JOIN app.identity_merge_reversals r ON r.workspace_id=m.workspace_id AND r.merge_id=m.id
          WHERE m.workspace_id=NEW.workspace_id AND m.retired_id=NEW.id AND m.retired_version=OLD.record_version
        ) THEN RAISE EXCEPTION 'Reviewed reversal required' USING ERRCODE='23514'; END IF;
      END IF;
      IF NEW.merged_into_id IS NOT NULL THEN
        IF TG_TABLE_NAME='accounts' THEN
          SELECT EXISTS(SELECT 1 FROM app.accounts WHERE workspace_id=NEW.workspace_id AND id=NEW.merged_into_id AND status IN ('active','identity_hold')) INTO cycle_found;
        ELSE
          SELECT EXISTS(SELECT 1 FROM app.people WHERE workspace_id=NEW.workspace_id AND id=NEW.merged_into_id AND status IN ('active','identity_hold')) INTO cycle_found;
        END IF;
        IF NOT cycle_found THEN RAISE EXCEPTION 'Invalid merge survivor' USING ERRCODE='23514'; END IF;
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER identity_graph BEFORE INSERT OR UPDATE ON app.accounts FOR EACH ROW EXECUTE FUNCTION app.core_identity_guard();
    CREATE TRIGGER identity_graph BEFORE INSERT OR UPDATE ON app.people FOR EACH ROW EXECUTE FUNCTION app.core_identity_guard();

    CREATE FUNCTION app.core_relationship_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    BEGIN
      IF TG_TABLE_NAME='contact_points' THEN
        IF TG_OP='UPDATE' THEN
          IF NEW.value_original<>OLD.value_original OR NEW.value_normalized<>OLD.value_normalized OR NEW.match_key<>OLD.match_key OR NEW.kind<>OLD.kind THEN
            RAISE EXCEPTION 'Contact replacement required' USING ERRCODE='23514';
          END IF;
        END IF;
        IF NEW.person_id IS NOT NULL AND NEW.account_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM app.employments WHERE workspace_id=NEW.workspace_id AND person_id=NEW.person_id AND account_id=NEW.account_id) THEN
          RAISE EXCEPTION 'Contact owner mismatch' USING ERRCODE='23514';
        END IF;
      ELSIF TG_TABLE_NAME='employments' THEN
        IF NOT EXISTS(SELECT 1 FROM app.evidence WHERE workspace_id=NEW.workspace_id AND id=NEW.evidence_id AND subject_id=NEW.person_id AND fact_key='employment.account_id' AND fact_type='string' AND string_value=NEW.account_id::text) THEN
          RAISE EXCEPTION 'Employment support mismatch' USING ERRCODE='23514';
        END IF;
      ELSIF TG_TABLE_NAME='signals' THEN
        IF NOT EXISTS(SELECT 1 FROM app.evidence WHERE workspace_id=NEW.workspace_id AND id=NEW.evidence_id AND subject_id=NEW.subject_id AND fact_kind='observed') THEN
          RAISE EXCEPTION 'Signal must reference observed subject evidence' USING ERRCODE='23514';
        END IF;
      ELSIF TG_TABLE_NAME='leads' THEN
        IF NEW.contact_point_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM app.contact_points WHERE workspace_id=NEW.workspace_id AND id=NEW.contact_point_id AND (account_id=NEW.account_id OR (account_id IS NULL AND person_id=NEW.person_id)) AND (NEW.person_id IS NULL OR person_id=NEW.person_id)) THEN
          RAISE EXCEPTION 'Lead contact mismatch' USING ERRCODE='23514';
        END IF;
        IF NEW.person_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM app.employments WHERE workspace_id=NEW.workspace_id AND person_id=NEW.person_id AND account_id=NEW.account_id) THEN
          RAISE EXCEPTION 'Lead employment mismatch' USING ERRCODE='23514';
        END IF;
        IF NEW.state IN ('eligible','engaged','qualified') THEN
          RAISE EXCEPTION 'Later-phase transition' USING ERRCODE='23514';
        END IF;
      ELSIF TG_TABLE_NAME='identity_merges' THEN
        IF NOT EXISTS(SELECT 1 FROM app.resources s JOIN app.resources r ON r.workspace_id=s.workspace_id AND r.resource_type=s.resource_type WHERE s.workspace_id=NEW.workspace_id AND s.id=NEW.survivor_id AND r.id=NEW.retired_id AND s.resource_type IN ('account','person')) THEN
          RAISE EXCEPTION 'Merge type mismatch' USING ERRCODE='23514';
        END IF;
      END IF;
      RETURN NEW;
    END $$;
    """)
    for table, (append_only, _) in TABLES.items():
        op.execute(
            f"CREATE TRIGGER core_immutable BEFORE UPDATE OR DELETE ON app.{table} FOR EACH ROW EXECUTE FUNCTION app.core_row_guard('{'append' if append_only else 'mutable'}')"
        )
    for table in ["contact_points", "employments", "signals", "leads", "identity_merges"]:
        op.execute(
            f"CREATE TRIGGER relationship_integrity BEFORE INSERT OR UPDATE ON app.{table} FOR EACH ROW EXECUTE FUNCTION app.core_relationship_guard()"
        )
    op.execute(
        "REVOKE ALL ON FUNCTION app.core_row_guard(),app.core_resource_guard(),app.core_identity_guard(),app.core_relationship_guard() FROM PUBLIC"
    )


def downgrade() -> None:
    # Explicit operator rollback of synthetic Phase 3 data, retaining Phase 2 schema.
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE app.{table} CASCADE")
    for function in [
        "core_row_guard",
        "core_resource_guard",
        "core_identity_guard",
        "core_relationship_guard",
    ]:
        op.execute(f"DROP FUNCTION app.{function}()")
    op.execute(
        "DELETE FROM app.role_permissions WHERE permission IN ('business.read','business.write','identity.review')"
    )
    op.execute("ALTER TABLE app.role_permissions DROP CONSTRAINT role_permissions_permission_check")
    op.execute(
        "ALTER TABLE app.role_permissions ADD CONSTRAINT role_permissions_permission_check CHECK(permission IN ('workspace.read','system.read','approval.grant'))"
    )
