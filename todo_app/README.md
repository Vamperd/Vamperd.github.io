# Private TODO

A zero-dependency, localhost-only task app. Task data is stored in
`local/todo/todo.sqlite3`, which is excluded from Git by the repository's
existing `local/` ignore rule.

## Start

- Double-click `start_todo.bat`, or
- Run `python todo_app/server.py` from the repository root.

The browser opens at `http://127.0.0.1:8765/`. Close the terminal or press
Ctrl+C to stop the app.

## Task groups

- Choose **Task group** when adding a task to create one parent with child items.
- A **Daily** group advances only after the current child is completed. Add and
  reorder **Rest day** steps to build cycles such as chest, legs, shoulders and
  back, then rest. Missed training remains current; rest days complete the
  parent automatically.
- A **Long Term** group lets you mark one unfinished child as the current focus.
  The parent archives automatically when every child is complete.
- Existing standalone tasks can be converted to groups from the edit dialog.
  Group children can be reordered by dragging or with the arrow buttons.

## Data and backup

The SQLite database and daily startup backups stay under `local/todo/`.
To make a private manual backup, copy that directory while the app is stopped.

## Test

```powershell
python -m unittest discover -s todo_app/tests -v
```
