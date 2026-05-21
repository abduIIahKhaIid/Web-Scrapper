create extension if not exists vector;

-- Development reset.
-- Use this only while testing because it deletes these three tables.
drop function if exists public.match_activity_by_name(vector, text, integer);

drop table if exists public.reconciliation_results cascade;
drop table if exists public.fetched_activities cascade;
drop table if exists public.activities cascade;

create table public.activities (
    id bigserial primary key,

    activity_name text not null,
    activity_name_normalized text not null,

    activity_code bigint not null,

    division integer,
    activity_group integer,
    class_code integer,

    isic_description text,
    activity_description text,

    jurisdiction text not null,

    -- Jurisdiction/API official fields.
    -- Keep official_code as text because Meydan codes are like 0140.00.
    official_code text,
    official_category text,
    official_status text,
    official_risk_rating text,
    official_industry_risk text,
    official_dnfbp text,
    official_third_party text,
    official_when text,
    official_notes text,

    -- Vector search should be based only on Activity Name.
    semantic_text text not null,
    embedding vector(1536),

    status text default 'Approved',
    match_type text,
    matched_with text,
    match_score numeric,
    reason text,
    openai_decision jsonb,

    source text default 'consolidated_xlsx',
    raw_payload jsonb,

    source_row_hash text unique,

    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    last_checked_at timestamptz
);

create table public.fetched_activities (
    id bigserial primary key,

    jurisdiction text not null,
    source_type text not null,

    official_code text,
    activity_name text not null,
    activity_name_normalized text not null,

    official_category text,
    official_status text,
    official_risk_rating text,
    official_industry_risk text,
    official_dnfbp text,
    official_third_party text,
    official_when text,
    official_notes text,

    raw_payload jsonb,
    source_row_hash text unique,

    fetched_at timestamptz default now()
);

create table public.reconciliation_results (
    id bigserial primary key,

    jurisdiction text not null,

    fetched_activity_name text,
    fetched_official_code text,

    matched_activity_id bigint,
    matched_activity_name text,
    matched_activity_code bigint,

    assigned_activity_code bigint,

    fuzzy_score numeric,
    vector_score numeric,

    action_type text,
    status text,
    reason text,
    openai_decision jsonb,

    created_at timestamptz default now()
);

create or replace function public.match_activity_by_name(
    query_embedding vector(1536),
    target_jurisdiction text,
    match_count int default 5
)
returns table (
    id bigint,
    activity_name text,
    activity_code bigint,
    jurisdiction text,
    status text,
    similarity float
)
language sql
stable
as $$
    select
        activities.id,
        activities.activity_name,
        activities.activity_code,
        activities.jurisdiction,
        activities.status,
        1 - (activities.embedding <=> query_embedding) as similarity
    from public.activities
    where activities.embedding is not null
      and lower(activities.jurisdiction) = lower(target_jurisdiction)
      and activities.activity_code is not null
    order by activities.embedding <=> query_embedding
    limit match_count;
$$;

notify pgrst, 'reload schema';