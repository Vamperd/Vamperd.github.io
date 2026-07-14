"""Private, localhost-only TODO application.

Run with: python todo_app/server.py
"""

from __future__ import annotations

import argparse
import calendar
import json
import os
import secrets
import sqlite3
import sys
import threading
import webbrowser
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


APP_DIR = Path(__file__).resolve().parent
REPO_DIR = APP_DIR.parent
STATIC_DIR = APP_DIR / "static"
DEFAULT_DATA_DIR = REPO_DIR / "local" / "todo"
CN_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")
DOMAINS = {"daily_life", "robomaster_team", "phd_learning"}
CADENCES = {"daily", "long_term"}
MAX_BODY_BYTES = 512 * 1024


def now_cn() -> datetime:
    return datetime.now(CN_TZ)


def iso_now() -> str:
    return now_cn().isoformat(timespec="seconds")


def today_cn() -> date:
    return now_cn().date()


def parse_day(value: str | None, *, field: str = "date") -> date:
    if not value:
        return today_cn()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid {field}; expected YYYY-MM-DD") from exc


def normalize_optional_day(value: object, *, field: str) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a date string")
    return parse_day(value, field=field).isoformat()


class TodoStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.RLock()
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _initialize(self) -> None:
        with self._write_lock, closing(self.connect()) as db:
            db.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 200),
                    details TEXT NOT NULL DEFAULT '' CHECK(length(details) <= 4000),
                    domain TEXT NOT NULL CHECK(domain IN ('daily_life','robomaster_team','phd_learning')),
                    cadence TEXT NOT NULL CHECK(cadence IN ('daily','long_term')),
                    position INTEGER NOT NULL DEFAULT 0,
                    due_date TEXT,
                    active_from TEXT NOT NULL,
                    paused_at TEXT,
                    completed_at TEXT,
                    archived_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS daily_checkins (
                    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    check_date TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    PRIMARY KEY (task_id, check_date)
                );
                CREATE TABLE IF NOT EXISTS task_pauses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    started_on TEXT NOT NULL,
                    ended_on TEXT
                );
                CREATE TABLE IF NOT EXISTS task_groups (
                    task_id INTEGER PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
                    mode TEXT NOT NULL CHECK(mode IN ('daily_rotation','long_term_focus')),
                    focused_item_id INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS group_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER NOT NULL REFERENCES task_groups(task_id) ON DELETE CASCADE,
                    title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 200),
                    details TEXT NOT NULL DEFAULT '' CHECK(length(details) <= 4000),
                    item_type TEXT NOT NULL CHECK(item_type IN ('task','rest')),
                    position INTEGER NOT NULL DEFAULT 0,
                    completed_at TEXT,
                    archived_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS group_item_checkins (
                    item_id INTEGER NOT NULL REFERENCES group_items(id) ON DELETE CASCADE,
                    check_date TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    PRIMARY KEY (item_id, check_date)
                );
                CREATE TABLE IF NOT EXISTS rotation_assignments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER NOT NULL REFERENCES task_groups(task_id) ON DELETE CASCADE,
                    item_id INTEGER NOT NULL REFERENCES group_items(id),
                    starts_on TEXT NOT NULL,
                    resolved_on TEXT,
                    resolution TEXT CHECK(resolution IN ('completed','rest','skipped')),
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_scope
                    ON tasks(domain, cadence, archived_at, position);
                CREATE INDEX IF NOT EXISTS idx_checkins_date
                    ON daily_checkins(check_date);
                CREATE INDEX IF NOT EXISTS idx_pauses_task
                    ON task_pauses(task_id, started_on, ended_on);
                CREATE INDEX IF NOT EXISTS idx_group_items_scope
                    ON group_items(group_id, archived_at, position);
                CREATE INDEX IF NOT EXISTS idx_group_checkins_date
                    ON group_item_checkins(check_date);
                CREATE INDEX IF NOT EXISTS idx_rotation_group_day
                    ON rotation_assignments(group_id, starts_on, id);
                """
            )
            db.commit()

    def backup_once_per_day(self, backup_dir: Path) -> Path | None:
        backup_dir.mkdir(parents=True, exist_ok=True)
        destination = backup_dir / f"todo-{today_cn().isoformat()}.sqlite3"
        if destination.exists():
            return None
        with self._write_lock, closing(self.connect()) as source:
            target = sqlite3.connect(destination)
            try:
                source.backup(target)
            finally:
                target.close()
        return destination

    @staticmethod
    def _task_to_dict(row: sqlite3.Row, complete: bool = False) -> dict:
        task = dict(row)
        task["is_complete"] = bool(complete)
        task["is_paused"] = bool(task.get("paused_at"))
        return task

    @staticmethod
    def _is_paused_on(pauses: list[sqlite3.Row], day: date) -> bool:
        day_s = day.isoformat()
        return any(
            pause["started_on"] <= day_s
            and (pause["ended_on"] is None or day_s < pause["ended_on"])
            for pause in pauses
        )

    @staticmethod
    def _active_group_items(db: sqlite3.Connection, group_id: int) -> list[sqlite3.Row]:
        return db.execute(
            """
            SELECT * FROM group_items
            WHERE group_id = ? AND archived_at IS NULL
            ORDER BY position, id
            """,
            (group_id,),
        ).fetchall()

    @classmethod
    def _next_rotation_item(
        cls, db: sqlite3.Connection, group_id: int, current_item_id: int
    ) -> sqlite3.Row:
        items = cls._active_group_items(db, group_id)
        if not items:
            raise ValueError("A task group needs at least one active item")
        for index, item in enumerate(items):
            if item["id"] == current_item_id:
                return items[(index + 1) % len(items)]
        previous = db.execute(
            "SELECT position FROM group_items WHERE id = ? AND group_id = ?",
            (current_item_id, group_id),
        ).fetchone()
        if previous:
            for item in items:
                if item["position"] > previous["position"]:
                    return item
        return items[0]

    @staticmethod
    def _assignment_for_day(
        db: sqlite3.Connection, group_id: int, selected_day: date
    ) -> sqlite3.Row | None:
        return db.execute(
            """
            SELECT a.*, i.title AS item_title, i.item_type, i.archived_at AS item_archived_at
            FROM rotation_assignments a
            JOIN group_items i ON i.id = a.item_id
            WHERE a.group_id = ? AND a.starts_on <= ?
            ORDER BY a.starts_on DESC, a.id DESC
            LIMIT 1
            """,
            (group_id, selected_day.isoformat()),
        ).fetchone()

    def _ensure_rotation_assignment(
        self, db: sqlite3.Connection, group_id: int, starts_on: str
    ) -> None:
        exists = db.execute(
            "SELECT 1 FROM rotation_assignments WHERE group_id = ? LIMIT 1",
            (group_id,),
        ).fetchone()
        if exists:
            return
        items = self._active_group_items(db, group_id)
        if not items:
            raise ValueError("A daily group needs at least one sequence item")
        db.execute(
            """
            INSERT INTO rotation_assignments(group_id, item_id, starts_on, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (group_id, items[0]["id"], starts_on, iso_now()),
        )

    def _sync_daily_groups(self, db: sqlite3.Connection, through_day: date) -> None:
        groups = db.execute(
            """
            SELECT g.task_id, t.active_from
            FROM task_groups g
            JOIN tasks t ON t.id = g.task_id
            WHERE g.mode = 'daily_rotation'
              AND t.archived_at IS NULL
              AND t.paused_at IS NULL
              AND t.active_from <= ?
            """,
            (through_day.isoformat(),),
        ).fetchall()
        for group in groups:
            self._ensure_rotation_assignment(db, group["task_id"], group["active_from"])
            for _ in range(1000):
                assignment = db.execute(
                    """
                    SELECT a.*, i.item_type
                    FROM rotation_assignments a
                    JOIN group_items i ON i.id = a.item_id
                    WHERE a.group_id = ?
                    ORDER BY a.starts_on DESC, a.id DESC
                    LIMIT 1
                    """,
                    (group["task_id"],),
                ).fetchone()
                if (
                    not assignment
                    or assignment["item_type"] != "rest"
                    or assignment["starts_on"] > through_day.isoformat()
                ):
                    break
                rest_day = date.fromisoformat(assignment["starts_on"])
                timestamp = iso_now()
                if not assignment["resolved_on"]:
                    db.execute(
                        """
                        UPDATE rotation_assignments
                        SET resolved_on = ?, resolution = 'rest'
                        WHERE id = ?
                        """,
                        (rest_day.isoformat(), assignment["id"]),
                    )
                    db.execute(
                        """
                        INSERT OR IGNORE INTO daily_checkins(task_id, check_date, completed_at)
                        VALUES (?, ?, ?)
                        """,
                        (group["task_id"], rest_day.isoformat(), timestamp),
                    )
                later = db.execute(
                    "SELECT 1 FROM rotation_assignments WHERE group_id = ? AND id > ? LIMIT 1",
                    (group["task_id"], assignment["id"]),
                ).fetchone()
                if not later:
                    next_item = self._next_rotation_item(
                        db, group["task_id"], assignment["item_id"]
                    )
                    db.execute(
                        """
                        INSERT INTO rotation_assignments(group_id, item_id, starts_on, created_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            group["task_id"],
                            next_item["id"],
                            (rest_day + timedelta(days=1)).isoformat(),
                            timestamp,
                        ),
                    )
            else:  # pragma: no cover - defensive guard for corrupt all-rest sequences
                raise RuntimeError("Rotation contains too many consecutive rest steps")

    def state(self, day: date | None = None) -> dict:
        selected_day = day or today_cn()
        day_s = selected_day.isoformat()
        with self._write_lock, closing(self.connect()) as db:
            self._sync_daily_groups(db, min(selected_day, today_cn()))
            db.commit()
            rows = db.execute(
                """
                SELECT t.*,
                       CASE WHEN c.task_id IS NULL THEN 0 ELSE 1 END AS checked_today
                FROM tasks t
                LEFT JOIN daily_checkins c
                  ON c.task_id = t.id AND c.check_date = ?
                WHERE t.archived_at IS NULL
                ORDER BY t.domain, t.cadence, t.position, t.id
                """,
                (day_s,),
            ).fetchall()
            pauses = db.execute(
                "SELECT task_id, started_on, ended_on FROM task_pauses"
            ).fetchall()
            group_rows = db.execute("SELECT * FROM task_groups").fetchall()
            item_rows = db.execute(
                """
                SELECT * FROM group_items
                WHERE archived_at IS NULL
                ORDER BY group_id, position, id
                """
            ).fetchall()
            item_checkins = db.execute(
                "SELECT item_id FROM group_item_checkins WHERE check_date = ?",
                (day_s,),
            ).fetchall()

        pauses_by_task: dict[int, list[sqlite3.Row]] = {}
        for pause in pauses:
            pauses_by_task.setdefault(pause["task_id"], []).append(pause)

        groups_by_task = {row["task_id"]: row for row in group_rows}
        items_by_group: dict[int, list[sqlite3.Row]] = {}
        for item in item_rows:
            items_by_group.setdefault(item["group_id"], []).append(item)
        checked_items = {row["item_id"] for row in item_checkins}

        tasks = []
        for row in rows:
            task_day = date.fromisoformat(row["active_from"])
            if row["cadence"] == "daily":
                if task_day > selected_day:
                    continue
                paused_on_day = self._is_paused_on(
                    pauses_by_task.get(row["id"], []), selected_day
                )
                complete = bool(row["checked_today"])
            else:
                paused_on_day = False
                complete = bool(row["completed_at"])
            task = self._task_to_dict(row, complete)
            task["is_paused"] = paused_on_day
            group = groups_by_task.get(row["id"])
            task["task_type"] = "group" if group else "standalone"
            if group:
                assignment = None
                if group["mode"] == "daily_rotation":
                    with closing(self.connect()) as lookup:
                        assignment = self._assignment_for_day(
                            lookup, row["id"], selected_day
                        )
                children = []
                for item in items_by_group.get(row["id"], []):
                    child = dict(item)
                    child["is_complete"] = (
                        bool(item["completed_at"])
                        if group["mode"] == "long_term_focus"
                        else item["id"] in checked_items
                    )
                    child["is_active"] = bool(
                        assignment
                        and assignment["item_type"] == "task"
                        and assignment["item_id"] == item["id"]
                    )
                    child["is_focused"] = bool(
                        group["focused_item_id"] == item["id"]
                    )
                    children.append(child)
                action_children = [item for item in children if item["item_type"] == "task"]
                completed_children = sum(
                    1 for item in action_children if item["is_complete"]
                )
                task["group"] = {
                    "mode": group["mode"],
                    "children": children,
                    "active_item_id": (
                        assignment["item_id"]
                        if assignment and assignment["item_type"] == "task"
                        else None
                    ),
                    "focused_item_id": group["focused_item_id"],
                    "is_rest_day": bool(
                        assignment and assignment["item_type"] == "rest"
                    ),
                    "rest_title": (
                        assignment["item_title"]
                        if assignment and assignment["item_type"] == "rest"
                        else None
                    ),
                    "completed_item_id": next(
                        (item["id"] for item in children if item["id"] in checked_items),
                        None,
                    ),
                    "progress": {
                        "completed": completed_children,
                        "total": len(action_children),
                    },
                }
            tasks.append(task)

        daily_tasks = [
            t for t in tasks if t["cadence"] == "daily" and not t["is_paused"]
        ]
        completed = sum(1 for task in daily_tasks if task["is_complete"])
        return {
            "today": today_cn().isoformat(),
            "selected_date": day_s,
            "tasks": tasks,
            "daily_progress": {
                "completed": completed,
                "total": len(daily_tasks),
            },
        }

    def calendar_month(self, year: int, month: int) -> dict:
        if year < 2000 or year > 2200 or month < 1 or month > 12:
            raise ValueError("Invalid calendar month")
        first = date(year, month, 1)
        last = date(year, month, calendar.monthrange(year, month)[1])
        today = today_cn()

        with closing(self.connect()) as db:
            tasks = db.execute(
                """
                SELECT * FROM tasks
                WHERE cadence = 'daily'
                  AND active_from <= ?
                  AND (archived_at IS NULL OR substr(archived_at, 1, 10) > ?)
                """,
                (last.isoformat(), first.isoformat()),
            ).fetchall()
            checkins = db.execute(
                """
                SELECT task_id, check_date FROM daily_checkins
                WHERE check_date BETWEEN ? AND ?
                """,
                (first.isoformat(), last.isoformat()),
            ).fetchall()
            pauses = db.execute(
                """
                SELECT task_id, started_on, ended_on FROM task_pauses
                WHERE started_on <= ? AND (ended_on IS NULL OR ended_on > ?)
                """,
                (last.isoformat(), first.isoformat()),
            ).fetchall()

        checked = {(row["task_id"], row["check_date"]) for row in checkins}
        pauses_by_task: dict[int, list[sqlite3.Row]] = {}
        for pause in pauses:
            pauses_by_task.setdefault(pause["task_id"], []).append(pause)

        days = []
        cursor = first
        while cursor <= last:
            eligible = []
            for task in tasks:
                if task["active_from"] > cursor.isoformat():
                    continue
                if task["archived_at"] and task["archived_at"][:10] <= cursor.isoformat():
                    continue
                if self._is_paused_on(pauses_by_task.get(task["id"], []), cursor):
                    continue
                eligible.append(task)
            completed = sum(
                1 for task in eligible if (task["id"], cursor.isoformat()) in checked
            )
            total = len(eligible)
            if total == 0:
                status = "empty"
            elif completed == total:
                status = "complete"
            elif cursor > today:
                status = "future"
            elif cursor == today:
                status = "in_progress"
            elif completed:
                status = "partial"
            else:
                status = "missed"
            days.append(
                {
                    "date": cursor.isoformat(),
                    "completed": completed,
                    "total": total,
                    "missing": max(total - completed, 0),
                    "status": status,
                }
            )
            cursor += timedelta(days=1)
        return {"year": year, "month": month, "days": days}

    def _next_position(self, db: sqlite3.Connection, domain: str, cadence: str) -> int:
        row = db.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 AS next FROM tasks WHERE domain = ? AND cadence = ?",
            (domain, cadence),
        ).fetchone()
        return int(row["next"])

    @staticmethod
    def _validate_task_payload(payload: dict, *, partial: bool = False) -> dict:
        result: dict = {}
        if not partial or "title" in payload:
            title = payload.get("title")
            if not isinstance(title, str) or not title.strip():
                raise ValueError("Title is required")
            title = title.strip()
            if len(title) > 200:
                raise ValueError("Title is too long")
            result["title"] = title
        if not partial or "details" in payload:
            details = payload.get("details", "")
            if not isinstance(details, str) or len(details) > 4000:
                raise ValueError("Details must be at most 4000 characters")
            result["details"] = details.strip()
        if not partial or "domain" in payload:
            domain = payload.get("domain")
            if domain not in DOMAINS:
                raise ValueError("Invalid domain")
            result["domain"] = domain
        if not partial or "cadence" in payload:
            cadence = payload.get("cadence")
            if cadence not in CADENCES:
                raise ValueError("Invalid cadence")
            result["cadence"] = cadence
        if not partial or "due_date" in payload:
            result["due_date"] = normalize_optional_day(payload.get("due_date"), field="due_date")
        if "position" in payload:
            try:
                result["position"] = max(0, int(payload["position"]))
            except (TypeError, ValueError) as exc:
                raise ValueError("Position must be a number") from exc
        return result

    @staticmethod
    def _validate_group_items(payload: object, cadence: str) -> list[dict]:
        if not isinstance(payload, list):
            raise ValueError("Group items must be a list")
        if not payload or len(payload) > 100:
            raise ValueError("A group needs between 1 and 100 sequence items")
        result = []
        seen_ids: set[int] = set()
        action_count = 0
        for index, raw in enumerate(payload):
            if not isinstance(raw, dict):
                raise ValueError("Each group item must be an object")
            item_type = raw.get("item_type", "task")
            if item_type not in {"task", "rest"}:
                raise ValueError("Group item type must be task or rest")
            if cadence == "long_term" and item_type == "rest":
                raise ValueError("Long Term groups cannot contain rest steps")
            title = raw.get("title", "Rest day" if item_type == "rest" else "")
            if not isinstance(title, str) or not title.strip():
                raise ValueError("Every task item needs a title")
            title = title.strip()
            if len(title) > 200:
                raise ValueError("Group item title is too long")
            details = raw.get("details", "")
            if not isinstance(details, str) or len(details) > 4000:
                raise ValueError("Group item details must be at most 4000 characters")
            item_id = raw.get("id")
            if item_id not in (None, ""):
                try:
                    item_id = int(item_id)
                except (TypeError, ValueError) as exc:
                    raise ValueError("Invalid group item id") from exc
                if item_id <= 0 or item_id in seen_ids:
                    raise ValueError("Invalid or duplicate group item id")
                seen_ids.add(item_id)
            else:
                item_id = None
            if item_type == "task":
                action_count += 1
            result.append(
                {
                    "id": item_id,
                    "title": title,
                    "details": details.strip(),
                    "item_type": item_type,
                    "position": index,
                }
            )
        if action_count == 0:
            raise ValueError("A group needs at least one task item")
        return result

    def _insert_group(
        self,
        db: sqlite3.Connection,
        task_id: int,
        cadence: str,
        active_from: str,
        items: list[dict],
    ) -> None:
        timestamp = iso_now()
        mode = "daily_rotation" if cadence == "daily" else "long_term_focus"
        db.execute(
            """
            INSERT INTO task_groups(task_id, mode, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (task_id, mode, timestamp, timestamp),
        )
        for item in items:
            db.execute(
                """
                INSERT INTO group_items
                    (group_id, title, details, item_type, position, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    item["title"],
                    item["details"],
                    item["item_type"],
                    item["position"],
                    timestamp,
                    timestamp,
                ),
            )
        if cadence == "daily":
            self._ensure_rotation_assignment(db, task_id, active_from)

    def _update_group_items(
        self,
        db: sqlite3.Connection,
        task_id: int,
        cadence: str,
        items: list[dict],
    ) -> None:
        existing_rows = db.execute(
            "SELECT * FROM group_items WHERE group_id = ? AND archived_at IS NULL",
            (task_id,),
        ).fetchall()
        existing = {row["id"]: row for row in existing_rows}
        supplied_ids = {item["id"] for item in items if item["id"] is not None}
        if not supplied_ids.issubset(existing):
            raise ValueError("A group item does not belong to this task")
        timestamp = iso_now()
        for item in items:
            if item["id"] is None:
                cursor = db.execute(
                    """
                    INSERT INTO group_items
                        (group_id, title, details, item_type, position, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task_id,
                        item["title"],
                        item["details"],
                        item["item_type"],
                        item["position"],
                        timestamp,
                        timestamp,
                    ),
                )
                item["id"] = cursor.lastrowid
                supplied_ids.add(item["id"])
                continue
            if existing[item["id"]]["item_type"] != item["item_type"]:
                raise ValueError("An existing item cannot change between task and rest")
            db.execute(
                """
                UPDATE group_items
                SET title = ?, details = ?, position = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    item["title"],
                    item["details"],
                    item["position"],
                    timestamp,
                    item["id"],
                ),
            )
        removed_ids = set(existing) - supplied_ids
        if removed_ids:
            placeholders = ",".join("?" for _ in removed_ids)
            db.execute(
                f"""
                UPDATE group_items SET archived_at = ?, updated_at = ?
                WHERE group_id = ? AND id IN ({placeholders})
                """,
                (timestamp, timestamp, task_id, *sorted(removed_ids)),
            )
            db.execute(
                f"""
                UPDATE task_groups SET focused_item_id = NULL, updated_at = ?
                WHERE task_id = ? AND focused_item_id IN ({placeholders})
                """,
                (timestamp, task_id, *sorted(removed_ids)),
            )

        if cadence == "daily":
            for _ in range(100):
                latest = db.execute(
                    """
                    SELECT a.*, i.archived_at AS item_archived_at
                    FROM rotation_assignments a
                    JOIN group_items i ON i.id = a.item_id
                    WHERE a.group_id = ? AND a.resolved_on IS NULL
                    ORDER BY a.starts_on DESC, a.id DESC LIMIT 1
                    """,
                    (task_id,),
                ).fetchone()
                if not latest or not latest["item_archived_at"]:
                    break
                replacement = self._next_rotation_item(db, task_id, latest["item_id"])
                replacement_day = max(
                    date.fromisoformat(latest["starts_on"]), today_cn()
                ).isoformat()
                db.execute(
                    """
                    UPDATE rotation_assignments
                    SET resolved_on = ?, resolution = 'skipped'
                    WHERE id = ?
                    """,
                    (today_cn().isoformat(), latest["id"]),
                )
                db.execute(
                    """
                    INSERT INTO rotation_assignments(group_id, item_id, starts_on, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (task_id, replacement["id"], replacement_day, timestamp),
                )
            self._sync_daily_groups(db, today_cn())

    def create_task(self, payload: dict) -> dict:
        values = self._validate_task_payload(payload)
        task_type = payload.get("task_type", "standalone")
        if task_type not in {"standalone", "group"}:
            raise ValueError("task_type must be standalone or group")
        group_items = (
            self._validate_group_items(payload.get("children"), values["cadence"])
            if task_type == "group"
            else None
        )
        timestamp = iso_now()
        active_from = normalize_optional_day(payload.get("active_from"), field="active_from") or today_cn().isoformat()
        with self._write_lock, closing(self.connect()) as db:
            position = self._next_position(db, values["domain"], values["cadence"])
            cursor = db.execute(
                """
                INSERT INTO tasks
                    (title, details, domain, cadence, position, due_date, active_from, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    values["title"],
                    values["details"],
                    values["domain"],
                    values["cadence"],
                    position,
                    values["due_date"],
                    active_from,
                    timestamp,
                    timestamp,
                ),
            )
            task_id = cursor.lastrowid
            if group_items is not None:
                self._insert_group(
                    db, task_id, values["cadence"], active_from, group_items
                )
            db.commit()
            row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        result = self._task_to_dict(row)
        result["task_type"] = task_type
        return result

    def update_task(self, task_id: int, payload: dict) -> dict:
        values = self._validate_task_payload(payload, partial=True)
        if not values and "task_type" not in payload and "children" not in payload:
            raise ValueError("No editable fields supplied")
        with self._write_lock, closing(self.connect()) as db:
            existing = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not existing:
                raise KeyError("Task not found")
            group = db.execute(
                "SELECT * FROM task_groups WHERE task_id = ?", (task_id,)
            ).fetchone()
            requested_type = payload.get(
                "task_type", "group" if group else "standalone"
            )
            if requested_type not in {"standalone", "group"}:
                raise ValueError("task_type must be standalone or group")
            if group and requested_type == "standalone":
                raise ValueError("A group cannot be converted back to a standalone task")
            cadence = values.get("cadence", existing["cadence"])
            if group and cadence != existing["cadence"]:
                raise ValueError("A group rhythm cannot be changed after creation")
            group_items = None
            if requested_type == "group":
                if "children" not in payload:
                    if not group:
                        raise ValueError("Children are required when converting to a group")
                else:
                    group_items = self._validate_group_items(payload["children"], cadence)
            if values:
                values["updated_at"] = iso_now()
                assignments = ", ".join(f"{field} = ?" for field in values)
                db.execute(
                    f"UPDATE tasks SET {assignments} WHERE id = ?",
                    (*values.values(), task_id),
                )
            if requested_type == "group" and not group:
                self._insert_group(
                    db,
                    task_id,
                    cadence,
                    existing["active_from"],
                    group_items or [],
                )
                group = True
            elif group and group_items is not None:
                self._update_group_items(db, task_id, cadence, group_items)
            db.commit()
            row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        result = self._task_to_dict(row, bool(row["completed_at"]))
        result["task_type"] = "group" if group else "standalone"
        return result

    def complete_task(self, task_id: int, day: date | None = None) -> None:
        selected_day = day or today_cn()
        timestamp = iso_now()
        with self._write_lock, closing(self.connect()) as db:
            task = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not task or task["archived_at"]:
                raise KeyError("Task not found")
            group = db.execute(
                "SELECT 1 FROM task_groups WHERE task_id = ?", (task_id,)
            ).fetchone()
            if group:
                raise ValueError("Complete the active child inside this group")
            if task["cadence"] == "daily":
                db.execute(
                    "INSERT OR REPLACE INTO daily_checkins(task_id, check_date, completed_at) VALUES (?, ?, ?)",
                    (task_id, selected_day.isoformat(), timestamp),
                )
            else:
                db.execute(
                    "UPDATE tasks SET completed_at = ?, archived_at = ?, updated_at = ? WHERE id = ?",
                    (timestamp, timestamp, timestamp, task_id),
                )
            db.commit()

    def complete_group_item(
        self, task_id: int, item_id: int, day: date | None = None
    ) -> None:
        selected_day = day or today_cn()
        if selected_day > today_cn():
            raise ValueError("A future task cannot be completed")
        timestamp = iso_now()
        with self._write_lock, closing(self.connect()) as db:
            task = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            group = db.execute(
                "SELECT * FROM task_groups WHERE task_id = ?", (task_id,)
            ).fetchone()
            item = db.execute(
                """
                SELECT * FROM group_items
                WHERE id = ? AND group_id = ? AND archived_at IS NULL
                """,
                (item_id, task_id),
            ).fetchone()
            if not task or not group or not item or task["archived_at"]:
                raise KeyError("Group item not found")
            if item["item_type"] != "task":
                raise ValueError("Rest steps complete automatically")
            if group["mode"] == "daily_rotation":
                self._sync_daily_groups(db, min(selected_day, today_cn()))
                assignment = self._assignment_for_day(db, task_id, selected_day)
                if (
                    not assignment
                    or assignment["item_id"] != item_id
                    or assignment["item_type"] != "task"
                    or assignment["resolved_on"]
                ):
                    raise ValueError("Only the current rotation item can be completed")
                if selected_day < date.fromisoformat(assignment["starts_on"]):
                    raise ValueError("This rotation item has not started")
                db.execute(
                    """
                    INSERT OR REPLACE INTO group_item_checkins(item_id, check_date, completed_at)
                    VALUES (?, ?, ?)
                    """,
                    (item_id, selected_day.isoformat(), timestamp),
                )
                db.execute(
                    """
                    INSERT OR REPLACE INTO daily_checkins(task_id, check_date, completed_at)
                    VALUES (?, ?, ?)
                    """,
                    (task_id, selected_day.isoformat(), timestamp),
                )
                db.execute(
                    """
                    UPDATE rotation_assignments
                    SET resolved_on = ?, resolution = 'completed'
                    WHERE id = ?
                    """,
                    (selected_day.isoformat(), assignment["id"]),
                )
                next_item = self._next_rotation_item(db, task_id, item_id)
                db.execute(
                    """
                    INSERT INTO rotation_assignments(group_id, item_id, starts_on, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        task_id,
                        next_item["id"],
                        (selected_day + timedelta(days=1)).isoformat(),
                        timestamp,
                    ),
                )
                self._sync_daily_groups(db, today_cn())
            else:
                if item["completed_at"]:
                    return
                db.execute(
                    "UPDATE group_items SET completed_at = ?, updated_at = ? WHERE id = ?",
                    (timestamp, timestamp, item_id),
                )
                db.execute(
                    """
                    UPDATE task_groups
                    SET focused_item_id = CASE WHEN focused_item_id = ? THEN NULL ELSE focused_item_id END,
                        updated_at = ?
                    WHERE task_id = ?
                    """,
                    (item_id, timestamp, task_id),
                )
                remaining = db.execute(
                    """
                    SELECT COUNT(*) AS count FROM group_items
                    WHERE group_id = ? AND item_type = 'task'
                      AND archived_at IS NULL AND completed_at IS NULL
                    """,
                    (task_id,),
                ).fetchone()["count"]
                if remaining == 0:
                    db.execute(
                        """
                        UPDATE tasks
                        SET completed_at = ?, archived_at = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (timestamp, timestamp, timestamp, task_id),
                    )
            db.commit()

    def _undo_daily_group(
        self, db: sqlite3.Connection, task_id: int, selected_day: date
    ) -> None:
        day_s = selected_day.isoformat()
        later = db.execute(
            """
            SELECT 1 FROM daily_checkins
            WHERE task_id = ? AND check_date > ? LIMIT 1
            """,
            (task_id, day_s),
        ).fetchone()
        if later:
            raise ValueError("Undo newer rotation days before changing this day")
        item_checkin = db.execute(
            """
            SELECT c.item_id FROM group_item_checkins c
            JOIN group_items i ON i.id = c.item_id
            WHERE i.group_id = ? AND c.check_date = ?
            ORDER BY c.completed_at DESC LIMIT 1
            """,
            (task_id, day_s),
        ).fetchone()
        if not item_checkin:
            raise ValueError("Automatic rest days cannot be undone")
        assignment = db.execute(
            """
            SELECT * FROM rotation_assignments
            WHERE group_id = ? AND item_id = ?
              AND resolved_on = ? AND resolution = 'completed'
            ORDER BY id DESC LIMIT 1
            """,
            (task_id, item_checkin["item_id"], day_s),
        ).fetchone()
        if not assignment:
            raise ValueError("Rotation completion record was not found")
        db.execute(
            "DELETE FROM rotation_assignments WHERE group_id = ? AND id > ?",
            (task_id, assignment["id"]),
        )
        db.execute(
            """
            UPDATE rotation_assignments
            SET resolved_on = NULL, resolution = NULL WHERE id = ?
            """,
            (assignment["id"],),
        )
        db.execute(
            "DELETE FROM group_item_checkins WHERE item_id = ? AND check_date = ?",
            (item_checkin["item_id"], day_s),
        )
        db.execute(
            "DELETE FROM daily_checkins WHERE task_id = ? AND check_date = ?",
            (task_id, day_s),
        )

    def undo_group_item(
        self, task_id: int, item_id: int, day: date | None = None
    ) -> None:
        selected_day = day or today_cn()
        with self._write_lock, closing(self.connect()) as db:
            group = db.execute(
                "SELECT * FROM task_groups WHERE task_id = ?", (task_id,)
            ).fetchone()
            item = db.execute(
                "SELECT * FROM group_items WHERE id = ? AND group_id = ?",
                (item_id, task_id),
            ).fetchone()
            if not group or not item:
                raise KeyError("Group item not found")
            if group["mode"] == "daily_rotation":
                self._undo_daily_group(db, task_id, selected_day)
            else:
                timestamp = iso_now()
                db.execute(
                    "UPDATE group_items SET completed_at = NULL, updated_at = ? WHERE id = ?",
                    (timestamp, item_id),
                )
                db.execute(
                    """
                    UPDATE tasks SET completed_at = NULL, archived_at = NULL, updated_at = ?
                    WHERE id = ?
                    """,
                    (timestamp, task_id),
                )
            db.commit()

    def set_group_focus(self, task_id: int, item_id: int | None) -> None:
        with self._write_lock, closing(self.connect()) as db:
            group = db.execute(
                "SELECT * FROM task_groups WHERE task_id = ?", (task_id,)
            ).fetchone()
            if not group or group["mode"] != "long_term_focus":
                raise KeyError("Long Term group not found")
            if item_id is not None:
                item = db.execute(
                    """
                    SELECT 1 FROM group_items
                    WHERE id = ? AND group_id = ? AND item_type = 'task'
                      AND archived_at IS NULL AND completed_at IS NULL
                    """,
                    (item_id, task_id),
                ).fetchone()
                if not item:
                    raise ValueError("Focus must be an unfinished child task")
            db.execute(
                "UPDATE task_groups SET focused_item_id = ?, updated_at = ? WHERE task_id = ?",
                (item_id, iso_now(), task_id),
            )
            db.commit()

    def undo_task(self, task_id: int, day: date | None = None) -> None:
        selected_day = day or today_cn()
        with self._write_lock, closing(self.connect()) as db:
            task = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not task:
                raise KeyError("Task not found")
            group = db.execute(
                "SELECT * FROM task_groups WHERE task_id = ?", (task_id,)
            ).fetchone()
            if group:
                if group["mode"] != "daily_rotation":
                    raise ValueError("Undo a specific child inside this group")
                self._undo_daily_group(db, task_id, selected_day)
                db.commit()
                return
            if task["cadence"] == "daily":
                db.execute(
                    "DELETE FROM daily_checkins WHERE task_id = ? AND check_date = ?",
                    (task_id, selected_day.isoformat()),
                )
            else:
                db.execute(
                    "UPDATE tasks SET completed_at = NULL, archived_at = NULL, updated_at = ? WHERE id = ?",
                    (iso_now(), task_id),
                )
            db.commit()

    def archive_task(self, task_id: int) -> None:
        with self._write_lock, closing(self.connect()) as db:
            cursor = db.execute(
                "UPDATE tasks SET archived_at = ?, updated_at = ? WHERE id = ? AND archived_at IS NULL",
                (iso_now(), iso_now(), task_id),
            )
            if cursor.rowcount == 0:
                raise KeyError("Task not found")
            db.commit()

    def move_task(self, task_id: int, direction: str) -> None:
        if direction not in {"up", "down"}:
            raise ValueError("direction must be up or down")
        with self._write_lock, closing(self.connect()) as db:
            task = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not task or task["archived_at"]:
                raise KeyError("Task not found")
            rows = db.execute(
                """
                SELECT id FROM tasks
                WHERE domain = ? AND cadence = ? AND archived_at IS NULL
                ORDER BY position, id
                """,
                (task["domain"], task["cadence"]),
            ).fetchall()
            ordered_ids = [row["id"] for row in rows]
            current = ordered_ids.index(task_id)
            target = current - 1 if direction == "up" else current + 1
            if target < 0 or target >= len(ordered_ids):
                return
            ordered_ids[current], ordered_ids[target] = ordered_ids[target], ordered_ids[current]
            db.executemany(
                "UPDATE tasks SET position = ?, updated_at = ? WHERE id = ?",
                [(index, iso_now(), item_id) for index, item_id in enumerate(ordered_ids)],
            )
            db.commit()

    def set_paused(self, task_id: int, paused: bool) -> None:
        timestamp = iso_now()
        day_s = today_cn().isoformat()
        with self._write_lock, closing(self.connect()) as db:
            task = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not task or task["cadence"] != "daily" or task["archived_at"]:
                raise KeyError("Daily task not found")
            if paused and not task["paused_at"]:
                db.execute(
                    "INSERT INTO task_pauses(task_id, started_on) VALUES (?, ?)",
                    (task_id, day_s),
                )
                db.execute(
                    "UPDATE tasks SET paused_at = ?, updated_at = ? WHERE id = ?",
                    (timestamp, timestamp, task_id),
                )
            elif not paused and task["paused_at"]:
                db.execute(
                    "UPDATE task_pauses SET ended_on = ? WHERE task_id = ? AND ended_on IS NULL",
                    (day_s, task_id),
                )
                db.execute(
                    "UPDATE tasks SET paused_at = NULL, updated_at = ? WHERE id = ?",
                    (timestamp, task_id),
                )
                assignment = self._assignment_for_day(db, task_id, today_cn())
                if assignment and assignment["item_type"] == "rest" and not assignment["resolved_on"]:
                    db.execute(
                        "UPDATE rotation_assignments SET starts_on = ? WHERE id = ?",
                        (day_s, assignment["id"]),
                    )
                self._sync_daily_groups(db, today_cn())
            db.commit()

    def archive(self) -> list[dict]:
        with closing(self.connect()) as db:
            rows = db.execute(
                """
                SELECT t.*, CASE WHEN g.task_id IS NULL THEN 'standalone' ELSE 'group' END AS task_type
                FROM tasks t LEFT JOIN task_groups g ON g.task_id = t.id
                WHERE t.archived_at IS NOT NULL ORDER BY t.archived_at DESC
                """
            ).fetchall()
        return [self._task_to_dict(row, bool(row["completed_at"])) for row in rows]

    def restore_task(self, task_id: int) -> None:
        with self._write_lock, closing(self.connect()) as db:
            task = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not task:
                raise KeyError("Task not found")
            group = db.execute(
                "SELECT * FROM task_groups WHERE task_id = ?", (task_id,)
            ).fetchone()
            focus_item_id = None
            if group and group["mode"] == "long_term_focus" and task["completed_at"]:
                latest = db.execute(
                    """
                    SELECT id FROM group_items
                    WHERE group_id = ? AND archived_at IS NULL AND completed_at IS NOT NULL
                    ORDER BY completed_at DESC, id DESC LIMIT 1
                    """,
                    (task_id,),
                ).fetchone()
                if latest:
                    focus_item_id = latest["id"]
                    db.execute(
                        "UPDATE group_items SET completed_at = NULL, updated_at = ? WHERE id = ?",
                        (iso_now(), focus_item_id),
                    )
            cursor = db.execute(
                "UPDATE tasks SET archived_at = NULL, completed_at = NULL, updated_at = ? WHERE id = ?",
                (iso_now(), task_id),
            )
            if cursor.rowcount == 0:
                raise KeyError("Task not found")
            if focus_item_id is not None:
                db.execute(
                    "UPDATE task_groups SET focused_item_id = ?, updated_at = ? WHERE task_id = ?",
                    (focus_item_id, iso_now(), task_id),
                )
            db.commit()


class TodoHandler(BaseHTTPRequestHandler):
    server_version = "LocalTodo/1.1"

    @property
    def app(self) -> "TodoServer":
        return self.server  # type: ignore[return-value]

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stdout.write(f"[{iso_now()}] {self.address_string()} {fmt % args}\n")

    def _valid_request_host(self) -> bool:
        host = self.headers.get("Host", "")
        allowed = {
            f"127.0.0.1:{self.app.server_port}",
            f"localhost:{self.app.server_port}",
        }
        return host in allowed

    def _valid_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        return origin in {
            f"http://127.0.0.1:{self.app.server_port}",
            f"http://localhost:{self.app.server_port}",
        }

    def _send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(encoded)

    def _send_error_json(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"error": message}, status)

    def _send_static(self, filename: str, content_type: str) -> None:
        path = STATIC_DIR / filename
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        payload = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(payload)

    def _read_json(self) -> dict:
        content_type = self.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            raise ValueError("Expected application/json")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Invalid content length") from exc
        if length <= 0 or length > MAX_BODY_BYTES:
            raise ValueError("Invalid request size")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def _require_write_access(self) -> bool:
        if not self._valid_request_host() or not self._valid_origin():
            self._send_error_json(HTTPStatus.FORBIDDEN, "Request origin is not allowed")
            return False
        if not secrets.compare_digest(
            self.headers.get("X-CSRF-Token", ""), self.app.csrf_token
        ):
            self._send_error_json(HTTPStatus.FORBIDDEN, "Invalid session token")
            return False
        return True

    def do_GET(self) -> None:  # noqa: N802
        if not self._valid_request_host():
            self._send_error_json(HTTPStatus.FORBIDDEN, "Invalid host")
            return
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                self._send_static("index.html", "text/html; charset=utf-8")
            elif parsed.path == "/app.css":
                self._send_static("app.css", "text/css; charset=utf-8")
            elif parsed.path == "/app.js":
                self._send_static("app.js", "text/javascript; charset=utf-8")
            elif parsed.path == "/api/session":
                self._send_json({"csrf_token": self.app.csrf_token})
            elif parsed.path == "/api/state":
                params = parse_qs(parsed.query)
                day = parse_day(params.get("date", [None])[0])
                self._send_json(self.app.store.state(day))
            elif parsed.path == "/api/calendar":
                params = parse_qs(parsed.query)
                month_value = params.get("month", [today_cn().strftime("%Y-%m")])[0]
                try:
                    year, month = (int(part) for part in month_value.split("-", 1))
                except (ValueError, AttributeError) as exc:
                    raise ValueError("Invalid month; expected YYYY-MM") from exc
                self._send_json(self.app.store.calendar_month(year, month))
            elif parsed.path == "/api/archive":
                self._send_json({"tasks": self.app.store.archive()})
            else:
                self._send_error_json(HTTPStatus.NOT_FOUND, "Not found")
        except ValueError as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:  # pragma: no cover - final safety net
            self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def _task_route(self, path: str) -> tuple[int, str] | None:
        parts = [part for part in path.split("/") if part]
        if len(parts) < 3 or parts[0:2] != ["api", "tasks"]:
            return None
        try:
            task_id = int(parts[2])
        except ValueError:
            return None
        action = parts[3] if len(parts) == 4 else ""
        if len(parts) > 4:
            return None
        return task_id, action

    def _group_route(self, path: str) -> tuple[int, int | None, str] | None:
        parts = [part for part in path.split("/") if part]
        if len(parts) == 4 and parts[0:2] == ["api", "groups"] and parts[3] == "focus":
            try:
                return int(parts[2]), None, "focus"
            except ValueError:
                return None
        if (
            len(parts) == 6
            and parts[0:2] == ["api", "groups"]
            and parts[3] == "children"
            and parts[5] in {"complete", "undo"}
        ):
            try:
                return int(parts[2]), int(parts[4]), parts[5]
            except ValueError:
                return None
        return None

    def do_POST(self) -> None:  # noqa: N802
        if not self._require_write_access():
            return
        parsed = urlparse(self.path)
        try:
            payload = self._read_json()
            if parsed.path == "/api/tasks":
                task = self.app.store.create_task(payload)
                self._send_json({"task": task}, HTTPStatus.CREATED)
                return
            group_route = self._group_route(parsed.path)
            if group_route:
                task_id, item_id, action = group_route
                if action == "focus":
                    raw_item_id = payload.get("item_id")
                    if raw_item_id is None:
                        focus_item_id = None
                    else:
                        try:
                            focus_item_id = int(raw_item_id)
                        except (TypeError, ValueError) as exc:
                            raise ValueError("item_id must be a number or null") from exc
                    self.app.store.set_group_focus(task_id, focus_item_id)
                else:
                    day = parse_day(payload.get("date")) if payload.get("date") else None
                    if action == "complete":
                        self.app.store.complete_group_item(task_id, item_id, day)
                    else:
                        self.app.store.undo_group_item(task_id, item_id, day)
                self._send_json({"ok": True})
                return
            route = self._task_route(parsed.path)
            if not route:
                self._send_error_json(HTTPStatus.NOT_FOUND, "Not found")
                return
            task_id, action = route
            day = parse_day(payload.get("date")) if payload.get("date") else None
            if action == "complete":
                self.app.store.complete_task(task_id, day)
            elif action == "undo":
                self.app.store.undo_task(task_id, day)
            elif action == "archive":
                self.app.store.archive_task(task_id)
            elif action == "move":
                self.app.store.move_task(task_id, payload.get("direction", ""))
            elif action == "restore":
                self.app.store.restore_task(task_id)
            elif action == "pause":
                if not isinstance(payload.get("paused"), bool):
                    raise ValueError("paused must be true or false")
                self.app.store.set_paused(task_id, payload["paused"])
            else:
                self._send_error_json(HTTPStatus.NOT_FOUND, "Not found")
                return
            self._send_json({"ok": True})
        except KeyError as exc:
            self._send_error_json(HTTPStatus.NOT_FOUND, str(exc))
        except ValueError as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:  # pragma: no cover
            self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_PATCH(self) -> None:  # noqa: N802
        if not self._require_write_access():
            return
        parsed = urlparse(self.path)
        route = self._task_route(parsed.path)
        if not route or route[1]:
            self._send_error_json(HTTPStatus.NOT_FOUND, "Not found")
            return
        try:
            task = self.app.store.update_task(route[0], self._read_json())
            self._send_json({"task": task})
        except KeyError as exc:
            self._send_error_json(HTTPStatus.NOT_FOUND, str(exc))
        except ValueError as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:  # pragma: no cover
            self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))


class TodoServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], store: TodoStore):
        self.store = store
        self.csrf_token = secrets.token_urlsafe(32)
        super().__init__(address, TodoHandler)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the private local TODO app")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.environ.get("TODO_DATA_DIR", DEFAULT_DATA_DIR)),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data_dir = args.data_dir.resolve()
    store = TodoStore(data_dir / "todo.sqlite3")
    store.backup_once_per_day(data_dir / "backups")
    try:
        server = TodoServer(("127.0.0.1", args.port), store)
    except OSError as exc:
        print(f"Unable to start on port {args.port}: {exc}", file=sys.stderr)
        return 1

    url = f"http://127.0.0.1:{args.port}/"
    print(f"Private TODO is running at {url}")
    print(f"Data: {store.db_path}")
    print("Press Ctrl+C to stop.")
    if not args.no_browser:
        threading.Timer(0.45, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=0.4)
    except KeyboardInterrupt:
        print("\nStopping Private TODO...")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
