from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from api.config import settings
from api.db import get_connection as _backend_connect
from api.db.base import DbConnection
from api.db.dialect import last_insert_id as _dialect_last_insert_id
from api.db.dialect import table_columns, table_exists
from api.security import hash_password


SYNC_SCHEMA_VERSION = "2026-07-tmc-settlements-v1"
SYNC_OPERATIONS = {"INSERT", "UPDATE", "DELETE"}

UUID_READY_TABLES = (
    "users",
    "persons",
    "organizations",
    "counterparties",
    "objects",
    "works",
    "units",
    "materials",
    "work_specifications",
    "estimates",
    "estimate_lines",
    "daily_reports",
    "daily_report_lines",
    "timesheets",
    "timesheet_lines",
    "work_execution_register",
    "payroll_register",
    "contracts",
    "payment_schedules",
    "payment_schedule_lines",
    "payment_transactions",
    "payment_schedule_register",
    "goods_receipts",
    "goods_receipt_lines",
    "goods_issues",
    "goods_issue_lines",
)

REFERENCE_TABLES = {
    "counterparties",
    "objects",
    "works",
    "persons",
    "organizations",
    "contracts",
}

SCHEMA_TABLES_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'manager',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    uuid TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sessions (
    jti TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    last_activity TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS persons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    personnel_number TEXT,
    position TEXT,
    phone TEXT,
    hourly_rate REAL NOT NULL DEFAULT 0,
    user_id INTEGER,
    parent_id INTEGER,
    marked_for_deletion INTEGER NOT NULL DEFAULT 0,
    is_group INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    uuid TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (parent_id) REFERENCES persons(id)
);

CREATE TABLE IF NOT EXISTS organizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    inn TEXT,
    default_responsible_id INTEGER,
    parent_id INTEGER,
    marked_for_deletion INTEGER NOT NULL DEFAULT 0,
    is_group INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    uuid TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (default_responsible_id) REFERENCES persons(id),
    FOREIGN KEY (parent_id) REFERENCES organizations(id)
);

CREATE TABLE IF NOT EXISTS counterparties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    inn TEXT,
    contact_person TEXT,
    phone TEXT,
    parent_id INTEGER,
    marked_for_deletion INTEGER NOT NULL DEFAULT 0,
    is_group INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    uuid TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (parent_id) REFERENCES counterparties(id)
);

CREATE TABLE IF NOT EXISTS objects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    address TEXT,
    owner_id INTEGER,
    parent_id INTEGER,
    marked_for_deletion INTEGER NOT NULL DEFAULT 0,
    is_group INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    uuid TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (owner_id) REFERENCES counterparties(id),
    FOREIGN KEY (parent_id) REFERENCES objects(id)
);

CREATE TABLE IF NOT EXISTS works (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    code TEXT,
    unit TEXT,
    price REAL NOT NULL DEFAULT 0,
    labor_rate REAL NOT NULL DEFAULT 0,
    specification_review_status TEXT NOT NULL DEFAULT 'ok',
    specification_review_note TEXT,
    parent_id INTEGER,
    marked_for_deletion INTEGER NOT NULL DEFAULT 0,
    is_group INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    uuid TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (parent_id) REFERENCES works(id)
);

CREATE TABLE IF NOT EXISTS units (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    short_name TEXT,
    marked_for_deletion INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    uuid TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    name TEXT NOT NULL,
    unit_id INTEGER,
    price REAL NOT NULL DEFAULT 0,
    marked_for_deletion INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    uuid TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (unit_id) REFERENCES units(id)
);

CREATE TABLE IF NOT EXISTS work_specifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_id INTEGER NOT NULL,
    component_type TEXT NOT NULL,
    component_name TEXT NOT NULL,
    unit_id INTEGER,
    consumption_rate REAL NOT NULL DEFAULT 0,
    unit_price REAL NOT NULL DEFAULT 0,
    marked_for_deletion INTEGER NOT NULL DEFAULT 0,
    material_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    uuid TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE,
    FOREIGN KEY (unit_id) REFERENCES units(id),
    FOREIGN KEY (material_id) REFERENCES materials(id)
);

CREATE TABLE IF NOT EXISTS estimates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL,
    date TEXT NOT NULL,
    customer_id INTEGER,
    object_id INTEGER,
    contractor_id INTEGER,
    responsible_id INTEGER,
    contract_id INTEGER,
    total_sum REAL NOT NULL DEFAULT 0,
    total_labor REAL NOT NULL DEFAULT 0,
    is_posted INTEGER NOT NULL DEFAULT 0,
    posted_at TEXT,
    marked_for_deletion INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    uuid TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (customer_id) REFERENCES counterparties(id),
    FOREIGN KEY (object_id) REFERENCES objects(id),
    FOREIGN KEY (contractor_id) REFERENCES organizations(id),
    FOREIGN KEY (contract_id) REFERENCES contracts(id),
    FOREIGN KEY (responsible_id) REFERENCES persons(id)
);

CREATE TABLE IF NOT EXISTS estimate_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    estimate_id INTEGER NOT NULL,
    line_number INTEGER NOT NULL,
    work_id INTEGER,
    quantity REAL NOT NULL DEFAULT 0,
    unit TEXT,
    price REAL NOT NULL DEFAULT 0,
    labor_rate REAL NOT NULL DEFAULT 0,
    sum REAL NOT NULL DEFAULT 0,
    planned_labor REAL NOT NULL DEFAULT 0,
    is_group INTEGER NOT NULL DEFAULT 0,
    group_name TEXT,
    parent_group_id INTEGER,
    is_collapsed INTEGER NOT NULL DEFAULT 0,
    marked_for_deletion INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    uuid TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (estimate_id) REFERENCES estimates(id) ON DELETE CASCADE,
    FOREIGN KEY (work_id) REFERENCES works(id),
    FOREIGN KEY (parent_group_id) REFERENCES estimate_lines(id)
);

CREATE TABLE IF NOT EXISTS daily_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL,
    date TEXT NOT NULL,
    estimate_id INTEGER,
    foreman_id INTEGER,
    supplementary_agreement_id INTEGER,
    is_posted INTEGER NOT NULL DEFAULT 0,
    posted_at TEXT,
    marked_for_deletion INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    uuid TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (estimate_id) REFERENCES estimates(id),
    FOREIGN KEY (foreman_id) REFERENCES persons(id),
    FOREIGN KEY (supplementary_agreement_id) REFERENCES contracts(id)
);

CREATE TABLE IF NOT EXISTS daily_report_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL,
    line_number INTEGER NOT NULL,
    work_id INTEGER,
    planned_labor REAL NOT NULL DEFAULT 0,
    actual_labor REAL NOT NULL DEFAULT 0,
    deviation_percent REAL NOT NULL DEFAULT 0,
    quantity REAL NOT NULL DEFAULT 0,
    unit TEXT,
    price REAL NOT NULL DEFAULT 0,
    actual_sum REAL NOT NULL DEFAULT 0,
    is_group INTEGER NOT NULL DEFAULT 0,
    group_name TEXT,
    parent_group_id INTEGER,
    is_collapsed INTEGER NOT NULL DEFAULT 0,
    marked_for_deletion INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    uuid TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (report_id) REFERENCES daily_reports(id) ON DELETE CASCADE,
    FOREIGN KEY (work_id) REFERENCES works(id),
    FOREIGN KEY (parent_group_id) REFERENCES daily_report_lines(id)
);

CREATE TABLE IF NOT EXISTS daily_report_executors (
    report_line_id INTEGER NOT NULL,
    executor_id INTEGER NOT NULL,
    PRIMARY KEY (report_line_id, executor_id),
    FOREIGN KEY (report_line_id) REFERENCES daily_report_lines(id) ON DELETE CASCADE,
    FOREIGN KEY (executor_id) REFERENCES persons(id)
);

CREATE TABLE IF NOT EXISTS work_execution_register (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorder_type TEXT NOT NULL,
    recorder_id INTEGER NOT NULL,
    line_number INTEGER NOT NULL,
    period TEXT NOT NULL,
    object_id INTEGER,
    estimate_id INTEGER,
    work_id INTEGER,
    quantity_income REAL NOT NULL DEFAULT 0,
    quantity_expense REAL NOT NULL DEFAULT 0,
    sum_income REAL NOT NULL DEFAULT 0,
    sum_expense REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    uuid TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (object_id) REFERENCES objects(id),
    FOREIGN KEY (estimate_id) REFERENCES estimates(id),
    FOREIGN KEY (work_id) REFERENCES works(id)
);

CREATE TABLE IF NOT EXISTS timesheets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL,
    date TEXT NOT NULL,
    object_id INTEGER,
    estimate_id INTEGER,
    foreman_id INTEGER,
    month_year TEXT NOT NULL,
    is_posted INTEGER NOT NULL DEFAULT 0,
    posted_at TEXT,
    marked_for_deletion INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    uuid TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (object_id) REFERENCES objects(id),
    FOREIGN KEY (estimate_id) REFERENCES estimates(id),
    FOREIGN KEY (foreman_id) REFERENCES persons(id)
);

CREATE TABLE IF NOT EXISTS timesheet_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timesheet_id INTEGER NOT NULL,
    line_number INTEGER NOT NULL,
    employee_id INTEGER NOT NULL,
    hourly_rate REAL NOT NULL DEFAULT 0,
    day_01 REAL NOT NULL DEFAULT 0,
    day_02 REAL NOT NULL DEFAULT 0,
    day_03 REAL NOT NULL DEFAULT 0,
    day_04 REAL NOT NULL DEFAULT 0,
    day_05 REAL NOT NULL DEFAULT 0,
    day_06 REAL NOT NULL DEFAULT 0,
    day_07 REAL NOT NULL DEFAULT 0,
    day_08 REAL NOT NULL DEFAULT 0,
    day_09 REAL NOT NULL DEFAULT 0,
    day_10 REAL NOT NULL DEFAULT 0,
    day_11 REAL NOT NULL DEFAULT 0,
    day_12 REAL NOT NULL DEFAULT 0,
    day_13 REAL NOT NULL DEFAULT 0,
    day_14 REAL NOT NULL DEFAULT 0,
    day_15 REAL NOT NULL DEFAULT 0,
    day_16 REAL NOT NULL DEFAULT 0,
    day_17 REAL NOT NULL DEFAULT 0,
    day_18 REAL NOT NULL DEFAULT 0,
    day_19 REAL NOT NULL DEFAULT 0,
    day_20 REAL NOT NULL DEFAULT 0,
    day_21 REAL NOT NULL DEFAULT 0,
    day_22 REAL NOT NULL DEFAULT 0,
    day_23 REAL NOT NULL DEFAULT 0,
    day_24 REAL NOT NULL DEFAULT 0,
    day_25 REAL NOT NULL DEFAULT 0,
    day_26 REAL NOT NULL DEFAULT 0,
    day_27 REAL NOT NULL DEFAULT 0,
    day_28 REAL NOT NULL DEFAULT 0,
    day_29 REAL NOT NULL DEFAULT 0,
    day_30 REAL NOT NULL DEFAULT 0,
    day_31 REAL NOT NULL DEFAULT 0,
    total_hours REAL NOT NULL DEFAULT 0,
    total_amount REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    uuid TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (timesheet_id) REFERENCES timesheets(id) ON DELETE CASCADE,
    FOREIGN KEY (employee_id) REFERENCES persons(id)
);

CREATE TABLE IF NOT EXISTS payroll_register (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorder_type TEXT NOT NULL,
    recorder_id INTEGER NOT NULL,
    line_number INTEGER NOT NULL,
    period TEXT NOT NULL,
    object_id INTEGER,
    estimate_id INTEGER,
    employee_id INTEGER,
    work_date TEXT NOT NULL,
    hours_worked REAL NOT NULL DEFAULT 0,
    amount REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    uuid TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (object_id) REFERENCES objects(id),
    FOREIGN KEY (estimate_id) REFERENCES estimates(id),
    FOREIGN KEY (employee_id) REFERENCES persons(id)
);

CREATE TABLE IF NOT EXISTS contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL DEFAULT '',
    date TEXT,
    counterparty_id INTEGER,
    organization_id INTEGER,
    parent_id INTEGER,
    amount REAL NOT NULL DEFAULT 0,
    kind TEXT NOT NULL DEFAULT 'supply',
    currency TEXT NOT NULL DEFAULT 'RUB',
    vat_rate REAL NOT NULL DEFAULT 20.0,
    payment_deferral_days INTEGER NOT NULL DEFAULT 0,
    agreement_date TEXT,
    valid_until TEXT,
    description TEXT,
    marked_for_deletion INTEGER NOT NULL DEFAULT 0,
    is_group INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    uuid TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (counterparty_id) REFERENCES counterparties(id),
    FOREIGN KEY (organization_id) REFERENCES organizations(id),
    FOREIGN KEY (parent_id) REFERENCES contracts(id)
);

CREATE TABLE IF NOT EXISTS payment_schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL DEFAULT '',
    date_from TEXT NOT NULL,
    date_to TEXT NOT NULL,
    object_id INTEGER,
    contract_id INTEGER,
    responsible_id INTEGER,
    is_posted INTEGER NOT NULL DEFAULT 0,
    posted_at TEXT,
    marked_for_deletion INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    uuid TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (object_id) REFERENCES objects(id),
    FOREIGN KEY (contract_id) REFERENCES contracts(id),
    FOREIGN KEY (responsible_id) REFERENCES persons(id)
);

CREATE TABLE IF NOT EXISTS payment_schedule_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schedule_id INTEGER NOT NULL,
    line_number INTEGER NOT NULL,
    direction TEXT NOT NULL DEFAULT 'outgoing',
    category TEXT NOT NULL DEFAULT 'other',
    planned_date TEXT NOT NULL,
    counterparty_id INTEGER,
    contract_id INTEGER,
    estimate_id INTEGER,
    object_id INTEGER,
    planned_amount REAL NOT NULL DEFAULT 0,
    description TEXT,
    source_kind TEXT NOT NULL DEFAULT 'manual',
    source_ref TEXT,
    is_group INTEGER NOT NULL DEFAULT 0,
    group_name TEXT,
    parent_group_id INTEGER,
    is_collapsed INTEGER NOT NULL DEFAULT 0,
    marked_for_deletion INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    uuid TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (schedule_id) REFERENCES payment_schedules(id) ON DELETE CASCADE,
    FOREIGN KEY (counterparty_id) REFERENCES counterparties(id),
    FOREIGN KEY (contract_id) REFERENCES contracts(id),
    FOREIGN KEY (estimate_id) REFERENCES estimates(id),
    FOREIGN KEY (object_id) REFERENCES objects(id),
    FOREIGN KEY (parent_group_id) REFERENCES payment_schedule_lines(id)
);

CREATE TABLE IF NOT EXISTS payment_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL DEFAULT '',
    date TEXT NOT NULL,
    direction TEXT NOT NULL DEFAULT 'outgoing',
    category TEXT NOT NULL DEFAULT 'other',
    counterparty_id INTEGER,
    contract_id INTEGER,
    estimate_id INTEGER,
    object_id INTEGER,
    linked_schedule_id INTEGER,
    linked_line_id INTEGER,
    amount REAL NOT NULL DEFAULT 0,
    description TEXT,
    is_posted INTEGER NOT NULL DEFAULT 0,
    posted_at TEXT,
    marked_for_deletion INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    uuid TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (counterparty_id) REFERENCES counterparties(id),
    FOREIGN KEY (contract_id) REFERENCES contracts(id),
    FOREIGN KEY (estimate_id) REFERENCES estimates(id),
    FOREIGN KEY (object_id) REFERENCES objects(id),
    FOREIGN KEY (linked_schedule_id) REFERENCES payment_schedules(id),
    FOREIGN KEY (linked_line_id) REFERENCES payment_schedule_lines(id)
);

CREATE TABLE IF NOT EXISTS payment_schedule_register (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorder_type TEXT NOT NULL,
    recorder_id INTEGER NOT NULL,
    line_number INTEGER NOT NULL,
    period TEXT NOT NULL,
    direction TEXT NOT NULL,
    category TEXT NOT NULL,
    counterparty_id INTEGER,
    contract_id INTEGER,
    estimate_id INTEGER,
    object_id INTEGER,
    planned_amount REAL NOT NULL DEFAULT 0,
    fact_amount REAL NOT NULL DEFAULT 0,
    linked_line_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    uuid TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (counterparty_id) REFERENCES counterparties(id),
    FOREIGN KEY (contract_id) REFERENCES contracts(id),
    FOREIGN KEY (estimate_id) REFERENCES estimates(id),
    FOREIGN KEY (object_id) REFERENCES objects(id),
    FOREIGN KEY (linked_line_id) REFERENCES payment_schedule_lines(id)
);

CREATE TABLE IF NOT EXISTS goods_receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL DEFAULT '',
    date TEXT NOT NULL,
    organization_id INTEGER NOT NULL,
    counterparty_id INTEGER,
    contract_id INTEGER,
    object_id INTEGER,
    estimate_id INTEGER,
    responsible_id INTEGER,
    sum_without_vat REAL NOT NULL DEFAULT 0,
    vat_amount REAL NOT NULL DEFAULT 0,
    sum_with_vat REAL NOT NULL DEFAULT 0,
    due_date TEXT,
    description TEXT,
    is_posted INTEGER NOT NULL DEFAULT 0,
    posted_at TEXT,
    marked_for_deletion INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    uuid TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (organization_id) REFERENCES organizations(id),
    FOREIGN KEY (counterparty_id) REFERENCES counterparties(id),
    FOREIGN KEY (contract_id) REFERENCES contracts(id),
    FOREIGN KEY (object_id) REFERENCES objects(id),
    FOREIGN KEY (estimate_id) REFERENCES estimates(id),
    FOREIGN KEY (responsible_id) REFERENCES persons(id)
);

CREATE TABLE IF NOT EXISTS goods_receipt_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_id INTEGER NOT NULL,
    line_number INTEGER NOT NULL,
    material_id INTEGER,
    name TEXT NOT NULL,
    unit_id INTEGER,
    unit TEXT,
    quantity REAL NOT NULL DEFAULT 0,
    price_without_vat REAL NOT NULL DEFAULT 0,
    vat_rate REAL NOT NULL DEFAULT 20.0,
    vat_amount REAL NOT NULL DEFAULT 0,
    sum_without_vat REAL NOT NULL DEFAULT 0,
    sum_with_vat REAL NOT NULL DEFAULT 0,
    object_id INTEGER,
    drawing_code TEXT,
    note TEXT,
    marked_for_deletion INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    uuid TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (receipt_id) REFERENCES goods_receipts(id) ON DELETE CASCADE,
    FOREIGN KEY (material_id) REFERENCES materials(id),
    FOREIGN KEY (unit_id) REFERENCES units(id),
    FOREIGN KEY (object_id) REFERENCES objects(id)
);

CREATE TABLE IF NOT EXISTS goods_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL DEFAULT '',
    date TEXT NOT NULL,
    organization_id INTEGER NOT NULL,
    counterparty_id INTEGER,
    contract_id INTEGER,
    object_id INTEGER,
    estimate_id INTEGER,
    responsible_id INTEGER,
    sum_without_vat REAL NOT NULL DEFAULT 0,
    vat_amount REAL NOT NULL DEFAULT 0,
    sum_with_vat REAL NOT NULL DEFAULT 0,
    due_date TEXT,
    description TEXT,
    is_posted INTEGER NOT NULL DEFAULT 0,
    posted_at TEXT,
    marked_for_deletion INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    uuid TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (organization_id) REFERENCES organizations(id),
    FOREIGN KEY (counterparty_id) REFERENCES counterparties(id),
    FOREIGN KEY (contract_id) REFERENCES contracts(id),
    FOREIGN KEY (object_id) REFERENCES objects(id),
    FOREIGN KEY (estimate_id) REFERENCES estimates(id),
    FOREIGN KEY (responsible_id) REFERENCES persons(id)
);

CREATE TABLE IF NOT EXISTS goods_issue_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id INTEGER NOT NULL,
    line_number INTEGER NOT NULL,
    material_id INTEGER,
    name TEXT NOT NULL,
    unit_id INTEGER,
    unit TEXT,
    quantity REAL NOT NULL DEFAULT 0,
    price_without_vat REAL NOT NULL DEFAULT 0,
    vat_rate REAL NOT NULL DEFAULT 20.0,
    vat_amount REAL NOT NULL DEFAULT 0,
    sum_without_vat REAL NOT NULL DEFAULT 0,
    sum_with_vat REAL NOT NULL DEFAULT 0,
    object_id INTEGER,
    drawing_code TEXT,
    note TEXT,
    marked_for_deletion INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    uuid TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (issue_id) REFERENCES goods_issues(id) ON DELETE CASCADE,
    FOREIGN KEY (material_id) REFERENCES materials(id),
    FOREIGN KEY (unit_id) REFERENCES units(id),
    FOREIGN KEY (object_id) REFERENCES objects(id)
);

CREATE TABLE IF NOT EXISTS inventory_register (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorder_type TEXT NOT NULL,
    recorder_id INTEGER NOT NULL,
    line_number INTEGER NOT NULL,
    period TEXT NOT NULL,
    material_id INTEGER,
    object_id INTEGER,
    unit_id INTEGER,
    quantity_income REAL NOT NULL DEFAULT 0,
    quantity_expense REAL NOT NULL DEFAULT 0,
    sum_income REAL NOT NULL DEFAULT 0,
    sum_expense REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    uuid TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (material_id) REFERENCES materials(id),
    FOREIGN KEY (object_id) REFERENCES objects(id),
    FOREIGN KEY (unit_id) REFERENCES units(id)
);

CREATE TABLE IF NOT EXISTS mutual_settlements_register (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorder_type TEXT NOT NULL,
    recorder_id INTEGER NOT NULL,
    line_number INTEGER NOT NULL,
    period TEXT NOT NULL,
    organization_id INTEGER NOT NULL,
    counterparty_id INTEGER,
    contract_id INTEGER,
    object_id INTEGER,
    estimate_id INTEGER,
    direction TEXT NOT NULL,
    accrual_amount REAL NOT NULL DEFAULT 0,
    payment_amount REAL NOT NULL DEFAULT 0,
    planned_amount REAL NOT NULL DEFAULT 0,
    linked_line_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    uuid TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (organization_id) REFERENCES organizations(id),
    FOREIGN KEY (counterparty_id) REFERENCES counterparties(id),
    FOREIGN KEY (contract_id) REFERENCES contracts(id),
    FOREIGN KEY (object_id) REFERENCES objects(id),
    FOREIGN KEY (estimate_id) REFERENCES estimates(id)
);

CREATE TABLE IF NOT EXISTS sync_nodes (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    is_local INTEGER NOT NULL DEFAULT 0,
    last_sync_in TEXT,
    last_sync_out TEXT,
    received_packet_no INTEGER NOT NULL DEFAULT 0,
    sent_packet_no INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sync_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_uuid TEXT NOT NULL,
    operation TEXT NOT NULL,
    packet_no INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (node_id) REFERENCES sync_nodes(id)
);

CREATE TABLE IF NOT EXISTS object_version_history (
    id TEXT PRIMARY KEY,
    entity_uuid TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    source_node_id TEXT NOT NULL,
    arrival_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    serialized_data TEXT NOT NULL,
    conflict_resolution TEXT,
    resolved_at TEXT,
    FOREIGN KEY (source_node_id) REFERENCES sync_nodes(id)
);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER NOT NULL,
    form_name TEXT NOT NULL,
    setting_key TEXT NOT NULL,
    setting_value TEXT,
    PRIMARY KEY (user_id, form_name, setting_key),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS constants (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id INTEGER NOT NULL DEFAULT 0,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""

SCHEMA_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_uuid ON users(uuid);
CREATE INDEX IF NOT EXISTS idx_persons_user_id ON persons(user_id);
CREATE INDEX IF NOT EXISTS idx_persons_personnel_number ON persons(personnel_number);
CREATE INDEX IF NOT EXISTS idx_persons_uuid ON persons(uuid);
CREATE INDEX IF NOT EXISTS idx_organizations_uuid ON organizations(uuid);
CREATE INDEX IF NOT EXISTS idx_counterparties_uuid ON counterparties(uuid);
CREATE INDEX IF NOT EXISTS idx_objects_uuid ON objects(uuid);
CREATE INDEX IF NOT EXISTS idx_works_parent_id ON works(parent_id);
CREATE INDEX IF NOT EXISTS idx_works_uuid ON works(uuid);
CREATE INDEX IF NOT EXISTS idx_estimates_date ON estimates(date);
CREATE INDEX IF NOT EXISTS idx_estimates_uuid ON estimates(uuid);
CREATE INDEX IF NOT EXISTS idx_estimate_lines_estimate_id ON estimate_lines(estimate_id);
CREATE INDEX IF NOT EXISTS idx_estimate_lines_uuid ON estimate_lines(uuid);
CREATE INDEX IF NOT EXISTS idx_daily_reports_date ON daily_reports(date);
CREATE INDEX IF NOT EXISTS idx_daily_reports_uuid ON daily_reports(uuid);
CREATE INDEX IF NOT EXISTS idx_daily_report_lines_report_id ON daily_report_lines(report_id);
CREATE INDEX IF NOT EXISTS idx_daily_report_lines_uuid ON daily_report_lines(uuid);
CREATE INDEX IF NOT EXISTS idx_work_execution_period ON work_execution_register(period);
CREATE INDEX IF NOT EXISTS idx_work_execution_uuid ON work_execution_register(uuid);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_units_name ON units(name);
CREATE INDEX IF NOT EXISTS idx_units_uuid ON units(uuid);
CREATE INDEX IF NOT EXISTS idx_materials_name ON materials(name);
CREATE INDEX IF NOT EXISTS idx_materials_code ON materials(code);
CREATE INDEX IF NOT EXISTS idx_materials_uuid ON materials(uuid);
CREATE INDEX IF NOT EXISTS idx_work_specifications_work_id ON work_specifications(work_id);
CREATE INDEX IF NOT EXISTS idx_work_specifications_component_type ON work_specifications(component_type);
CREATE INDEX IF NOT EXISTS idx_work_specifications_material_id ON work_specifications(material_id);
CREATE INDEX IF NOT EXISTS idx_work_specifications_uuid ON work_specifications(uuid);
CREATE INDEX IF NOT EXISTS idx_timesheets_uuid ON timesheets(uuid);
CREATE INDEX IF NOT EXISTS idx_timesheet_lines_uuid ON timesheet_lines(uuid);
CREATE INDEX IF NOT EXISTS idx_payroll_register_uuid ON payroll_register(uuid);
CREATE INDEX IF NOT EXISTS idx_contracts_uuid ON contracts(uuid);
CREATE INDEX IF NOT EXISTS idx_contracts_counterparty_id ON contracts(counterparty_id);
CREATE INDEX IF NOT EXISTS idx_contracts_parent_id ON contracts(parent_id);
CREATE INDEX IF NOT EXISTS idx_payment_schedules_uuid ON payment_schedules(uuid);
CREATE INDEX IF NOT EXISTS idx_payment_schedules_date_from ON payment_schedules(date_from);
CREATE INDEX IF NOT EXISTS idx_payment_schedules_object_id ON payment_schedules(object_id);
CREATE INDEX IF NOT EXISTS idx_payment_schedule_lines_schedule_id ON payment_schedule_lines(schedule_id);
CREATE INDEX IF NOT EXISTS idx_payment_schedule_lines_uuid ON payment_schedule_lines(uuid);
CREATE INDEX IF NOT EXISTS idx_payment_schedule_lines_planned_date ON payment_schedule_lines(planned_date);
CREATE INDEX IF NOT EXISTS idx_payment_transactions_uuid ON payment_transactions(uuid);
CREATE INDEX IF NOT EXISTS idx_payment_transactions_date ON payment_transactions(date);
CREATE INDEX IF NOT EXISTS idx_payment_transactions_linked_line_id ON payment_transactions(linked_line_id);
CREATE INDEX IF NOT EXISTS idx_payment_schedule_register_period ON payment_schedule_register(period);
CREATE INDEX IF NOT EXISTS idx_payment_schedule_register_uuid ON payment_schedule_register(uuid);
CREATE INDEX IF NOT EXISTS idx_payment_schedule_register_recorder ON payment_schedule_register(recorder_type, recorder_id);
CREATE INDEX IF NOT EXISTS idx_payment_schedule_register_counterparty ON payment_schedule_register(counterparty_id);
CREATE INDEX IF NOT EXISTS idx_payment_schedule_register_linked_line ON payment_schedule_register(linked_line_id);
CREATE INDEX IF NOT EXISTS idx_contracts_organization_id ON contracts(organization_id);
CREATE INDEX IF NOT EXISTS idx_contracts_org_cp ON contracts(organization_id, counterparty_id);
CREATE INDEX IF NOT EXISTS idx_goods_receipts_lookup ON goods_receipts(date, organization_id, counterparty_id, contract_id, object_id);
CREATE INDEX IF NOT EXISTS idx_goods_receipts_uuid ON goods_receipts(uuid);
CREATE INDEX IF NOT EXISTS idx_goods_receipt_lines_receipt_id ON goods_receipt_lines(receipt_id);
CREATE INDEX IF NOT EXISTS idx_goods_receipt_lines_uuid ON goods_receipt_lines(uuid);
CREATE INDEX IF NOT EXISTS idx_goods_issues_lookup ON goods_issues(date, organization_id, counterparty_id, contract_id, object_id);
CREATE INDEX IF NOT EXISTS idx_goods_issues_uuid ON goods_issues(uuid);
CREATE INDEX IF NOT EXISTS idx_goods_issue_lines_issue_id ON goods_issue_lines(issue_id);
CREATE INDEX IF NOT EXISTS idx_goods_issue_lines_uuid ON goods_issue_lines(uuid);
CREATE INDEX IF NOT EXISTS idx_inventory_recorder ON inventory_register(recorder_type, recorder_id);
CREATE INDEX IF NOT EXISTS idx_inventory_dims ON inventory_register(period, material_id, object_id);
CREATE INDEX IF NOT EXISTS idx_mutual_recorder ON mutual_settlements_register(recorder_type, recorder_id);
CREATE INDEX IF NOT EXISTS idx_mutual_dims ON mutual_settlements_register(period, organization_id, counterparty_id, contract_id, direction);
CREATE INDEX IF NOT EXISTS idx_sync_changes_entity ON sync_changes(entity_type, entity_uuid);
CREATE INDEX IF NOT EXISTS idx_sync_changes_node_created ON sync_changes(node_id, created_at);
CREATE INDEX IF NOT EXISTS idx_object_version_entity ON object_version_history(entity_type, entity_uuid);
"""

DEFAULT_UNITS = [
    ("m", "m"),
    ("m2", "m2"),
    ("m3", "m3"),
    ("kg", "kg"),
    ("t", "t"),
    ("pcs", "pcs"),
    ("h", "h"),
    ("man-hour", "man-hour"),
]

DEFAULT_MATERIALS = [
    ("M001", "Cement M400", "t", 5000.0),
    ("M002", "River Sand", "t", 800.0),
    ("M003", "Crushed Stone 5-20", "t", 1200.0),
    ("M004", "Rebar A500", "t", 42000.0),
]


def utcnow_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def new_uuid() -> str:
    return str(uuid4())


def get_connection() -> DbConnection:
    """Return a backend connection, applying runtime schema if needed.

    The concrete type depends on ``settings.db_type``: a raw
    ``sqlite3.Connection`` for SQLite, or a ``PostgresConnection`` wrapper for
    PostgreSQL. Both satisfy the :class:`DbConnection` protocol.
    """

    if settings.db_type == "sqlite":
        settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = _backend_connect()
    _ensure_connection_runtime_schema(connection)
    return connection


@contextmanager
def transactional_connection() -> Iterator[DbConnection]:
    connection = get_connection()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def row_to_dict(row: Any | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def rows_to_dicts(rows: list[Any]) -> list[dict[str, Any]]:
    return [row_to_dict(row) or {} for row in rows]


def last_insert_id(connection: DbConnection) -> int:
    """Return the id generated by the most recent INSERT in this session.

    Thin backend-aware wrapper so callers can use a single argument.
    """

    return _dialect_last_insert_id(connection, settings.db_type)


def initialize_database() -> None:
    # The file-existence / destructive reset path only applies to file-based
    # (SQLite) backends. Server backends rely on idempotent DDL below.
    if settings.db_type == "sqlite" and settings.database_path.exists():
        connection = _backend_connect()
        try:
            if not _is_uuid_ready_schema(connection):
                connection.close()
                if settings.reset_database_on_schema_mismatch:
                    _delete_database_files()
                else:
                    print(
                        "Database schema mismatch detected; preserving existing database and applying runtime schema updates."
                    )
            else:
                connection.close()
        except Exception:
            connection.close()
            raise

    with transactional_connection() as connection:
        connection.executescript(SCHEMA_TABLES_SQL)
        ensure_runtime_schema(connection)
        connection.executescript(SCHEMA_INDEXES_SQL)
        if settings.allow_seed_data:
            seed_database(connection)


def _table_columns(connection: DbConnection, table_name: str) -> set[str]:
    return table_columns(connection, table_name, settings.db_type)


def _table_exists(connection: DbConnection, table_name: str) -> bool:
    return table_exists(connection, table_name, settings.db_type)


def _ensure_column(connection: DbConnection, table_name: str, column_name: str, definition: str) -> None:
    if column_name in _table_columns(connection, table_name):
        return
    connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def _ensure_connection_runtime_schema(connection: DbConnection) -> None:
    if not _table_exists(connection, "constants"):
        return
    if not _table_exists(connection, "persons"):
        return

    person_columns = _table_columns(connection, "persons")
    if "hourly_rate" in person_columns and "personnel_number" in person_columns:
        return

    ensure_runtime_schema(connection)
    connection.executescript(SCHEMA_INDEXES_SQL)
    connection.commit()


def _get_constant(connection: sqlite3.Connection, key: str) -> str | None:
    if not _table_exists(connection, "constants"):
        return None
    row = connection.execute("SELECT value FROM constants WHERE key = ?", (key,)).fetchone()
    return None if row is None else str(row["value"])


def _set_constant(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute(
        """
        INSERT INTO constants (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


def _is_uuid_ready_schema(connection: sqlite3.Connection) -> bool:
    if _get_constant(connection, "schema.version") == SYNC_SCHEMA_VERSION:
        return True

    required_tables = {"sync_nodes", "sync_changes", "object_version_history"}
    if any(not _table_exists(connection, table) for table in required_tables):
        return False

    required_columns = {
        "persons": {"uuid", "updated_at", "is_deleted"},
        "works": {"uuid", "updated_at", "is_deleted"},
        "estimates": {"uuid", "updated_at", "is_deleted"},
        "daily_reports": {"uuid", "updated_at", "is_deleted"},
    }
    for table_name, columns in required_columns.items():
        if not _table_exists(connection, table_name):
            return False
        table_columns = _table_columns(connection, table_name)
        if not columns.issubset(table_columns):
            return False
    return True


def _delete_database_files() -> None:
    base = settings.database_path
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(f"{base}{suffix}")
        if candidate.exists():
            candidate.unlink()


def ensure_runtime_schema(connection: sqlite3.Connection) -> None:
    for table_name in UUID_READY_TABLES:
        _ensure_sync_columns(connection, table_name)
    if _table_exists(connection, "persons"):
        _ensure_column(connection, "persons", "personnel_number", "TEXT")
        _ensure_column(connection, "persons", "hourly_rate", "REAL NOT NULL DEFAULT 0")
    if _table_exists(connection, "works"):
        _ensure_column(connection, "works", "specification_review_status", "TEXT NOT NULL DEFAULT 'ok'")
        _ensure_column(connection, "works", "specification_review_note", "TEXT")
        connection.execute(
            """
            UPDATE works
            SET specification_review_status = COALESCE(NULLIF(TRIM(specification_review_status), ''), 'ok')
            """
        )
    for table_name in ("estimate_lines", "daily_report_lines"):
        if _table_exists(connection, table_name) and "marked_for_deletion" not in _table_columns(connection, table_name):
            _ensure_column(connection, table_name, "marked_for_deletion", "INTEGER NOT NULL DEFAULT 0")
    if _table_exists(connection, "estimates"):
        _ensure_column(connection, "estimates", "contract_id", "INTEGER")
    if _table_exists(connection, "daily_reports"):
        _ensure_column(connection, "daily_reports", "supplementary_agreement_id", "INTEGER")
    if _table_exists(connection, "daily_report_lines"):
        _ensure_column(connection, "daily_report_lines", "quantity", "REAL NOT NULL DEFAULT 0")
        _ensure_column(connection, "daily_report_lines", "unit", "TEXT")
        _ensure_column(connection, "daily_report_lines", "price", "REAL NOT NULL DEFAULT 0")
        _ensure_column(connection, "daily_report_lines", "actual_sum", "REAL NOT NULL DEFAULT 0")

    if _table_exists(connection, "contracts"):
        _ensure_column(connection, "contracts", "organization_id", "INTEGER")
        _ensure_column(connection, "contracts", "kind", "TEXT NOT NULL DEFAULT 'supply'")
        _ensure_column(connection, "contracts", "currency", "TEXT NOT NULL DEFAULT 'RUB'")
        _ensure_column(connection, "contracts", "vat_rate", "REAL NOT NULL DEFAULT 20.0")
        _ensure_column(connection, "contracts", "payment_deferral_days", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(connection, "contracts", "agreement_date", "TEXT")
        _ensure_column(connection, "contracts", "valid_until", "TEXT")

    _set_constant(connection, "schema.version", SYNC_SCHEMA_VERSION)
    seed_runtime_catalogs(connection)
    ensure_local_sync_node(connection)


def _ensure_sync_columns(connection: sqlite3.Connection, table_name: str) -> None:
    if not _table_exists(connection, table_name):
        return

    table_columns = _table_columns(connection, table_name)
    if "uuid" not in table_columns:
        _ensure_column(connection, table_name, "uuid", "TEXT")
    if "updated_at" not in table_columns:
        _ensure_column(connection, table_name, "updated_at", "TEXT")
    if "is_deleted" not in table_columns:
        _ensure_column(connection, table_name, "is_deleted", "INTEGER NOT NULL DEFAULT 0")
    if "created_at" in table_columns and "modified_at" not in table_columns:
        _ensure_column(connection, table_name, "modified_at", "TEXT")

    refresh_columns = _table_columns(connection, table_name)
    assignments: list[str] = []
    if "uuid" in refresh_columns:
        assignments.append("uuid = COALESCE(uuid, ?)")
    if "modified_at" in refresh_columns:
        if "created_at" in refresh_columns:
            assignments.append("modified_at = COALESCE(modified_at, created_at, ?)")
        else:
            assignments.append("modified_at = COALESCE(modified_at, ?)")
    if "updated_at" in refresh_columns:
        if "modified_at" in refresh_columns:
            assignments.append("updated_at = COALESCE(updated_at, modified_at, ?)")
        elif "created_at" in refresh_columns:
            assignments.append("updated_at = COALESCE(updated_at, created_at, ?)")
        else:
            assignments.append("updated_at = COALESCE(updated_at, ?)")

    if not assignments:
        return

    rows = connection.execute(f"SELECT id, uuid FROM {table_name}").fetchall()
    for row in rows:
        params: list[Any] = []
        for assignment in assignments:
            if "uuid = COALESCE(uuid, ?)" in assignment:
                params.append(new_uuid())
            else:
                params.append(utcnow_iso())
        params.append(row["id"])
        connection.execute(
            f"UPDATE {table_name} SET {', '.join(assignments)} WHERE id = ?",
            params,
        )


def local_db_label() -> str:
    """A short identifier for the local database, backend-aware."""

    if settings.db_type == "postgresql":
        return settings.postgres_db.strip() or "ctm"
    return settings.database_path.stem.strip() or "ctm"


def local_sync_node_code() -> str:
    stem = local_db_label()
    sanitized = "".join(char if char.isalnum() else "-" for char in stem.upper()).strip("-")
    return f"LOCAL-{sanitized or 'CTM'}"


def ensure_local_sync_node(connection: sqlite3.Connection) -> dict[str, Any]:
    node_id = _get_constant(connection, "sync.local_node_id")
    if node_id:
        row = connection.execute("SELECT * FROM sync_nodes WHERE id = ?", (node_id,)).fetchone()
        if row is not None:
            return row_to_dict(row) or {}

    code = local_sync_node_code()
    row = connection.execute("SELECT * FROM sync_nodes WHERE code = ?", (code,)).fetchone()
    now = utcnow_iso()
    if row is None:
        node_id = new_uuid()
        connection.execute(
            """
            INSERT INTO sync_nodes (
                id, code, name, is_local, created_at, updated_at
            ) VALUES (?, ?, ?, 1, ?, ?)
            """,
            (node_id, code, f"Local node for {local_db_label()}", now, now),
        )
    else:
        node_id = str(row["id"])
        connection.execute(
            "UPDATE sync_nodes SET is_local = 1, updated_at = ? WHERE id = ?",
            (now, node_id),
        )

    connection.execute("UPDATE sync_nodes SET is_local = 0 WHERE id <> ?", (node_id,))
    _set_constant(connection, "sync.local_node_id", node_id)
    row = connection.execute("SELECT * FROM sync_nodes WHERE id = ?", (node_id,)).fetchone()
    return row_to_dict(row) or {}


def get_local_sync_node(connection: sqlite3.Connection) -> dict[str, Any]:
    row = connection.execute("SELECT * FROM sync_nodes WHERE is_local = 1 LIMIT 1").fetchone()
    if row is not None:
        return row_to_dict(row) or {}
    return ensure_local_sync_node(connection)


def register_sync_change(
    connection: sqlite3.Connection,
    *,
    entity_type: str,
    entity_uuid: str,
    operation: str,
) -> None:
    operation_value = operation.upper().strip()
    if operation_value not in SYNC_OPERATIONS:
        raise ValueError(f"Unsupported sync operation: {operation}")
    local_node = get_local_sync_node(connection)
    connection.execute(
        """
        INSERT INTO sync_changes (node_id, entity_type, entity_uuid, operation, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (local_node["id"], entity_type, entity_uuid, operation_value, utcnow_iso()),
    )


def seed_runtime_catalogs(connection: sqlite3.Connection) -> None:
    # Import locally to avoid a module-level cycle with api.work_services.
    from api.work_services import _normalize_unit_name

    def unit_key(value: str | None) -> str:
        return _normalize_unit_name(value or "")

    existing_units: dict[str, int] = {}
    preferred_names: dict[str, str] = {}
    for row in connection.execute(
        "SELECT id, name FROM units WHERE marked_for_deletion = 0 ORDER BY id ASC"
    ).fetchall():
        if not row["name"]:
            continue
        key = unit_key(row["name"])
        if not key:
            continue
        current_name = str(row["name"])
        if key not in existing_units or (current_name == key and preferred_names.get(key) != key):
            existing_units[key] = int(row["id"])
            preferred_names[key] = current_name

    for name, short_name in DEFAULT_UNITS:
        key = unit_key(name)
        if key in existing_units:
            continue
        now = utcnow_iso()
        connection.execute(
            """
            INSERT INTO units (name, short_name, created_at, modified_at, uuid, updated_at, is_deleted)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (key, unit_key(short_name) or key, now, now, new_uuid(), now),
        )
        existing_units[key] = last_insert_id(connection)
        preferred_names[key] = key

    work_units = [
        row["unit"].strip()
        for row in connection.execute(
            "SELECT DISTINCT unit FROM works WHERE unit IS NOT NULL AND TRIM(unit) != ''"
        ).fetchall()
    ]
    for unit_name in work_units:
        key = unit_key(unit_name)
        if not key or key in existing_units:
            continue
        now = utcnow_iso()
        connection.execute(
            """
            INSERT INTO units (name, short_name, created_at, modified_at, uuid, updated_at, is_deleted)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (key, key, now, now, new_uuid(), now),
        )
        existing_units[key] = last_insert_id(connection)
        preferred_names[key] = key

    existing_materials = {
        row["name"].strip().lower()
        for row in connection.execute("SELECT name FROM materials WHERE marked_for_deletion = 0").fetchall()
        if row["name"]
    }
    for code, name, unit_name, price in DEFAULT_MATERIALS:
        if name.strip().lower() in existing_materials:
            continue
        unit_id = existing_units.get(unit_key(unit_name))
        now = utcnow_iso()
        connection.execute(
            """
            INSERT INTO materials (code, name, unit_id, price, created_at, modified_at, uuid, updated_at, is_deleted)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (code, name, unit_id, price, now, now, new_uuid(), now),
        )
        existing_materials.add(name.strip().lower())

    for row in connection.execute(
        """
        SELECT DISTINCT ws.unit_id
        FROM work_specifications ws
        LEFT JOIN units u ON u.id = ws.unit_id
        WHERE ws.unit_id IS NOT NULL AND u.id IS NULL
        """
    ).fetchall():
        now = utcnow_iso()
        connection.execute(
            """
            INSERT INTO units (id, name, short_name, created_at, modified_at, uuid, updated_at, is_deleted)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (row["unit_id"], f"Unit {row['unit_id']}", f"Unit {row['unit_id']}", now, now, new_uuid(), now),
        )

    for row in connection.execute(
        """
        SELECT ws.material_id, ws.component_name, ws.unit_id, ws.unit_price
        FROM work_specifications ws
        LEFT JOIN materials m ON m.id = ws.material_id
        WHERE ws.material_id IS NOT NULL AND m.id IS NULL
        GROUP BY ws.material_id, ws.component_name, ws.unit_id, ws.unit_price
        """
    ).fetchall():
        now = utcnow_iso()
        connection.execute(
            """
            INSERT INTO materials (
                id, code, name, unit_id, price, created_at, modified_at, uuid, updated_at, is_deleted
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                row["material_id"],
                f"AUTO-{row['material_id']}",
                row["component_name"] or f"Material {row['material_id']}",
                row["unit_id"],
                float(row["unit_price"] or 0),
                now,
                now,
                new_uuid(),
                now,
            ),
        )


def _user_exists(connection: sqlite3.Connection, username: str) -> bool:
    row = connection.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
    return row is not None


def seed_database(connection: sqlite3.Connection) -> None:
    if _user_exists(connection, "admin"):
        return

    now = utcnow_iso()
    admin_hash = hash_password("admin")
    manager_hash = hash_password("manager")
    foreman_hash = hash_password("foreman")

    connection.executemany(
        """
        INSERT INTO users (
            username, password_hash, role, is_active, created_at, modified_at, uuid, updated_at, is_deleted
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        [
            ("admin", admin_hash, "admin", 1, now, now, new_uuid(), now),
            ("manager", manager_hash, "manager", 1, now, now, new_uuid(), now),
            ("foreman", foreman_hash, "foreman", 1, now, now, new_uuid(), now),
        ],
    )

    users = {
        row["username"]: row["id"]
        for row in connection.execute("SELECT id, username FROM users").fetchall()
    }

    connection.executemany(
        """
        INSERT INTO persons (
            full_name, position, phone, hourly_rate, user_id, marked_for_deletion, is_group,
            created_at, modified_at, uuid, updated_at, is_deleted
        )
        VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?, 0)
        """,
        [
            ("CTM Administrator", "Administrator", "+7 900 111-11-11", 0, users["admin"], now, now, new_uuid(), now),
            ("Project Manager", "Manager", "+7 900 222-22-22", 420, users["manager"], now, now, new_uuid(), now),
            ("Site Foreman", "Foreman", "+7 900 333-33-33", 350, users["foreman"], now, now, new_uuid(), now),
        ],
    )

    person_ids = {
        row["full_name"]: row["id"]
        for row in connection.execute("SELECT id, full_name FROM persons").fetchall()
    }

    connection.execute(
        """
        INSERT INTO organizations (
            name, inn, default_responsible_id, marked_for_deletion, is_group,
            created_at, modified_at, uuid, updated_at, is_deleted
        ) VALUES (?, ?, ?, 0, 0, ?, ?, ?, ?, 0)
        """,
        ("MonтажСтрой LLC", "3010010010", person_ids["Project Manager"], now, now, new_uuid(), now),
    )
    connection.execute(
        """
        INSERT INTO counterparties (
            name, inn, contact_person, phone, marked_for_deletion, is_group,
            created_at, modified_at, uuid, updated_at, is_deleted
        ) VALUES (?, ?, ?, ?, 0, 0, ?, ?, ?, ?, 0)
        """,
        ("Alpha Development LLC", "3020020020", "Sidorov S.S.", "+7 900 444-44-44", now, now, new_uuid(), now),
    )
    connection.execute(
        """
        INSERT INTO objects (
            name, address, owner_id, marked_for_deletion, is_group,
            created_at, modified_at, uuid, updated_at, is_deleted
        )
        VALUES (?, ?, (SELECT id FROM counterparties WHERE name = ?), 0, 0, ?, ?, ?, ?, 0)
        """,
        ("North ЖК", "Astrakhan, Stroiteley 12", "Alpha Development LLC", now, now, new_uuid(), now),
    )
    connection.executemany(
        """
        INSERT INTO works (
            name, code, unit, price, labor_rate, marked_for_deletion, is_group,
            created_at, modified_at, uuid, updated_at, is_deleted
        ) VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?, 0)
        """,
        [
            ("Brickwork", "W-001", "m2", 1250.0, 6.0, now, now, new_uuid(), now),
            ("Wall Plastering", "W-002", "m2", 840.0, 3.5, now, now, new_uuid(), now),
            ("Slab Installation", "W-003", "m2", 1460.0, 7.0, now, now, new_uuid(), now),
        ],
    )

    connection.execute(
        """
        INSERT INTO estimates (
            number, date, customer_id, object_id, contractor_id, responsible_id, total_sum, total_labor,
            is_posted, marked_for_deletion, created_at, modified_at, uuid, updated_at, is_deleted
        )
        VALUES (
            'EST-001',
            '2026-04-20',
            (SELECT id FROM counterparties WHERE name = 'Alpha Development LLC'),
            (SELECT id FROM objects WHERE name = 'North ЖК'),
            (SELECT id FROM organizations WHERE name = 'MonтажСтрой LLC'),
            ?,
            56700.0,
            252.0,
            0,
            0,
            ?,
            ?,
            ?,
            ?,
            0
        )
        """,
        (person_ids["Project Manager"], now, now, new_uuid(), now),
    )

    estimate_id = int(connection.execute("SELECT id FROM estimates WHERE number = 'EST-001'").fetchone()["id"])
    works = {
        row["name"]: row["id"]
        for row in connection.execute("SELECT id, name FROM works").fetchall()
    }
    connection.executemany(
        """
        INSERT INTO estimate_lines (
            estimate_id, line_number, work_id, quantity, unit, price, labor_rate, sum, planned_labor,
            is_group, group_name, parent_group_id, is_collapsed, created_at, modified_at, uuid, updated_at, is_deleted
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        [
            (estimate_id, 1, works["Brickwork"], 20.0, "m2", 1250.0, 6.0, 25000.0, 120.0, 0, None, None, 0, now, now, new_uuid(), now),
            (estimate_id, 2, works["Wall Plastering"], 15.0, "m2", 840.0, 3.5, 12600.0, 52.5, 0, None, None, 0, now, now, new_uuid(), now),
            (estimate_id, 3, works["Slab Installation"], 13.0, "m2", 1460.0, 6.1153846154, 18980.0, 79.5, 0, None, None, 0, now, now, new_uuid(), now),
        ],
    )

    connection.execute(
        """
        INSERT INTO daily_reports (
            number, date, estimate_id, foreman_id, is_posted, marked_for_deletion,
            created_at, modified_at, uuid, updated_at, is_deleted
        ) VALUES ('DR-001', '2026-04-20', ?, ?, 0, 0, ?, ?, ?, ?, 0)
        """,
        (estimate_id, person_ids["Site Foreman"], now, now, new_uuid(), now),
    )
    report_id = int(connection.execute("SELECT id FROM daily_reports WHERE number = 'DR-001'").fetchone()["id"])
    connection.executemany(
        """
        INSERT INTO daily_report_lines (
            report_id, line_number, work_id, planned_labor, actual_labor, deviation_percent,
            is_group, group_name, parent_group_id, is_collapsed, created_at, modified_at, uuid, updated_at, is_deleted
        )
        VALUES (?, ?, ?, ?, ?, ?, 0, NULL, NULL, 0, ?, ?, ?, ?, 0)
        """,
        [
            (report_id, 1, works["Brickwork"], 120.0, 24.0, -80.0, now, now, new_uuid(), now),
            (report_id, 2, works["Wall Plastering"], 52.5, 12.0, -77.14, now, now, new_uuid(), now),
        ],
    )
    report_lines = connection.execute(
        "SELECT id FROM daily_report_lines WHERE report_id = ? ORDER BY line_number",
        (report_id,),
    ).fetchall()
    connection.executemany(
        "INSERT INTO daily_report_executors (report_line_id, executor_id) VALUES (?, ?)",
        [
            (report_lines[0]["id"], person_ids["Site Foreman"]),
            (report_lines[1]["id"], person_ids["Site Foreman"]),
        ],
    )


def database_exists() -> bool:
    if settings.db_type == "sqlite":
        return Path(settings.database_path).exists()
    # Server backends: existence is implied by connectability. The startup flow
    # uses this to decide whether to seed; CREATE TABLE IF NOT EXISTS makes the
    # server path idempotent regardless.
    return True
