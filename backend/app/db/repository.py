from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from typing import Any

from app.db.connection import connection_scope
from app.models.schemas import AnalysisRunRequest, IngestionRunRequest

ALLOWED_PREFIXES = ("SELECT", "WITH")
BLOCKED_KEYWORDS = ("DROP", "INSERT", "UPDATE", "DELETE", "PRAGMA", "ATTACH", "EXEC")
TABLE_WHITELIST: dict[str, dict[str, Any]] = {
    "entity_dictionary": {
        "description": "Canonical terms, aliases, and category metadata.",
        "search_columns": ["canonical_term", "entity_type", "hb_category", "origin_market", "description"],
        "order_columns": ["canonical_term", "entity_type", "hb_category", "origin_market"],
        "default_order": "canonical_term",
        "updated_column": None,
    },
    "search_trends": {
        "description": "Search breakout signals by keyword and region.",
        "search_columns": ["keyword", "geo", "llm_category", "llm_subcategory", "source_batch_id"],
        "order_columns": [
            "keyword",
            "geo",
            "snapshot_date",
            "wow_delta",
            "index_value",
            "processed_at",
            "last_updated",
            "source_batch_id",
        ],
        "default_order": "snapshot_date",
        "updated_column": "last_updated",
    },
    "social_posts": {
        "description": "RedNote social posts enriched with entities and sentiment.",
        "search_columns": ["id", "platform", "region", "title", "content_text", "seed_keyword", "source_batch_id"],
        "order_columns": [
            "id",
            "post_date",
            "liked_count",
            "comment_count",
            "share_count",
            "engagement_score",
            "positivity_score",
            "processed_at",
            "fetched_at",
            "source_batch_id",
        ],
        "default_order": "fetched_at",
        "updated_column": "fetched_at",
    },
    "sales_data": {
        "description": "Seeded sales snapshots and weekly velocity metrics.",
        "search_columns": ["sku", "product_name", "brand", "ingredient_tags", "category", "region", "source_batch_id"],
        "order_columns": ["sku", "brand", "category", "region", "week_start", "units_sold", "revenue", "wow_velocity"],
        "default_order": "week_start",
        "updated_column": "week_start",
    },
    "trend_exploration": {
        "description": "Persisted trend reports and evidence summaries.",
        "search_columns": ["trend_id", "canonical_term", "entity_type", "hb_category", "market", "confidence_tier", "status"],
        "order_columns": [
            "trend_id",
            "canonical_term",
            "entity_type",
            "hb_category",
            "virality_score",
            "confidence_tier",
            "market",
            "analysis_date",
            "status",
        ],
        "default_order": "analysis_date",
        "updated_column": "analysis_date",
    },
    "ingestion_runs": {
        "description": "Extraction job requests, status, and batch metadata.",
        "search_columns": ["id", "status", "market", "category", "source_batch_id", "error_message"],
        "order_columns": ["id", "status", "market", "category", "recent_days", "started_at", "completed_at", "source_batch_id"],
        "default_order": "started_at",
        "updated_column": "started_at",
    },
    "analysis_runs": {
        "description": "LangGraph analysis job status and stored reports.",
        "search_columns": ["id", "status", "market", "category", "analysis_mode", "error_message"],
        "order_columns": ["id", "status", "market", "category", "recency_days", "analysis_mode", "started_at", "completed_at"],
        "default_order": "started_at",
        "updated_column": "started_at",
    },
    "tiktok_photo_posts": {
        "description": "TikTok photo search results stored from TikHub.",
        "search_columns": ["id", "search_keyword", "description", "share_url", "source_batch_id"],
        "order_columns": [
            "id",
            "search_keyword",
            "create_time",
            "create_time_unix",
            "is_ad",
            "fetched_at",
            "source_batch_id",
        ],
        "default_order": "fetched_at",
        "updated_column": "fetched_at",
    },
    "instagram_posts": {
        "description": "Instagram hashtag posts stored from TikHub.",
        "search_columns": ["post_id", "search_keyword", "code", "username", "full_name", "caption", "location_name", "source_batch_id"],
        "order_columns": [
            "post_id",
            "search_keyword",
            "code",
            "username",
            "likes",
            "comments",
            "views",
            "created_at",
            "fetched_at",
            "source_batch_id",
        ],
        "default_order": "fetched_at",
        "updated_column": "fetched_at",
    },
}


def json_dumps(value: Any) -> str:
    return json.dumps(value, default=str)


def json_loads(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def safe_sql_execute(connection: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    normalized = query.strip().upper()
    if not any(normalized.startswith(prefix) for prefix in ALLOWED_PREFIXES):
        raise ValueError("Only SELECT queries are permitted")
    tokens = set(re.findall(r"\b[A-Z_]+\b", normalized))
    if any(keyword in tokens for keyword in BLOCKED_KEYWORDS):
        raise ValueError("Query contains blocked keyword")
    cursor = connection.execute(query, params)
    return [dict(row) for row in cursor.fetchall()]


def _get_table_metadata(table_name: str) -> dict[str, Any]:
    metadata = TABLE_WHITELIST.get(table_name)
    if metadata is None:
        raise ValueError(f"Unsupported table: {table_name}")
    return metadata


def _build_search_clause(metadata: dict[str, Any], search: str | None, column: str | None) -> tuple[str, list[Any]]:
    if not search:
        return "", []

    params: list[Any] = []
    if column:
        if column not in metadata["search_columns"]:
            raise ValueError(f"Unsupported search column: {column}")
        return f" WHERE CAST({column} AS TEXT) LIKE ?", [f"%{search}%"]

    clauses = [f"CAST({name} AS TEXT) LIKE ?" for name in metadata["search_columns"]]
    params.extend([f"%{search}%"] * len(clauses))
    return f" WHERE ({' OR '.join(clauses)})", params


def list_database_tables() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with connection_scope() as connection:
        for table_name, metadata in TABLE_WHITELIST.items():
            updated_column = metadata["updated_column"]
            updated_expr = f"MAX({updated_column})" if updated_column else "NULL"
            summary = safe_sql_execute(
                connection,
                f"SELECT COUNT(*) AS row_count, {updated_expr} AS last_updated FROM {table_name}",
            )[0]
            rows.append(
                {
                    "name": table_name,
                    "description": metadata["description"],
                    "row_count": summary["row_count"] or 0,
                    "last_updated": summary["last_updated"],
                }
            )
    return rows


def get_table_schema(table_name: str) -> list[dict[str, Any]]:
    _get_table_metadata(table_name)
    with connection_scope() as connection:
        columns = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        index_rows = connection.execute(f"PRAGMA index_list({table_name})").fetchall()

        indexed_columns: set[str] = set()
        for index_row in index_rows:
            index_name = index_row["name"]
            for column_row in connection.execute(f"PRAGMA index_info({index_name})").fetchall():
                indexed_columns.add(column_row["name"])

    return [
        {
            "name": column["name"],
            "data_type": column["type"] or "TEXT",
            "nullable": not bool(column["notnull"]),
            "is_primary_key": bool(column["pk"]),
            "is_indexed": column["name"] in indexed_columns,
        }
        for column in columns
    ]


def get_table_rows(
    table_name: str,
    *,
    limit: int = 50,
    offset: int = 0,
    search: str | None = None,
    column: str | None = None,
    order_by: str | None = None,
    order_dir: str = "desc",
) -> tuple[list[dict[str, Any]], int]:
    metadata = _get_table_metadata(table_name)
    effective_limit = max(1, min(limit, 100))
    effective_offset = max(offset, 0)
    sort_column = order_by or metadata["default_order"]
    if sort_column not in metadata["order_columns"]:
        raise ValueError(f"Unsupported sort column: {sort_column}")

    sort_direction = "ASC" if order_dir.lower() == "asc" else "DESC"
    where_sql, params = _build_search_clause(metadata, search, column)

    with connection_scope() as connection:
        total_row = safe_sql_execute(
            connection,
            f"SELECT COUNT(*) AS total FROM {table_name}{where_sql}",
            tuple(params),
        )[0]
        rows = safe_sql_execute(
            connection,
            f"SELECT * FROM {table_name}{where_sql} ORDER BY {sort_column} {sort_direction} LIMIT ? OFFSET ?",
            tuple([*params, effective_limit, effective_offset]),
        )

    return rows, int(total_row["total"] or 0)


def _list_runs(table_name: str, limit: int = 20, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
    effective_limit = max(1, min(limit, 100))
    effective_offset = max(offset, 0)
    with connection_scope() as connection:
        total = safe_sql_execute(connection, f"SELECT COUNT(*) AS total FROM {table_name}")[0]["total"]
        rows = safe_sql_execute(
            connection,
            f"""
            SELECT *
            FROM {table_name}
            ORDER BY COALESCE(completed_at, started_at) DESC, started_at DESC
            LIMIT ? OFFSET ?
            """,
            (effective_limit, effective_offset),
        )
    return rows, int(total or 0)


def create_ingestion_run(run_id: str, batch_id: str, request: IngestionRunRequest) -> None:
    with connection_scope() as connection:
        connection.execute(
            """
            INSERT INTO ingestion_runs (
                id, status, market, category, recent_days, from_timestamp, to_timestamp,
                sources, seed_terms, target_keywords, suggested_keywords, recency_support_json,
                source_batch_id, guardrail_flags, stats_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                "queued",
                request.market,
                request.category,
                request.recent_days,
                request.from_timestamp.isoformat() if request.from_timestamp else None,
                request.to_timestamp.isoformat() if request.to_timestamp else None,
                json_dumps(request.sources),
                json_dumps(request.seed_terms),
                json_dumps(request.target_keywords),
                json_dumps(request.suggested_keywords),
                json_dumps([]),
                batch_id,
                json_dumps([]),
                json_dumps({}),
            ),
        )


def update_ingestion_run(
    run_id: str,
    *,
    status: str,
    stats: dict[str, Any] | None = None,
    error_message: str | None = None,
    guardrail_flags: list[str] | None = None,
    recency_support: list[dict[str, Any]] | None = None,
) -> None:
    completed_at = datetime.utcnow().isoformat() if status in {"completed", "failed"} else None
    with connection_scope() as connection:
        connection.execute(
            """
            UPDATE ingestion_runs
            SET status = ?,
                stats_json = COALESCE(?, stats_json),
                error_message = COALESCE(?, error_message),
                guardrail_flags = COALESCE(?, guardrail_flags),
                recency_support_json = COALESCE(?, recency_support_json),
                completed_at = COALESCE(?, completed_at)
            WHERE id = ?
            """,
            (
                status,
                json_dumps(stats) if stats is not None else None,
                error_message,
                json_dumps(guardrail_flags) if guardrail_flags is not None else None,
                json_dumps(recency_support) if recency_support is not None else None,
                completed_at,
                run_id,
            ),
        )


def get_ingestion_run(run_id: str) -> dict[str, Any] | None:
    with connection_scope() as connection:
        row = connection.execute("SELECT * FROM ingestion_runs WHERE id = ?", (run_id,)).fetchone()
    return dict(row) if row else None


def list_ingestion_runs(limit: int = 20, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
    return _list_runs("ingestion_runs", limit=limit, offset=offset)


def create_analysis_run(run_id: str, request: AnalysisRunRequest) -> None:
    with connection_scope() as connection:
        connection.execute(
            """
            INSERT INTO analysis_runs (
                id, status, market, category, recency_days, analysis_mode, execution_trace
            ) VALUES (?, 'queued', ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                request.market,
                request.category,
                request.recency_days,
                request.analysis_mode,
                json_dumps([]),
            ),
        )


def update_analysis_run(
    run_id: str,
    *,
    status: str,
    execution_trace: list[str] | None = None,
    report: dict[str, Any] | None = None,
    error_message: str | None = None,
    source_batch_ids: list[str] | None = None,
    tool_invocations: list[dict[str, Any]] | None = None,
) -> None:
    completed_at = datetime.utcnow().isoformat() if status in {"completed", "failed"} else None
    with connection_scope() as connection:
        connection.execute(
            """
            UPDATE analysis_runs
            SET status = ?,
                execution_trace = COALESCE(?, execution_trace),
                report_json = COALESCE(?, report_json),
                error_message = COALESCE(?, error_message),
                source_batch_ids = COALESCE(?, source_batch_ids),
                tool_invocations_json = COALESCE(?, tool_invocations_json),
                completed_at = COALESCE(?, completed_at)
            WHERE id = ?
            """,
            (
                status,
                json_dumps(execution_trace) if execution_trace is not None else None,
                json_dumps(report) if report is not None else None,
                error_message,
                json_dumps(source_batch_ids) if source_batch_ids is not None else None,
                json_dumps(tool_invocations) if tool_invocations is not None else None,
                completed_at,
                run_id,
            ),
        )


def get_analysis_run(run_id: str) -> dict[str, Any] | None:
    with connection_scope() as connection:
        row = connection.execute("SELECT * FROM analysis_runs WHERE id = ?", (run_id,)).fetchone()
    return dict(row) if row else None


def list_analysis_runs(limit: int = 20, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
    return _list_runs("analysis_runs", limit=limit, offset=offset)


def get_latest_trend_report(market: str, category: str) -> dict[str, Any] | None:
    with connection_scope() as connection:
        row = connection.execute(
            """
            SELECT report_json
            FROM analysis_runs
            WHERE status = 'completed' AND market = ? AND category = ?
            ORDER BY completed_at DESC
            LIMIT 1
            """,
            (market, category),
        ).fetchone()
    return json_loads(row["report_json"], None) if row and row["report_json"] else None


def get_prior_trend_snapshot(market: str, category: str, lookback_days: int = 30) -> dict[str, dict[str, Any]]:
    category_filter = "" if category == "all" else "AND COALESCE(hb_category, 'all') = ?"
    params: list[Any] = [market]
    if category != "all":
        params.append(category)
    params.append(f"-{lookback_days} days")
    with connection_scope() as connection:
        rows = connection.execute(
            f"""
            SELECT canonical_term,
                   market,
                   hb_category,
                   virality_score,
                   confidence_tier,
                   sources_count,
                   social_score,
                   search_score,
                   sales_score,
                   cross_market_score,
                   sentiment_score,
                   avg_positivity_score,
                   analysis_date,
                   source_batch_ids,
                   candidate_json,
                   evidence_summary,
                   llm_rationale,
                   status
            FROM trend_exploration
            WHERE market = ?
              {category_filter}
              AND datetime(analysis_date) >= datetime('now', ?)
            ORDER BY datetime(analysis_date) DESC
            """,
            tuple(params),
        ).fetchall()

    snapshot: dict[str, dict[str, Any]] = {}
    for row in rows:
        payload = dict(row)
        key = f"{payload['market']}:{payload['canonical_term']}"
        if key in snapshot:
            continue
        payload["source_batch_ids"] = json_loads(payload["source_batch_ids"], [])
        payload["candidate_json"] = json_loads(payload["candidate_json"], {})
        snapshot[key] = payload
    return snapshot


def get_latest_source_health() -> list[dict[str, Any]]:
    with connection_scope() as connection:
        search_row = connection.execute(
            """
            SELECT MAX(processed_at) AS latest_completed_at,
                   source_batch_id AS latest_batch_id,
                   COUNT(*) AS row_count
            FROM search_trends
            WHERE source_batch_id IS NOT NULL
            """
        ).fetchone()
        sales_row = connection.execute(
            """
            SELECT MAX(week_start) AS latest_completed_at,
                   source_batch_id AS latest_batch_id,
                   COUNT(*) AS row_count
            FROM sales_data
            """
        ).fetchone()
        tiktok_row = connection.execute(
            """
            SELECT
                (SELECT MAX(fetched_at) FROM tiktok_photo_posts) AS latest_completed_at,
                (
                    SELECT source_batch_id FROM tiktok_photo_posts
                    WHERE fetched_at = (SELECT MAX(fetched_at) FROM tiktok_photo_posts)
                    LIMIT 1
                ) AS latest_batch_id,
                (SELECT COUNT(*) FROM tiktok_photo_posts) AS row_count
            """
        ).fetchone()
        instagram_row = connection.execute(
            """
            SELECT
                (SELECT MAX(fetched_at) FROM instagram_posts) AS latest_completed_at,
                (
                    SELECT source_batch_id FROM instagram_posts
                    WHERE fetched_at = (SELECT MAX(fetched_at) FROM instagram_posts)
                    LIMIT 1
                ) AS latest_batch_id,
                (SELECT COUNT(*) FROM instagram_posts) AS row_count
            """
        ).fetchone()
    return [
        {"source": "google_trends", **dict(search_row)},
        {"source": "sales", **dict(sales_row)},
        {"source": "tiktok", **dict(tiktok_row)},
        {"source": "instagram", **dict(instagram_row)},
    ]


def get_entity_dictionary() -> dict[str, dict[str, Any]]:
    with connection_scope() as connection:
        rows = connection.execute("SELECT * FROM entity_dictionary").fetchall()
    return {
        row["canonical_term"]: {
            "aliases": json_loads(row["aliases"], []),
            "entity_type": row["entity_type"],
            "hb_category": row["hb_category"],
            "origin_market": row["origin_market"],
            "description": row["description"],
        }
        for row in rows
    }


def upsert_social_post(record: dict[str, Any]) -> None:
    with connection_scope() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO social_posts (
                id, platform, region, post_date, title, content_text, hashtags,
                entity_mentions, comment_mentions, liked_count, collected_count,
                comment_count, share_count, engagement_score, seed_keyword,
                llm_category, llm_subcategory, positivity_score, sentiment_label,
                relevance_score, llm_entities, llm_summary, processed_at,
                processing_model, source_batch_id, source_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["id"],
                record.get("platform", "rednote"),
                record.get("region"),
                record["post_date"],
                record.get("title"),
                record.get("content_text"),
                json_dumps(record.get("hashtags", [])),
                json_dumps(record.get("entity_mentions", [])),
                json_dumps(record.get("comment_mentions", [])),
                record.get("liked_count", 0),
                record.get("collected_count", 0),
                record.get("comment_count", 0),
                record.get("share_count", 0),
                record.get("engagement_score", 0.0),
                record.get("seed_keyword"),
                record.get("llm_category"),
                record.get("llm_subcategory"),
                record.get("positivity_score", 0.0),
                record.get("sentiment_label"),
                record.get("relevance_score", 0.0),
                json_dumps(record.get("llm_entities", [])),
                record.get("llm_summary"),
                record.get("processed_at"),
                record.get("processing_model"),
                record.get("source_batch_id"),
                json_dumps(record.get("source_payload", {})),
            ),
        )


def upsert_tiktok_photo_posts(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with connection_scope() as connection:
        connection.executemany(
            """
            INSERT OR REPLACE INTO tiktok_photo_posts (
                id, search_keyword, create_time_unix, create_time, description,
                author_json, image_url, cover_url, stats_json, hashtags_json,
                music_json, is_ad, share_url, source_batch_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["id"],
                    row["search_keyword"],
                    row.get("create_time_unix"),
                    row.get("create_time"),
                    row.get("description", ""),
                    row.get("author_json", "{}"),
                    row.get("image_url"),
                    row.get("cover_url"),
                    row.get("stats_json", "{}"),
                    row.get("hashtags_json", "[]"),
                    row.get("music_json"),
                    int(row.get("is_ad", 0)),
                    row.get("share_url"),
                    row.get("source_batch_id"),
                )
                for row in rows
            ],
        )


def upsert_instagram_posts(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with connection_scope() as connection:
        connection.executemany(
            """
            INSERT OR REPLACE INTO instagram_posts (
                post_id, search_keyword, code, username, full_name, caption,
                hashtags_json, mentions_json, likes, comments, views, is_video,
                created_at, location_name, city, lat, lng, source_batch_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["post_id"],
                    row["search_keyword"],
                    row.get("code"),
                    row.get("username"),
                    row.get("full_name"),
                    row.get("caption"),
                    row.get("hashtags_json", "[]"),
                    row.get("mentions_json", "[]"),
                    int(row.get("likes", 0)),
                    int(row.get("comments", 0)),
                    int(row.get("views", 0)),
                    int(row.get("is_video", 0)),
                    row.get("created_at"),
                    row.get("location_name"),
                    row.get("city"),
                    row.get("lat"),
                    row.get("lng"),
                    row.get("source_batch_id"),
                )
                for row in rows
            ],
        )


def upsert_search_trend(record: dict[str, Any]) -> None:
    with connection_scope() as connection:
        connection.execute(
            """
            INSERT INTO search_trends (
                keyword, geo, snapshot_date, index_value, wow_delta, is_breakout,
                related_rising, raw_timeseries, source, llm_category, llm_subcategory,
                relevance_score, processed_at, source_batch_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(keyword, geo, snapshot_date)
            DO UPDATE SET
                index_value = excluded.index_value,
                wow_delta = excluded.wow_delta,
                is_breakout = excluded.is_breakout,
                related_rising = excluded.related_rising,
                raw_timeseries = excluded.raw_timeseries,
                source = excluded.source,
                llm_category = excluded.llm_category,
                llm_subcategory = excluded.llm_subcategory,
                relevance_score = excluded.relevance_score,
                processed_at = excluded.processed_at,
                source_batch_id = excluded.source_batch_id,
                last_updated = CURRENT_TIMESTAMP
            """,
            (
                record["keyword"],
                record["geo"],
                record["snapshot_date"],
                record.get("index_value"),
                record.get("wow_delta"),
                int(record.get("is_breakout", False)),
                json_dumps(record.get("related_rising", [])),
                json_dumps(record.get("raw_timeseries", [])),
                record.get("source", "serpapi"),
                record.get("llm_category"),
                record.get("llm_subcategory"),
                record.get("relevance_score", 0.0),
                record.get("processed_at"),
                record.get("source_batch_id"),
            ),
        )


def get_social_trend_rows(region: str, category: str, recency_days: int) -> list[dict[str, Any]]:
    category_filter = "" if category == "all" else "AND COALESCE(llm_category, 'all') = ?"
    params: list[Any] = [region, f"-{recency_days} days"]
    if category != "all":
        params.append(category)
    query = f"""
        SELECT
            COALESCE(llm_entities, entity_mentions, '[]') AS entity_list,
            AVG(engagement_score) AS avg_engagement,
            AVG(positivity_score) AS avg_positivity_score,
            COUNT(*) AS post_count,
            SUM(liked_count) AS total_likes,
            SUM(comment_count) AS total_comments
        FROM social_posts
        WHERE region = ?
          AND date(post_date) >= date('now', ?)
          {category_filter}
          AND relevance_score >= 0.4
        GROUP BY entity_list
    """
    with connection_scope() as connection:
        return safe_sql_execute(connection, query, tuple(params))


def get_search_breakout_rows(region: str, category: str, recency_days: int) -> list[dict[str, Any]]:
    category_filter = "" if category == "all" else "AND COALESCE(llm_category, 'all') = ?"
    params: list[Any] = [region, f"-{recency_days} days"]
    if category != "all":
        params.append(category)
    query = f"""
        SELECT
            keyword,
            wow_delta,
            index_value,
            is_breakout,
            related_rising,
            source_batch_id
        FROM search_trends
        WHERE geo = ?
          AND date(snapshot_date) >= date('now', ?)
          AND is_breakout = 1
          {category_filter}
          AND relevance_score >= 0.4
        ORDER BY wow_delta DESC
    """
    with connection_scope() as connection:
        return safe_sql_execute(connection, query, tuple(params))


def get_sales_velocity_rows(region: str, category: str, recency_days: int) -> list[dict[str, Any]]:
    category_filter = "" if category == "all" else "AND category = ?"
    params: list[Any] = [region, f"-{recency_days} days"]
    if category != "all":
        params.append(category)
    query = f"""
        SELECT
            ingredient_tags,
            brand,
            category,
            AVG(wow_velocity) AS avg_velocity,
            SUM(units_sold) AS total_units,
            SUM(is_restocking) AS restock_count,
            source_batch_id
        FROM sales_data
        WHERE region = ?
          AND date(week_start) >= date('now', ?)
          {category_filter}
        GROUP BY brand, ingredient_tags, category, source_batch_id
        ORDER BY avg_velocity DESC
    """
    with connection_scope() as connection:
        return safe_sql_execute(connection, query, tuple(params))


def persist_trend_report(
    report_id: str,
    market: str,
    batch_ids: list[str],
    trend_rows: list[dict[str, Any]],
    report_payload: dict[str, Any] | None = None,
) -> None:
    analysis_date = datetime.utcnow().isoformat()
    with connection_scope() as connection:
        for trend in trend_rows:
            connection.execute(
                """
                INSERT OR REPLACE INTO trend_exploration (
                    trend_id, canonical_term, entity_type, hb_category, virality_score,
                    confidence_tier, sources_count, social_score, search_score,
                    sales_score, cross_market_score, sentiment_score, avg_positivity_score,
                    market, analysis_date, current_batch_id, source_batch_ids,
                    candidate_json, evidence_summary, llm_rationale, status, report_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"{report_id}:{trend['term']}",
                    trend["term"],
                    trend["entity_type"],
                    trend.get("category"),
                    trend["virality_score"],
                    trend["confidence_tier"],
                    trend["sources_count"],
                    trend["social_score"],
                    trend["search_score"],
                    trend["sales_score"],
                    trend["cross_market_score"],
                    trend.get("sentiment_score", 0.0),
                    trend.get("avg_positivity_score", 0.0),
                    market,
                    analysis_date,
                    batch_ids[0] if batch_ids else None,
                    json_dumps(batch_ids),
                    json_dumps(trend),
                    trend.get("why_viral"),
                    trend.get("headline"),
                    "watch" if trend.get("watch_flag") else "confirmed",
                    json_dumps(report_payload) if report_payload is not None else None,
                ),
            )


def get_latest_source_batch_ids() -> list[str]:
    with connection_scope() as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT source_batch_id
            FROM (
                SELECT source_batch_id, processed_at AS completed_at FROM social_posts WHERE source_batch_id IS NOT NULL
                UNION ALL
                SELECT source_batch_id, processed_at AS completed_at FROM search_trends WHERE source_batch_id IS NOT NULL
                UNION ALL
                SELECT source_batch_id, week_start AS completed_at FROM sales_data WHERE source_batch_id IS NOT NULL
                UNION ALL
                SELECT source_batch_id, fetched_at AS completed_at FROM tiktok_photo_posts WHERE source_batch_id IS NOT NULL
                UNION ALL
                SELECT source_batch_id, fetched_at AS completed_at FROM instagram_posts WHERE source_batch_id IS NOT NULL
            )
            WHERE source_batch_id IS NOT NULL
            ORDER BY completed_at DESC
            LIMIT 3
            """
        ).fetchall()
    return [row["source_batch_id"] for row in rows]
