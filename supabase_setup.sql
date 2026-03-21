-- Run this in Supabase SQL Editor (Dashboard → SQL Editor → New query)

CREATE TABLE IF NOT EXISTS users (
    luffa_uid TEXT PRIMARY KEY,
    customer_name TEXT DEFAULT 'Customer',
    first_seen TIMESTAMPTZ DEFAULT now(),
    last_seen TIMESTAMPTZ DEFAULT now(),
    total_quotes INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS quote_history (
    id SERIAL PRIMARY KEY,
    luffa_uid TEXT REFERENCES users(luffa_uid),
    session_id TEXT,
    quote_reference TEXT,
    job_type TEXT,
    final_price REAL,
    created_at TIMESTAMPTZ DEFAULT now()
);
