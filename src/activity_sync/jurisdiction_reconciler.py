from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List

import pandas as pd
from loguru import logger
from rapidfuzz import fuzz, process

from activity_sync.openai_service import OpenAIService
from activity_sync.settings import Settings
from activity_sync.supabase_repository import SupabaseRepository
from activity_sync.text_utils import (
    clean_int,
    clean_text,
    length_ratio_ok,
    normalize_activity_name,
    row_hash,
)


class JurisdictionReconciler:
    """
    Reconciles fetched jurisdiction activities against the consolidated base data.

    Final threshold logic:

    1. vector_score >= 0.88
       Already Exists
       No add / no draft

    2. 0.70 <= vector_score < 0.88
       Ambiguous range
       Send to OpenAI
       If OpenAI confirms same_activity with confidence >= 0.85:
           Already Exists
       Else:
           New activity
           Assign new Activity Code
           Status = Draft-Review

    3. vector_score < 0.70
       New activity
       Assign new Activity Code
       Status = Draft
       OpenAI is not used
    """

    def __init__(
        self,
        settings: Settings,
        repository: SupabaseRepository,
        openai_service: OpenAIService,
    ):
        self.settings = settings
        self.repository = repository
        self.openai_service = openai_service

    def load_fetched_csv(self, path: str) -> pd.DataFrame:
        df = pd.read_csv(path, encoding="utf-8-sig")

        required = [
            "jurisdiction",
            "official_code",
            "activity_name",
            "activity_name_normalized",
        ]

        missing = [col for col in required if col not in df.columns]

        if missing:
            raise ValueError(
                f"Fetched CSV missing columns: {missing}. "
                f"Available columns: {list(df.columns)}"
            )

        df["jurisdiction"] = df["jurisdiction"].apply(clean_text)
        df["official_code"] = df["official_code"].apply(clean_text)
        df["activity_name"] = df["activity_name"].apply(clean_text)
        df["activity_name_normalized"] = df["activity_name_normalized"].apply(clean_text)

        optional_columns = [
            "official_category",
            "official_status",
            "official_risk_rating",
            "official_industry_risk",
            "official_dnfbp",
            "official_third_party",
            "official_when",
            "official_notes",
            "source_type",
            "raw_payload",
            "source_row_hash",
        ]

        for col in optional_columns:
            if col not in df.columns:
                df[col] = ""

            df[col] = df[col].apply(clean_text)

        df = df[df["activity_name"] != ""].copy()

        df.drop_duplicates(
            subset=["jurisdiction", "official_code", "activity_name"],
            inplace=True,
        )

        return df

    def base_choice_map(self, base_df: pd.DataFrame) -> Dict[int, str]:
        choices: Dict[int, str] = {}

        for _, row in base_df.iterrows():
            activity_id = int(row["id"])
            normalized_name = clean_text(row.get("activity_name_normalized", ""))

            if normalized_name:
                choices[activity_id] = normalized_name

        return choices

    def find_exact_existing(
        self,
        base_df: pd.DataFrame,
        normalized_name: str,
    ) -> pd.DataFrame:
        return base_df[
            base_df["activity_name_normalized"] == normalized_name
        ].copy()

    def find_best_fuzzy(
        self,
        normalized_name: str,
        choices: Dict[int, str],
    ):
        return process.extract(
            normalized_name,
            choices,
            scorer=fuzz.token_sort_ratio,
            limit=3,
        )

    def build_activity_semantic_text(self, activity_name: str) -> str:
        """
        Semantic search is based only on Activity Name.
        """
        return activity_name

    def safe_json_for_excel(self, value: Any) -> str:
        if value is None:
            return ""

        try:
            return json.dumps(value, ensure_ascii=False)
        except TypeError:
            return str(value)

    def log_entity_processing(
        self,
        status: str,
        activity_name: str,
        official_code: str,
        action: str,
        matched_with: str = "",
        code: int | None = None,
        vector_score: float | None = None,
    ) -> None:
        icon = {
            "Already Exists": "✓",
            "Auto-Updated": "↻",
            "Draft": "✎",
            "Draft-Review": "⚠",
        }.get(status, "•")

        code_text = f"Code: {code}" if code is not None else "Code: N/A"
        score_text = (
            f" [Vector Score: {vector_score:.4f}]"
            if vector_score is not None
            else ""
        )

        if matched_with:
            logger.info(
                f"{icon} [{status}] {activity_name} "
                f"(Official: {official_code}) | Action: {action} "
                f"→ {matched_with} ({code_text}){score_text}"
            )
        else:
            logger.info(
                f"{icon} [{status}] {activity_name} "
                f"(Official: {official_code}) | Action: {action} "
                f"({code_text}){score_text}"
            )

    def create_new_activity_row(
        self,
        jurisdiction: str,
        fetched_row: pd.Series,
        assigned_activity_code: int,
        status: str,
        match_type: str,
        matched_with: str,
        match_score: float,
        reason: str,
        openai_decision: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        activity_name = clean_text(fetched_row.get("activity_name", ""))
        official_code = clean_text(fetched_row.get("official_code", ""))

        normalized = normalize_activity_name(activity_name)
        semantic_text = self.build_activity_semantic_text(activity_name)

        embedding = self.openai_service.create_embedding(semantic_text)

        return {
            "activity_name": activity_name,
            "activity_name_normalized": normalized,
            "activity_code": assigned_activity_code,
            "division": None,
            "activity_group": None,
            "class_code": None,
            "isic_description": "",
            "activity_description": "",
            "jurisdiction": jurisdiction,
            "official_code": official_code,
            "official_category": clean_text(fetched_row.get("official_category", "")),
            "official_status": clean_text(fetched_row.get("official_status", "")),
            "official_risk_rating": clean_text(
                fetched_row.get("official_risk_rating", "")
            ),
            "official_industry_risk": clean_text(
                fetched_row.get("official_industry_risk", "")
            ),
            "official_dnfbp": clean_text(fetched_row.get("official_dnfbp", "")),
            "official_third_party": clean_text(
                fetched_row.get("official_third_party", "")
            ),
            "official_when": clean_text(fetched_row.get("official_when", "")),
            "official_notes": clean_text(fetched_row.get("official_notes", "")),
            "semantic_text": semantic_text,
            "embedding": embedding,
            "status": status,
            "match_type": match_type,
            "matched_with": matched_with,
            "match_score": round(float(match_score), 4),
            "reason": reason,
            "openai_decision": openai_decision,
            "source": "jurisdiction_fetch",
            "raw_payload": fetched_row.to_dict(),
            "source_row_hash": row_hash(
                [
                    "jurisdiction_fetch",
                    jurisdiction,
                    official_code,
                    activity_name,
                    assigned_activity_code,
                ]
            ),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "last_checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def run(
        self,
        jurisdiction: str,
        fetched_csv_path: str,
        apply_updates: bool = False,
        fuzzy_auto_threshold: float = 95.0,
        vector_same_threshold: float = 0.88,
        vector_review_threshold: float = 0.70,
        openai_same_confidence_threshold: float = 0.85,
        use_openai: bool = True,
    ) -> None:
        fetched_df = self.load_fetched_csv(fetched_csv_path)

        fetched_df = fetched_df[
            fetched_df["jurisdiction"].str.lower() == jurisdiction.lower()
        ].copy()

        base_df = self.repository.fetch_activities_by_jurisdiction(jurisdiction)

        if base_df.empty:
            raise RuntimeError(
                f"No base activities found in Supabase for jurisdiction: {jurisdiction}. "
                f"Run: uv run python scripts/load_consolidated.py --jurisdiction {jurisdiction}"
            )

        choices = self.base_choice_map(base_df)

        logger.info(f"Fetched rows for {jurisdiction}: {len(fetched_df)}")
        logger.info(f"Base rows for {jurisdiction}: {len(base_df)}")
        logger.info(
            f"Thresholds: vector_same_threshold={vector_same_threshold}, "
            f"vector_review_threshold={vector_review_threshold}, "
            f"openai_same_confidence_threshold={openai_same_confidence_threshold}"
        )

        if fetched_df.empty:
            logger.warning(f"No fetched rows found for jurisdiction={jurisdiction}")
            return

        if apply_updates:
            self.repository.upsert_fetched_activities(fetched_df.to_dict("records"))

        already_exists: List[Dict[str, Any]] = []
        auto_updated: List[Dict[str, Any]] = []
        new_draft: List[Dict[str, Any]] = []
        draft_review: List[Dict[str, Any]] = []

        # Important:
        # Get next code once and increment locally.
        # This prevents assigning the same new Activity Code repeatedly in dry run.
        next_activity_code = self.repository.get_next_activity_code()

        for _, fetched_row in fetched_df.iterrows():
            activity_name = clean_text(fetched_row.get("activity_name", ""))
            official_code = clean_text(fetched_row.get("official_code", ""))
            normalized = normalize_activity_name(activity_name)

            if not activity_name or not normalized:
                continue

            # ----------------------------------------------------
            # CASE 1A: Exact normalized activity name exists
            # ----------------------------------------------------
            exact = self.find_exact_existing(base_df, normalized)

            if not exact.empty:
                matched = exact.iloc[0]
                matched_code = clean_int(matched["activity_code"])

                already_exists.append(
                    {
                        "activity_name": activity_name,
                        "official_code": official_code,
                        "matched_activity_name": matched["activity_name"],
                        "activity_code": matched_code,
                        "status": "Already Exists",
                        "action": "No add / no draft",
                    }
                )

                self.log_entity_processing(
                    status="Already Exists",
                    activity_name=activity_name,
                    official_code=official_code,
                    action="No add / no draft",
                    matched_with=clean_text(matched["activity_name"]),
                    code=matched_code,
                )

                continue

            # ----------------------------------------------------
            # CASE 2: Spelling / grammar correction
            # ----------------------------------------------------
            fuzzy_matches = self.find_best_fuzzy(normalized, choices)

            fuzzy_candidate = None
            fuzzy_score = 0.0
            second_score = 0.0

            if fuzzy_matches:
                _, fuzzy_score, fuzzy_id = fuzzy_matches[0]
                second_score = (
                    float(fuzzy_matches[1][1]) if len(fuzzy_matches) > 1 else 0.0
                )
                fuzzy_candidate = base_df[base_df["id"] == fuzzy_id].iloc[0]

            if fuzzy_candidate is not None:
                candidate_name = clean_text(fuzzy_candidate["activity_name"])
                candidate_code = clean_int(fuzzy_candidate["activity_code"])
                score_gap = float(fuzzy_score) - float(second_score)

                is_safe_spelling = (
                    float(fuzzy_score) >= fuzzy_auto_threshold
                    and score_gap >= 3
                    and length_ratio_ok(activity_name, candidate_name)
                )

                openai_decision = None

                if not is_safe_spelling and use_openai and float(fuzzy_score) >= 88:
                    openai_decision = self.openai_service.decide_activity_relation(
                        fetched_activity={
                            "activity_name": activity_name,
                            "official_code": official_code,
                            "jurisdiction": jurisdiction,
                        },
                        candidate_activity={
                            "activity_name": candidate_name,
                            "activity_code": candidate_code,
                            "jurisdiction": jurisdiction,
                        },
                    )

                    is_safe_spelling = (
                        openai_decision.get("relation") == "spelling_correction"
                        and float(openai_decision.get("confidence", 0) or 0) >= 0.85
                    )

                if is_safe_spelling:
                    if apply_updates:
                        self.repository.update_activity_name(
                            activity_id=int(fuzzy_candidate["id"]),
                            new_activity_name=activity_name,
                            match_type="Spelling/Grammar Correction",
                            matched_with=activity_name,
                            match_score=float(fuzzy_score),
                            reason=(
                                "Official fetched activity name is spelling/formatting "
                                "correction of existing base activity."
                            ),
                            openai_decision=openai_decision,
                        )

                    auto_updated.append(
                        {
                            "activity_name": activity_name,
                            "official_code": official_code,
                            "matched_activity_name": candidate_name,
                            "activity_code": candidate_code,
                            "fuzzy_score": round(float(fuzzy_score), 4),
                            "status": (
                                "Auto-Updated"
                                if apply_updates
                                else "Auto-Update Candidate"
                            ),
                            "action": "Update base activity name",
                            "openai_decision": self.safe_json_for_excel(openai_decision),
                        }
                    )

                    self.log_entity_processing(
                        status="Auto-Updated",
                        activity_name=activity_name,
                        official_code=official_code,
                        action=(
                            "Updated spelling/formatting correction"
                            if apply_updates
                            else "Auto-update candidate"
                        ),
                        matched_with=candidate_name,
                        code=candidate_code,
                    )

                    continue

            # ----------------------------------------------------
            # CASE 1B / CASE 3: Semantic search on Activity Name only
            # ----------------------------------------------------
            query_embedding = self.openai_service.create_embedding(activity_name)

            vector_matches = self.repository.match_activity_by_name(
                query_embedding=query_embedding,
                jurisdiction=jurisdiction,
                match_count=5,
            )

            best_match = vector_matches[0] if vector_matches else None
            vector_score = (
                float(best_match.get("similarity", 0) or 0)
                if best_match
                else 0.0
            )

            matched_name = (
                clean_text(best_match.get("activity_name", ""))
                if best_match
                else ""
            )
            matched_code = (
                clean_int(best_match.get("activity_code"))
                if best_match
                else None
            )
            matched_id = best_match.get("id") if best_match else None

            # ----------------------------------------------------
            # THRESHOLD RULE 1:
            # vector_score >= 0.88
            # Already Exists
            # ----------------------------------------------------
            if best_match and vector_score >= vector_same_threshold:
                already_exists.append(
                    {
                        "activity_name": activity_name,
                        "official_code": official_code,
                        "matched_activity_name": matched_name,
                        "activity_code": matched_code,
                        "vector_score": round(vector_score, 4),
                        "status": "Semantic Match Exists",
                        "action": "No add / no draft",
                    }
                )

                self.log_entity_processing(
                    status="Already Exists",
                    activity_name=activity_name,
                    official_code=official_code,
                    action="No add / no draft",
                    matched_with=matched_name,
                    code=matched_code,
                    vector_score=vector_score,
                )

                continue

            # ----------------------------------------------------
            # THRESHOLD RULE 2:
            # 0.70 <= vector_score < 0.88
            # OpenAI check
            # If OpenAI says same_activity with confidence >= 0.85:
            # Already Exists
            # Else:
            # Draft-Review with new Activity Code
            # ----------------------------------------------------
            openai_decision = None

            is_medium_score = (
                best_match is not None
                and vector_score >= vector_review_threshold
                and vector_score < vector_same_threshold
            )

            if is_medium_score and use_openai:
                openai_decision = self.openai_service.decide_activity_relation(
                    fetched_activity={
                        "activity_name": activity_name,
                        "official_code": official_code,
                        "jurisdiction": jurisdiction,
                    },
                    candidate_activity={
                        "activity_name": matched_name,
                        "activity_code": matched_code,
                        "jurisdiction": jurisdiction,
                    },
                )

                is_openai_confirmed_existing = (
                    openai_decision.get("relation") == "same_activity"
                    and float(openai_decision.get("confidence", 0) or 0)
                    >= openai_same_confidence_threshold
                )

                if is_openai_confirmed_existing:
                    already_exists.append(
                        {
                            "activity_name": activity_name,
                            "official_code": official_code,
                            "matched_activity_name": matched_name,
                            "activity_code": matched_code,
                            "vector_score": round(vector_score, 4),
                            "status": "OpenAI Confirmed Exists",
                            "action": "No add / no draft",
                            "openai_decision": self.safe_json_for_excel(
                                openai_decision
                            ),
                        }
                    )

                    self.log_entity_processing(
                        status="Already Exists",
                        activity_name=activity_name,
                        official_code=official_code,
                        action="OpenAI confirmed same activity; no add / no draft",
                        matched_with=matched_name,
                        code=matched_code,
                        vector_score=vector_score,
                    )

                    continue

            # ----------------------------------------------------
            # CASE 3:
            # If not already exists, assign new Activity Code.
            # Medium score -> Draft-Review
            # Low score -> Draft
            # ----------------------------------------------------
            assigned_code = next_activity_code
            next_activity_code += 1

            if is_medium_score:
                status = "Draft-Review"
                match_type = "OpenAI Review / Possible Semantic Match - New Code Assigned"

                if use_openai:
                    reason = (
                        "Vector score is between 0.70 and 0.88. "
                        "OpenAI did not confirm this as an existing activity, "
                        "so a new Activity Code is assigned and manual review is required."
                    )
                else:
                    reason = (
                        "Vector score is between 0.70 and 0.88. "
                        "OpenAI is disabled, so a new Activity Code is assigned "
                        "and manual review is required."
                    )

                target_list = draft_review
                action_log = "Going to Draft-Review after OpenAI/medium-score check"

            else:
                status = "Draft"
                match_type = "New Activity - New Code Assigned"
                reason = (
                    "Vector score is below 0.70. "
                    "No reliable existing activity was found. "
                    "New Activity Code assigned."
                )

                target_list = new_draft
                action_log = "Going to Draft as new activity"

            new_row = self.create_new_activity_row(
                jurisdiction=jurisdiction,
                fetched_row=fetched_row,
                assigned_activity_code=assigned_code,
                status=status,
                match_type=match_type,
                matched_with=matched_name,
                match_score=vector_score,
                reason=reason,
                openai_decision=openai_decision,
            )

            if apply_updates:
                self.repository.upsert_activities([new_row])

            result = {
                "activity_name": activity_name,
                "official_code": official_code,
                "assigned_activity_code": assigned_code,
                "nearest_candidate": matched_name,
                "nearest_candidate_code": matched_code,
                "vector_score": round(vector_score, 4),
                "status": status,
                "match_type": match_type,
                "reason": reason,
                "openai_decision": self.safe_json_for_excel(openai_decision),
            }

            target_list.append(result)

            self.log_entity_processing(
                status=status,
                activity_name=activity_name,
                official_code=official_code,
                action=action_log,
                matched_with=matched_name,
                code=assigned_code,
                vector_score=vector_score,
            )

            if apply_updates:
                self.repository.insert_reconciliation_result(
                    {
                        "jurisdiction": jurisdiction,
                        "fetched_activity_name": activity_name,
                        "fetched_official_code": official_code,
                        "matched_activity_id": matched_id,
                        "matched_activity_name": matched_name,
                        "matched_activity_code": matched_code,
                        "assigned_activity_code": assigned_code,
                        "fuzzy_score": round(float(fuzzy_score), 4),
                        "vector_score": round(vector_score, 4),
                        "action_type": match_type,
                        "status": status,
                        "reason": reason,
                        "openai_decision": openai_decision,
                    }
                )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        audit_path = (
            self.settings.output_dir
            / f"{jurisdiction.lower()}_reconciliation_audit_{timestamp}.xlsx"
        )

        with pd.ExcelWriter(audit_path, engine="openpyxl") as writer:
            pd.DataFrame(already_exists).to_excel(
                writer,
                sheet_name="Already Exists",
                index=False,
            )

            pd.DataFrame(auto_updated).to_excel(
                writer,
                sheet_name="Auto Updated",
                index=False,
            )

            pd.DataFrame(new_draft).to_excel(
                writer,
                sheet_name="Draft",
                index=False,
            )

            pd.DataFrame(draft_review).to_excel(
                writer,
                sheet_name="Draft Review",
                index=False,
            )

            summary = pd.DataFrame(
                [
                    {
                        "jurisdiction": jurisdiction,
                        "apply_updates": apply_updates,
                        "fetched_rows": len(fetched_df),
                        "base_rows": len(base_df),
                        "already_exists": len(already_exists),
                        "auto_updated": len(auto_updated),
                        "draft": len(new_draft),
                        "draft_review": len(draft_review),
                        "vector_same_threshold": vector_same_threshold,
                        "vector_review_threshold": vector_review_threshold,
                        "openai_same_confidence_threshold": openai_same_confidence_threshold,
                        "threshold_rule_1": "vector_score >= 0.88 => Already Exists",
                        "threshold_rule_2": "0.70 <= vector_score < 0.88 => OpenAI check; if not confirmed, Draft-Review",
                        "threshold_rule_3": "vector_score < 0.70 => Draft as new activity",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                ]
            )

            summary.to_excel(writer, sheet_name="Summary", index=False)

        logger.success(f"Audit report saved: {audit_path}")
        logger.success(f"Already exists: {len(already_exists)}")
        logger.success(f"Auto updated: {len(auto_updated)}")
        logger.success(f"Draft: {len(new_draft)}")
        logger.success(f"Draft-Review: {len(draft_review)}")