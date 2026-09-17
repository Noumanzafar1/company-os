"""Retain complete score dependencies and enforce Signal observation chronology."""

from alembic import op

revision = "0005_phase3_review_fixes"
down_revision = "0004_core_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE app.scores ADD dependency_version smallint NOT NULL DEFAULT 0 CHECK(dependency_version IN (0,1))"
    )
    op.execute(
        "ALTER TABLE app.signals ADD acceptance_reason text CHECK(length(acceptance_reason) BETWEEN 1 AND 20000)"
    )
    for table, fields in {
        "score_input_evidence": "evidence_id uuid NOT NULL, UNIQUE(workspace_id,score_id,evidence_id)",
        "score_signals": "signal_id uuid NOT NULL, evidence_id uuid NOT NULL, signal_version bigint NOT NULL CHECK(signal_version>0), status text NOT NULL CHECK(status='accepted'), expires_at timestamptz NOT NULL, UNIQUE(workspace_id,score_id,signal_id)",
    }.items():
        op.execute(
            f"CREATE TABLE app.{table}(id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES app.workspaces(id), created_at timestamptz NOT NULL DEFAULT now(), schema_version smallint NOT NULL DEFAULT 1 CHECK(schema_version>0), created_by uuid NOT NULL REFERENCES app.principals(id), score_id uuid NOT NULL, {fields}, UNIQUE(workspace_id,id))"
        )
        refs = {"score_id": "scores", "evidence_id": "evidence"}
        if table == "score_signals":
            refs["signal_id"] = "signals"
        for column, parent in refs.items():
            op.execute(
                f"ALTER TABLE app.{table} ADD FOREIGN KEY(workspace_id,{column}) REFERENCES app.{parent}(workspace_id,id) DEFERRABLE INITIALLY IMMEDIATE"
            )
            op.execute(f"CREATE INDEX {table}_{column}_fk ON app.{table}(workspace_id,{column})")
        op.execute(f"CREATE INDEX {table}_chronology ON app.{table}(workspace_id,created_at,id)")
        op.execute(
            f"ALTER TABLE app.{table} ENABLE ROW LEVEL SECURITY; ALTER TABLE app.{table} FORCE ROW LEVEL SECURITY"
        )
        op.execute(
            f"CREATE POLICY tenant_scope ON app.{table} TO company_api USING(workspace_id=app.current_workspace_id() AND app.has_active_membership(app.current_principal_id(),workspace_id)) WITH CHECK(workspace_id=app.current_workspace_id() AND app.has_active_membership(app.current_principal_id(),workspace_id))"
        )
        op.execute(f"GRANT SELECT,INSERT ON app.{table} TO company_api")
        op.execute(
            f"CREATE TRIGGER core_actor BEFORE INSERT ON app.{table} FOR EACH ROW EXECUTE FUNCTION app.core_actor_guard()"
        )
        op.execute(
            f"CREATE TRIGGER core_immutable BEFORE UPDATE OR DELETE ON app.{table} FOR EACH ROW EXECUTE FUNCTION app.core_row_guard('append')"
        )
    op.execute("""
    CREATE FUNCTION app.review_score_support_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    DECLARE subject uuid; kind text;
    BEGIN
      SELECT s.subject_id,r.resource_type INTO subject,kind FROM app.scores s JOIN app.resources r ON r.workspace_id=s.workspace_id AND r.id=s.subject_id WHERE s.workspace_id=NEW.workspace_id AND s.id=NEW.score_id AND s.dependency_version=1;
      IF kind='lead' THEN SELECT account_id INTO subject FROM app.leads WHERE workspace_id=NEW.workspace_id AND id=subject; END IF;
      IF NOT EXISTS(SELECT 1 FROM app.evidence WHERE workspace_id=NEW.workspace_id AND id=NEW.evidence_id AND subject_id=subject) THEN
        RAISE EXCEPTION 'Score input subject mismatch' USING ERRCODE='23514';
      END IF;
      IF TG_TABLE_NAME='score_signals' THEN
        IF NOT EXISTS(SELECT 1 FROM app.signals WHERE workspace_id=NEW.workspace_id AND id=NEW.signal_id AND subject_id=subject AND evidence_id=NEW.evidence_id AND record_version=NEW.signal_version AND status=NEW.status AND expires_at=NEW.expires_at AND expires_at>now()) THEN
          RAISE EXCEPTION 'Score signal dependency mismatch' USING ERRCODE='23514';
        END IF;
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER review_score_support BEFORE INSERT ON app.score_input_evidence FOR EACH ROW EXECUTE FUNCTION app.review_score_support_guard();
    CREATE TRIGGER review_score_support BEFORE INSERT ON app.score_signals FOR EACH ROW EXECUTE FUNCTION app.review_score_support_guard();
    CREATE FUNCTION app.review_signal_time_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    BEGIN
      IF NEW.observed_at>statement_timestamp() OR NOT EXISTS(SELECT 1 FROM app.evidence WHERE workspace_id=NEW.workspace_id AND id=NEW.evidence_id AND observed_at<=NEW.observed_at) THEN
        RAISE EXCEPTION 'Invalid signal observation chronology' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER review_signal_time BEFORE INSERT OR UPDATE ON app.signals FOR EACH ROW EXECUTE FUNCTION app.review_signal_time_guard();
    REVOKE ALL ON FUNCTION app.review_score_support_guard(),app.review_signal_time_guard() FROM PUBLIC;
    """)


def downgrade() -> None:
    op.execute("""
    DROP TRIGGER review_signal_time ON app.signals;
    DROP FUNCTION app.review_signal_time_guard();
    DROP TABLE app.score_signals;
    DROP TABLE app.score_input_evidence;
    DROP FUNCTION app.review_score_support_guard();
    ALTER TABLE app.signals DROP COLUMN acceptance_reason;
    ALTER TABLE app.scores DROP COLUMN dependency_version;
    """)
