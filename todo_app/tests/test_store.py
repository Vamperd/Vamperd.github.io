import http.client
import json
import tempfile
import threading
import unittest
from datetime import timedelta
from pathlib import Path

from todo_app.server import TodoServer, TodoStore, today_cn


class TodoStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = TodoStore(Path(self.temp.name) / "todo.sqlite3")

    def tearDown(self):
        self.temp.cleanup()

    def create(self, **overrides):
        payload = {
            "title": "Read one paper",
            "details": "Write three useful notes",
            "domain": "phd_learning",
            "cadence": "daily",
        }
        payload.update(overrides)
        return self.store.create_task(payload)

    def create_group(self, *, cadence="daily", active_from=None, children=None):
        return self.store.create_task(
            {
                "title": "Fitness" if cadence == "daily" else "Thesis chapter",
                "details": "",
                "domain": "daily_life",
                "cadence": cadence,
                "task_type": "group",
                "active_from": active_from,
                "children": children
                or [
                    {"title": "Chest", "item_type": "task"},
                    {"title": "Legs", "item_type": "task"},
                    {"title": "Shoulders and back", "item_type": "task"},
                    {"title": "Rest day", "item_type": "rest"},
                ],
            }
        )

    def test_daily_completion_resets_on_the_next_day(self):
        day_one = today_cn()
        day_two = day_one + timedelta(days=1)
        task = self.create(active_from=day_one.isoformat())

        self.store.complete_task(task["id"], day_one)

        state_one = self.store.state(day_one)
        state_two = self.store.state(day_two)
        self.assertTrue(state_one["tasks"][0]["is_complete"])
        self.assertFalse(state_two["tasks"][0]["is_complete"])

    def test_long_term_completion_archives_and_can_be_undone(self):
        task = self.create(cadence="long_term", due_date=today_cn().isoformat())

        self.store.complete_task(task["id"])
        self.assertEqual(self.store.state()["tasks"], [])
        self.assertEqual(len(self.store.archive()), 1)

        self.store.undo_task(task["id"])
        restored = self.store.state()["tasks"][0]
        self.assertFalse(restored["is_complete"])

    def test_paused_daily_is_visible_but_not_counted(self):
        task = self.create()
        self.store.set_paused(task["id"], True)

        paused_state = self.store.state()
        self.assertTrue(paused_state["tasks"][0]["is_paused"])
        self.assertEqual(paused_state["daily_progress"]["total"], 0)

        self.store.set_paused(task["id"], False)
        active_state = self.store.state()
        self.assertFalse(active_state["tasks"][0]["is_paused"])
        self.assertEqual(active_state["daily_progress"]["total"], 1)

    def test_calendar_marks_complete_and_missed_days(self):
        today = today_cn()
        first_day = today - timedelta(days=2)
        missed_day = today - timedelta(days=1)
        if first_day.month != today.month:
            self.skipTest("Month boundary does not provide two prior days")
        task = self.create(active_from=first_day.isoformat())
        self.store.complete_task(task["id"], first_day)

        month = self.store.calendar_month(today.year, today.month)
        by_date = {item["date"]: item for item in month["days"]}
        self.assertEqual(by_date[first_day.isoformat()]["status"], "complete")
        self.assertEqual(by_date[missed_day.isoformat()]["status"], "missed")

    def test_tasks_can_be_reordered_within_their_group(self):
        first = self.create(title="First")
        second = self.create(title="Second")

        self.store.move_task(second["id"], "up")

        titles = [task["title"] for task in self.store.state()["tasks"]]
        self.assertEqual(titles, ["Second", "First"])

    def test_daily_group_rotates_by_completion_and_auto_completes_rest(self):
        start = today_cn() - timedelta(days=4)
        group = self.create_group(active_from=start.isoformat())

        state = self.store.state(start)
        chest, legs, shoulders, _rest = state["tasks"][0]["group"]["children"]
        self.assertTrue(chest["is_active"])
        self.store.complete_group_item(group["id"], chest["id"], start)
        self.assertTrue(
            next(
                item
                for item in self.store.state(start + timedelta(days=1))["tasks"][0]["group"]["children"]
                if item["id"] == legs["id"]
            )["is_active"]
        )

        self.store.complete_group_item(group["id"], legs["id"], start + timedelta(days=1))
        self.store.complete_group_item(group["id"], shoulders["id"], start + timedelta(days=2))

        rest_state = self.store.state(start + timedelta(days=3))["tasks"][0]
        self.assertTrue(rest_state["group"]["is_rest_day"])
        self.assertTrue(rest_state["is_complete"])
        today_state = self.store.state(today_cn())
        self.assertEqual(today_state["daily_progress"], {"completed": 0, "total": 1})
        self.assertEqual(today_state["tasks"][0]["group"]["active_item_id"], chest["id"])

    def test_missed_rotation_item_stays_active_until_completed(self):
        start = today_cn() - timedelta(days=2)
        group = self.create_group(active_from=start.isoformat())
        state = self.store.state(today_cn())
        active_id = state["tasks"][0]["group"]["active_item_id"]
        first_id = state["tasks"][0]["group"]["children"][0]["id"]
        self.assertEqual(active_id, first_id)

        self.store.complete_group_item(group["id"], first_id, today_cn())
        tomorrow = self.store.state(today_cn() + timedelta(days=1))["tasks"][0]
        self.assertNotEqual(tomorrow["group"]["active_item_id"], first_id)

    def test_daily_group_counts_only_the_parent(self):
        self.create_group()
        self.create(title="Drink water", domain="daily_life")
        state = self.store.state()
        self.assertEqual(state["daily_progress"]["total"], 2)
        month = self.store.calendar_month(today_cn().year, today_cn().month)
        today_entry = next(day for day in month["days"] if day["date"] == today_cn().isoformat())
        self.assertEqual(today_entry["total"], 2)

    def test_long_term_group_focus_and_parent_auto_archive(self):
        group = self.create_group(
            cadence="long_term",
            children=[
                {"title": "Outline", "item_type": "task"},
                {"title": "Draft", "item_type": "task"},
            ],
        )
        state = self.store.state()["tasks"][0]
        outline, draft = state["group"]["children"]
        self.store.set_group_focus(group["id"], outline["id"])
        focused = self.store.state()["tasks"][0]
        self.assertEqual(focused["group"]["focused_item_id"], outline["id"])

        self.store.complete_group_item(group["id"], outline["id"])
        after_outline = self.store.state()["tasks"][0]
        self.assertIsNone(after_outline["group"]["focused_item_id"])
        self.assertEqual(after_outline["group"]["progress"], {"completed": 1, "total": 2})

        self.store.complete_group_item(group["id"], draft["id"])
        self.assertEqual(self.store.state()["tasks"], [])
        self.assertEqual(self.store.archive()[0]["task_type"], "group")

        self.store.undo_group_item(group["id"], draft["id"])
        reopened = self.store.state()["tasks"][0]
        self.assertEqual(reopened["group"]["progress"], {"completed": 1, "total": 2})

    def test_group_edit_soft_archives_removed_child_and_replaces_active_item(self):
        group = self.create_group()
        original = self.store.state()["tasks"][0]
        children = original["group"]["children"]
        kept = children[1:]
        self.store.update_task(
            group["id"],
            {
                "task_type": "group",
                "children": [
                    {
                        "id": child["id"],
                        "title": child["title"],
                        "details": child["details"],
                        "item_type": child["item_type"],
                    }
                    for child in kept
                ],
            },
        )
        updated = self.store.state()["tasks"][0]
        self.assertNotEqual(updated["group"]["active_item_id"], children[0]["id"])
        db = self.store.connect()
        try:
            removed = db.execute(
                "SELECT archived_at FROM group_items WHERE id = ?", (children[0]["id"],)
            ).fetchone()
        finally:
            db.close()
        self.assertIsNotNone(removed["archived_at"])

    def test_standalone_task_can_be_converted_to_a_group(self):
        task = self.create(title="Training")
        self.store.update_task(
            task["id"],
            {
                "task_type": "group",
                "children": [
                    {"title": "Warm up", "item_type": "task"},
                    {"title": "Rest", "item_type": "rest"},
                ],
            },
        )

        converted = self.store.state()["tasks"][0]
        self.assertEqual(converted["task_type"], "group")
        self.assertEqual(converted["group"]["progress"]["total"], 1)
        self.assertEqual(converted["group"]["children"][0]["title"], "Warm up")


class TodoServerSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        store = TodoStore(Path(self.temp.name) / "todo.sqlite3")
        self.server = TodoServer(("127.0.0.1", 0), store)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=3
        )

    def tearDown(self):
        self.connection.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.temp.cleanup()

    def test_write_requires_csrf_token(self):
        body = json.dumps(
            {
                "title": "Test",
                "domain": "daily_life",
                "cadence": "daily",
                "details": "",
            }
        )
        self.connection.request(
            "POST",
            "/api/tasks",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        response.read()
        self.assertEqual(response.status, 403)

    def test_authenticated_local_write_succeeds(self):
        body = json.dumps(
            {
                "title": "Test",
                "domain": "daily_life",
                "cadence": "daily",
                "details": "",
            }
        )
        self.connection.request(
            "POST",
            "/api/tasks",
            body=body,
            headers={
                "Content-Type": "application/json",
                "X-CSRF-Token": self.server.csrf_token,
            },
        )
        response = self.connection.getresponse()
        payload = json.loads(response.read())
        self.assertEqual(response.status, 201)
        self.assertEqual(payload["task"]["title"], "Test")

    def test_group_child_completion_endpoint(self):
        group = self.server.store.create_task(
            {
                "title": "Fitness",
                "details": "",
                "domain": "daily_life",
                "cadence": "daily",
                "task_type": "group",
                "children": [
                    {"title": "Chest", "item_type": "task"},
                    {"title": "Rest day", "item_type": "rest"},
                ],
            }
        )
        child = self.server.store.state()["tasks"][0]["group"]["children"][0]
        self.connection.request(
            "POST",
            f"/api/groups/{group['id']}/children/{child['id']}/complete",
            body=json.dumps({"date": today_cn().isoformat()}),
            headers={
                "Content-Type": "application/json",
                "X-CSRF-Token": self.server.csrf_token,
            },
        )
        response = self.connection.getresponse()
        response.read()
        self.assertEqual(response.status, 200)
        self.assertEqual(self.server.store.state()["daily_progress"]["completed"], 1)


if __name__ == "__main__":
    unittest.main()
