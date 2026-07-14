"use strict";

const DOMAIN_DEFS = [
  { id: "daily_life", name: "Daily Life", note: "Body, home, and the texture of a day", mark: "DL" },
  { id: "robomaster_team", name: "RoboMaster Team", note: "Build, coordinate, and keep the team moving", mark: "RM" },
  { id: "phd_learning", name: "PhD Learning", note: "Read deeply, think clearly, write what remains", mark: "PL" },
];

const app = {
  csrf: "",
  state: null,
  tasks: [],
  taskMap: new Map(),
  calendar: null,
  calendarCursor: new Date(),
  selectedCalendarDate: null,
  openDomain: localStorage.getItem("todo.openDomain") || "daily_life",
  openGroups: new Set(JSON.parse(localStorage.getItem("todo.openGroups") || "[]")),
  editorItems: [],
  draggedEditorIndex: null,
  undo: null,
  undoTimer: null,
};

const els = {};

document.addEventListener("DOMContentLoaded", boot);

async function boot() {
  cacheElements();
  bindEvents();
  try {
    const session = await api("/api/session");
    app.csrf = session.csrf_token;
    await refreshAll();
    scheduleMidnightRefresh();
  } catch (error) {
    showFatal(error.message);
  }
}

function cacheElements() {
  [
    "today-label", "progress-count", "progress-fill", "progress-percent",
    "domain-stack", "calendar-heading", "calendar-grid", "calendar-detail",
    "prev-month", "next-month", "add-task-button", "archive-button",
    "task-dialog", "task-form", "task-id", "task-title", "task-details",
    "task-type", "task-domain", "task-cadence", "task-due-date", "due-field", "form-mode",
    "form-title", "form-error", "close-dialog", "cancel-task-button",
    "archive-task-button", "pause-task-button", "move-task-up", "move-task-down", "archive-dialog", "archive-list",
    "close-archive", "toast", "toast-message", "toast-undo", "empty-template",
    "group-editor", "group-editor-kicker", "group-editor-title", "group-editor-help",
    "group-item-editor-list", "add-child-button", "add-rest-button",
  ].forEach((id) => { els[id] = document.getElementById(id); });
}

function bindEvents() {
  els["add-task-button"].addEventListener("click", () => openTaskDialog());
  els["archive-button"].addEventListener("click", openArchive);
  els["close-dialog"].addEventListener("click", closeTaskDialog);
  els["cancel-task-button"].addEventListener("click", closeTaskDialog);
  els["close-archive"].addEventListener("click", () => els["archive-dialog"].close());
  els["task-form"].addEventListener("submit", saveTask);
  els["task-cadence"].addEventListener("change", updateDueField);
  els["task-type"].addEventListener("change", updateTaskShape);
  els["add-child-button"].addEventListener("click", () => addEditorItem("task"));
  els["add-rest-button"].addEventListener("click", () => addEditorItem("rest"));
  els["archive-task-button"].addEventListener("click", archiveCurrentTask);
  els["pause-task-button"].addEventListener("click", pauseCurrentTask);
  els["move-task-up"].addEventListener("click", () => moveCurrentTask("up"));
  els["move-task-down"].addEventListener("click", () => moveCurrentTask("down"));
  els["prev-month"].addEventListener("click", () => shiftMonth(-1));
  els["next-month"].addEventListener("click", () => shiftMonth(1));
  els["toast-undo"].addEventListener("click", performUndo);
  els["task-dialog"].addEventListener("click", closeDialogFromBackdrop);
  els["archive-dialog"].addEventListener("click", closeDialogFromBackdrop);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && app.state && localDay() !== app.state.today) refreshAll();
  });
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    headers["X-CSRF-Token"] = app.csrf;
    options.body = JSON.stringify(options.body);
  }
  const response = await fetch(path, { ...options, headers });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
  return payload;
}

async function refreshAll() {
  const [state] = await Promise.all([
    api("/api/state"),
    refreshCalendar(),
  ]);
  app.state = state;
  app.tasks = state.tasks;
  app.taskMap = new Map(app.tasks.map((task) => [Number(task.id), task]));
  renderHeader();
  renderDomains();
  renderCalendar();
}

function renderHeader() {
  const dateValue = new Date(`${app.state.today}T12:00:00`);
  els["today-label"].textContent = new Intl.DateTimeFormat("en", {
    weekday: "long", month: "long", day: "numeric", year: "numeric",
  }).format(dateValue).toUpperCase();
  const { completed, total } = app.state.daily_progress;
  const percent = total ? Math.round((completed / total) * 100) : 0;
  els["progress-count"].textContent = `${completed} of ${total}`;
  els["progress-percent"].textContent = `${percent}%`;
  els["progress-fill"].style.width = `${percent}%`;
}

function renderDomains() {
  els["domain-stack"].replaceChildren();
  DOMAIN_DEFS.forEach((domain) => {
    const tasks = app.tasks.filter((task) => task.domain === domain.id);
    const pending = tasks.filter((task) => !task.is_complete && !task.is_paused).length;
    const card = document.createElement("section");
    const isOpen = app.openDomain === domain.id;
    card.className = `domain-card${isOpen ? " is-open" : ""}`;
    card.dataset.domain = domain.id;
    card.innerHTML = `
      <button class="domain-toggle" type="button" aria-expanded="${isOpen}">
        <span class="domain-mark">${domain.mark}</span>
        <span class="domain-title"><strong>${domain.name}</strong><span>${domain.note}</span></span>
        <span class="domain-count">${pending} open</span>
        <span class="chevron" aria-hidden="true">⌄</span>
      </button>
      <div class="domain-content"><div class="domain-content-inner"><div class="task-columns"></div></div></div>`;
    card.querySelector(".domain-toggle").addEventListener("click", () => toggleDomain(domain.id));
    const columns = card.querySelector(".task-columns");
    columns.append(
      buildTaskGroup("Daily", tasks.filter((task) => task.cadence === "daily"), domain.id),
      buildTaskGroup("Long Term", tasks.filter((task) => task.cadence === "long_term"), domain.id),
    );
    els["domain-stack"].append(card);
  });
}

function toggleDomain(domainId) {
  app.openDomain = app.openDomain === domainId ? "" : domainId;
  localStorage.setItem("todo.openDomain", app.openDomain);
  renderDomains();
}

function buildTaskGroup(label, tasks, domainId) {
  const group = document.createElement("section");
  group.className = "task-group";
  const pending = tasks.filter((task) => !task.is_complete && !task.is_paused);
  const paused = tasks.filter((task) => task.is_paused);
  const completed = tasks.filter((task) => task.is_complete);
  group.innerHTML = `<div class="task-group-head"><h3>${label}</h3><span>${pending.length} remaining</span></div>`;
  const list = document.createElement("div");
  list.className = "task-list";
  if (!pending.length && !paused.length) {
    list.append(els["empty-template"].content.cloneNode(true));
  } else {
    [...pending, ...paused].forEach((task) => list.append(buildTaskEntry(task, domainId)));
  }
  group.append(list);
  if (completed.length) {
    const details = document.createElement("details");
    details.className = "completed-block";
    details.innerHTML = `<summary>${completed.length} completed today</summary>`;
    completed.forEach((task) => details.append(buildTaskEntry(task, domainId)));
    group.append(details);
  }
  return group;
}

function buildTaskEntry(task, domainId) {
  return task.task_type === "group" ? buildTaskCluster(task, domainId) : buildTaskRow(task, domainId);
}

function buildTaskCluster(task, domainId) {
  const cluster = document.createElement("article");
  cluster.className = "task-cluster";
  cluster.dataset.taskId = task.id;
  cluster.style.setProperty("--domain-id", domainId);

  const hasCurrent = Boolean(task.group.active_item_id || task.group.focused_item_id);
  const storedOpen = app.openGroups.has(Number(task.id));
  const isOpen = storedOpen || (hasCurrent && !localStorage.getItem("todo.openGroupsTouched"));
  cluster.classList.toggle("is-open", isOpen);

  const head = document.createElement("div");
  head.className = "cluster-head";

  const status = document.createElement("span");
  status.className = `cluster-status${task.is_complete ? " is-complete" : ""}`;
  status.setAttribute("aria-hidden", "true");
  status.textContent = task.is_complete ? "✓" : task.cadence === "daily" ? "↻" : "◇";

  const copy = document.createElement("button");
  copy.type = "button";
  copy.className = "cluster-copy";
  copy.setAttribute("aria-expanded", String(isOpen));
  const title = document.createElement("strong");
  title.textContent = task.title;
  const summary = document.createElement("span");
  summary.textContent = groupSummary(task);
  copy.append(title, summary);
  copy.addEventListener("click", () => toggleTaskCluster(task.id));

  const edit = document.createElement("button");
  edit.type = "button";
  edit.className = "edit-button";
  edit.setAttribute("aria-label", `Edit ${task.title}`);
  edit.textContent = "•••";
  edit.addEventListener("click", () => openTaskDialog(task));

  const chevron = document.createElement("button");
  chevron.type = "button";
  chevron.className = "cluster-chevron";
  chevron.setAttribute("aria-label", `${isOpen ? "Collapse" : "Expand"} ${task.title}`);
  chevron.textContent = "⌄";
  chevron.addEventListener("click", () => toggleTaskCluster(task.id));
  head.append(status, copy, edit, chevron);

  const body = document.createElement("div");
  body.className = "cluster-body";
  body.hidden = !isOpen;
  body.inert = !isOpen;
  body.setAttribute("aria-hidden", String(!isOpen));
  const inner = document.createElement("div");
  inner.className = "cluster-body-inner";
  if (task.details) {
    const details = document.createElement("p");
    details.className = "cluster-details";
    details.textContent = task.details;
    inner.append(details);
  }
  if (task.group.is_rest_day) {
    const rest = document.createElement("div");
    rest.className = "rest-day-banner";
    rest.innerHTML = `<span aria-hidden="true">☾</span><div><strong></strong><p>Recovery is part of the rotation. The next task begins tomorrow.</p></div>`;
    rest.querySelector("strong").textContent = task.group.rest_title || "Rest day";
    inner.append(rest);
  }

  const children = task.group.children.filter((child) => child.item_type === "task");
  const childGrid = document.createElement("div");
  childGrid.className = `cluster-children${hasCurrent && !task.group.is_rest_day ? " has-current" : " is-equal"}`;
  const currentChild = children.find((child) => child.is_active || child.is_focused);
  if (currentChild && !task.group.is_rest_day) {
    const others = children.filter((child) => child.id !== currentChild.id);
    childGrid.classList.toggle("is-solo", !others.length);
    childGrid.append(buildChildTask(task, currentChild, true));
    if (others.length) {
      const rail = document.createElement("div");
      rail.className = "child-rail";
      others.forEach((child) => rail.append(buildChildTask(task, child, true)));
      childGrid.append(rail);
    }
  } else {
    children.forEach((child) => childGrid.append(buildChildTask(task, child, false)));
  }
  inner.append(childGrid);
  body.append(inner);
  cluster.append(head, body);
  return cluster;
}

function groupSummary(task) {
  if (task.is_paused) return "Paused";
  if (task.group.is_rest_day) return task.is_complete ? "Rest day · complete" : "Rest day";
  if (task.cadence === "daily") {
    const active = task.group.children.find((child) => child.id === task.group.active_item_id);
    if (task.is_complete) {
      const completed = task.group.children.find((child) => child.id === task.group.completed_item_id);
      return completed ? `Completed · ${completed.title}` : "Completed today";
    }
    return active ? `Today · ${active.title}` : "Rotation ready";
  }
  const { completed, total } = task.group.progress;
  const focused = task.group.children.find((child) => child.id === task.group.focused_item_id);
  return focused ? `${completed}/${total} · Focus: ${focused.title}` : `${completed}/${total} complete`;
}

function buildChildTask(task, child, hasCurrent) {
  const row = document.createElement("div");
  const isCurrent = Boolean(child.is_active || child.is_focused);
  row.className = `child-task${isCurrent ? " is-current" : ""}${hasCurrent && !isCurrent ? " is-receded" : ""}${child.is_complete ? " is-complete" : ""}`;
  row.dataset.itemId = child.id;

  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.className = "task-check child-check";
  checkbox.checked = Boolean(child.is_complete);
  checkbox.disabled = Boolean(task.is_paused || (task.cadence === "daily" && (!child.is_active || task.group.is_rest_day)));
  checkbox.setAttribute("aria-label", `${child.is_complete ? "Undo" : "Complete"} ${task.title}: ${child.title}`);
  checkbox.addEventListener("change", () => toggleGroupItem(task, child, row, checkbox));

  const copy = document.createElement("div");
  copy.className = "child-copy";
  const title = document.createElement("strong");
  title.textContent = child.title;
  copy.append(title);
  if (child.details) {
    const details = document.createElement("p");
    details.textContent = child.details;
    copy.append(details);
  }

  row.append(checkbox, copy);
  if (task.cadence === "long_term" && !child.is_complete) {
    const focus = document.createElement("button");
    focus.type = "button";
    focus.className = `focus-button${child.is_focused ? " is-active" : ""}`;
    focus.textContent = child.is_focused ? "Focused" : "Focus";
    focus.setAttribute("aria-pressed", String(Boolean(child.is_focused)));
    focus.addEventListener("click", () => setGroupFocus(task.id, child.is_focused ? null : child.id));
    row.append(focus);
  }
  return row;
}

function toggleTaskCluster(taskId) {
  const id = Number(taskId);
  if (app.openGroups.has(id)) app.openGroups.delete(id);
  else app.openGroups.add(id);
  localStorage.setItem("todo.openGroups", JSON.stringify([...app.openGroups]));
  localStorage.setItem("todo.openGroupsTouched", "true");
  renderDomains();
}

function buildTaskRow(task, domainId) {
  const row = document.createElement("div");
  row.className = "task-row";
  row.dataset.taskId = task.id;
  row.style.setProperty("--domain-id", domainId);

  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.className = "task-check";
  checkbox.checked = Boolean(task.is_complete);
  checkbox.disabled = Boolean(task.is_paused);
  checkbox.setAttribute("aria-label", `${task.is_complete ? "Undo" : "Complete"} ${task.title}`);
  checkbox.addEventListener("change", () => toggleTask(task, row, checkbox));

  const main = document.createElement("div");
  main.className = "task-main";
  const title = document.createElement("span");
  title.className = "task-title";
  title.textContent = task.title;
  main.append(title);
  if (task.details) {
    const details = document.createElement("p");
    details.className = "task-details";
    details.textContent = task.details;
    main.append(details);
  }
  const meta = document.createElement("div");
  meta.className = "task-meta";
  if (task.is_paused) meta.append(metaLabel("Paused"));
  if (task.due_date) {
    const due = metaLabel(`Due ${formatShortDate(task.due_date)}`);
    if (!task.is_complete && task.due_date < app.state.today) due.classList.add("is-overdue");
    meta.append(due);
  }
  if (meta.childElementCount) main.append(meta);

  const edit = document.createElement("button");
  edit.type = "button";
  edit.className = "edit-button";
  edit.setAttribute("aria-label", `Edit ${task.title}`);
  edit.textContent = "•••";
  edit.addEventListener("click", () => openTaskDialog(task));
  row.append(checkbox, main, edit);
  return row;
}

function metaLabel(text) {
  const span = document.createElement("span");
  span.textContent = text;
  return span;
}

async function toggleTask(task, row, checkbox) {
  if (task.is_complete) {
    try {
      await api(`/api/tasks/${task.id}/undo`, { method: "POST", body: { date: app.state.today } });
      await refreshAll();
    } catch (error) {
      checkbox.checked = true;
      showToast(error.message);
    }
    return;
  }
  checkbox.disabled = true;
  try {
    await api(`/api/tasks/${task.id}/complete`, { method: "POST", body: { date: app.state.today } });
    createParticles(row);
    row.classList.add("is-completing");
    await wait(reducedMotion() ? 20 : 560);
    app.undo = { id: task.id, date: app.state.today };
    showToast(`Completed “${task.title}”`, true);
    await refreshAll();
  } catch (error) {
    checkbox.checked = false;
    checkbox.disabled = false;
    showToast(error.message);
  }
}

async function toggleGroupItem(task, child, row, checkbox) {
  const action = child.is_complete ? "undo" : "complete";
  checkbox.disabled = true;
  try {
    await api(`/api/groups/${task.id}/children/${child.id}/${action}`, {
      method: "POST",
      body: { date: app.state.today },
    });
    if (action === "complete") {
      createParticles(row);
      row.classList.add("is-completing");
      await wait(reducedMotion() ? 20 : 560);
      app.undo = { kind: "group_item", taskId: task.id, itemId: child.id, date: app.state.today };
      showToast(`Completed — ${task.title} · ${child.title}`, true);
    }
    await refreshAll();
  } catch (error) {
    checkbox.checked = Boolean(child.is_complete);
    checkbox.disabled = false;
    showToast(error.message);
  }
}

async function setGroupFocus(taskId, itemId) {
  try {
    await api(`/api/groups/${taskId}/focus`, {
      method: "POST",
      body: { item_id: itemId },
    });
    await refreshAll();
  } catch (error) {
    showToast(error.message);
  }
}

function createParticles(row) {
  if (reducedMotion()) return;
  const points = [[-18,-20],[4,-27],[21,-12],[24,11],[2,25],[-21,15]];
  points.forEach(([x, y]) => {
    const particle = document.createElement("span");
    particle.className = "particle";
    particle.style.setProperty("--x", `${x}px`);
    particle.style.setProperty("--y", `${y}px`);
    row.append(particle);
  });
}

function openTaskDialog(task = null) {
  els["task-form"].reset();
  els["form-error"].textContent = "";
  app.editorItems = task?.group?.children.map((child) => ({
    id: child.id,
    title: child.title,
    details: child.details || "",
    item_type: child.item_type,
  })) || [];
  els["task-id"].value = task ? task.id : "";
  els["form-mode"].textContent = task ? "EDIT TASK" : "NEW TASK";
  els["form-title"].textContent = task ? "Refine the task" : "Add a task";
  els["task-title"].value = task?.title || "";
  els["task-details"].value = task?.details || "";
  els["task-type"].value = task?.task_type || "standalone";
  els["task-domain"].value = task?.domain || app.openDomain || "daily_life";
  els["task-cadence"].value = task?.cadence || "daily";
  els["task-due-date"].value = task?.due_date || "";
  els["task-type"].disabled = Boolean(task?.task_type === "group");
  els["task-cadence"].disabled = Boolean(task?.task_type === "group");
  els["archive-task-button"].classList.toggle("is-hidden", !task);
  els["pause-task-button"].classList.toggle("is-hidden", !task || task.cadence !== "daily");
  els["move-task-up"].classList.toggle("is-hidden", !task);
  els["move-task-down"].classList.toggle("is-hidden", !task);
  els["pause-task-button"].textContent = task?.is_paused ? "Resume daily" : "Pause daily";
  updateTaskShape();
  els["task-dialog"].showModal();
  requestAnimationFrame(() => els["task-title"].focus());
}

function closeTaskDialog() {
  els["task-dialog"].close();
}

function updateDueField() {
  const isLongTerm = els["task-cadence"].value === "long_term";
  els["due-field"].classList.toggle("is-hidden", !isLongTerm);
  els["add-rest-button"].classList.toggle("is-hidden", isLongTerm);
  if (isLongTerm && els["task-type"].value === "group") {
    app.editorItems = app.editorItems.filter((item) => item.item_type !== "rest");
    if (!app.editorItems.length) app.editorItems.push(newEditorItem("task"));
    renderGroupEditor();
  }
  updateGroupEditorCopy();
}

function updateTaskShape() {
  const isGroup = els["task-type"].value === "group";
  els["group-editor"].classList.toggle("is-hidden", !isGroup);
  if (isGroup && !app.editorItems.length) app.editorItems.push(newEditorItem("task"));
  updateDueField();
  renderGroupEditor();
}

function updateGroupEditorCopy() {
  const isDaily = els["task-cadence"].value === "daily";
  els["group-editor-kicker"].textContent = isDaily ? "ROTATION" : "MILESTONES";
  els["group-editor-title"].textContent = isDaily ? "Daily sequence" : "Long Term children";
  els["group-editor-help"].textContent = isDaily
    ? "Drag to order. Completing the current item advances tomorrow."
    : "Drag to order. Choose the current focus from the task card.";
}

function newEditorItem(itemType) {
  return {
    id: null,
    title: itemType === "rest" ? "Rest day" : "",
    details: "",
    item_type: itemType,
  };
}

function addEditorItem(itemType) {
  app.editorItems.push(newEditorItem(itemType));
  renderGroupEditor();
  requestAnimationFrame(() => {
    const inputs = els["group-item-editor-list"].querySelectorAll(".group-item-title");
    inputs[inputs.length - 1]?.focus();
  });
}

function renderGroupEditor() {
  els["group-item-editor-list"].replaceChildren();
  if (els["task-type"].value !== "group") return;
  app.editorItems.forEach((item, index) => {
    const row = document.createElement("div");
    row.className = `group-item-editor${item.item_type === "rest" ? " is-rest" : ""}`;
    row.draggable = true;
    row.dataset.index = index;

    const handle = document.createElement("span");
    handle.className = "drag-handle";
    handle.textContent = "⠿";
    handle.setAttribute("aria-hidden", "true");

    const badge = document.createElement("span");
    badge.className = "item-type-badge";
    badge.textContent = item.item_type === "rest" ? "REST" : String(index + 1).padStart(2, "0");

    const fields = document.createElement("div");
    fields.className = "group-item-fields";
    const title = document.createElement("input");
    title.className = "group-item-title";
    title.maxLength = 200;
    title.required = true;
    title.autocomplete = "off";
    title.placeholder = item.item_type === "rest" ? "Rest day label" : "Child task";
    title.value = item.title;
    title.setAttribute("aria-label", `${item.item_type === "rest" ? "Rest step" : "Child task"} title`);
    title.addEventListener("input", () => { item.title = title.value; });
    fields.append(title);
    if (item.item_type === "task") {
      const details = document.createElement("input");
      details.className = "group-item-details";
      details.maxLength = 4000;
      details.placeholder = "Optional note";
      details.value = item.details;
      details.setAttribute("aria-label", `${item.title || "Child task"} note`);
      details.addEventListener("input", () => { item.details = details.value; });
      fields.append(details);
    }

    const controls = document.createElement("div");
    controls.className = "group-item-controls";
    controls.append(
      editorControl("↑", `Move ${item.title || "item"} up`, () => moveEditorItem(index, -1), index === 0),
      editorControl("↓", `Move ${item.title || "item"} down`, () => moveEditorItem(index, 1), index === app.editorItems.length - 1),
      editorControl("×", `Remove ${item.title || "item"}`, () => removeEditorItem(index)),
    );

    row.addEventListener("dragstart", (event) => {
      app.draggedEditorIndex = index;
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", String(index));
      row.classList.add("is-dragging");
    });
    row.addEventListener("dragend", () => {
      app.draggedEditorIndex = null;
      row.classList.remove("is-dragging");
    });
    row.addEventListener("dragover", (event) => {
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      row.classList.add("is-drop-target");
    });
    row.addEventListener("dragleave", () => row.classList.remove("is-drop-target"));
    row.addEventListener("drop", (event) => {
      event.preventDefault();
      const from = app.draggedEditorIndex ?? Number(event.dataTransfer.getData("text/plain"));
      row.classList.remove("is-drop-target");
      if (Number.isInteger(from) && from !== index) {
        const [moved] = app.editorItems.splice(from, 1);
        app.editorItems.splice(index, 0, moved);
        renderGroupEditor();
      }
    });
    row.append(handle, badge, fields, controls);
    els["group-item-editor-list"].append(row);
  });
}

function editorControl(label, ariaLabel, action, disabled = false) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "editor-icon-button";
  button.textContent = label;
  button.setAttribute("aria-label", ariaLabel);
  button.disabled = disabled;
  button.addEventListener("click", action);
  return button;
}

function moveEditorItem(index, delta) {
  const target = index + delta;
  if (target < 0 || target >= app.editorItems.length) return;
  [app.editorItems[index], app.editorItems[target]] = [app.editorItems[target], app.editorItems[index]];
  renderGroupEditor();
}

function removeEditorItem(index) {
  app.editorItems.splice(index, 1);
  renderGroupEditor();
}

async function saveTask(event) {
  event.preventDefault();
  const taskId = els["task-id"].value;
  const taskType = els["task-type"].value;
  const payload = {
    title: els["task-title"].value,
    details: els["task-details"].value,
    task_type: taskType,
    domain: els["task-domain"].value,
    cadence: els["task-cadence"].value,
    due_date: els["task-cadence"].value === "long_term" ? els["task-due-date"].value || null : null,
  };
  if (taskType === "group") {
    payload.children = app.editorItems.map((item) => ({
      id: item.id,
      title: item.title,
      details: item.details,
      item_type: item.item_type,
    }));
    if (!payload.children.some((item) => item.item_type === "task" && item.title.trim())) {
      els["form-error"].textContent = "Add at least one named child task.";
      return;
    }
  }
  try {
    const response = await api(taskId ? `/api/tasks/${taskId}` : "/api/tasks", {
      method: taskId ? "PATCH" : "POST",
      body: payload,
    });
    if (taskType === "group") {
      const groupId = Number(taskId || response.task?.id);
      if (groupId) {
        app.openGroups.add(groupId);
        localStorage.setItem("todo.openGroups", JSON.stringify([...app.openGroups]));
      }
    }
    closeTaskDialog();
    app.openDomain = payload.domain;
    localStorage.setItem("todo.openDomain", app.openDomain);
    await refreshAll();
  } catch (error) {
    els["form-error"].textContent = error.message;
  }
}

async function archiveCurrentTask() {
  const id = Number(els["task-id"].value);
  if (!id) return;
  try {
    await api(`/api/tasks/${id}/archive`, { method: "POST", body: {} });
    closeTaskDialog();
    showToast("Task moved to archive");
    await refreshAll();
  } catch (error) {
    els["form-error"].textContent = error.message;
  }
}

async function pauseCurrentTask() {
  const id = Number(els["task-id"].value);
  const task = app.taskMap.get(id);
  if (!task) return;
  try {
    await api(`/api/tasks/${id}/pause`, { method: "POST", body: { paused: !task.is_paused } });
    closeTaskDialog();
    showToast(task.is_paused ? "Daily task resumed" : "Daily task paused");
    await refreshAll();
  } catch (error) {
    els["form-error"].textContent = error.message;
  }
}

async function moveCurrentTask(direction) {
  const id = Number(els["task-id"].value);
  if (!id) return;
  try {
    await api(`/api/tasks/${id}/move`, { method: "POST", body: { direction } });
    closeTaskDialog();
    await refreshAll();
  } catch (error) {
    els["form-error"].textContent = error.message;
  }
}

async function openArchive() {
  try {
    const payload = await api("/api/archive");
    els["archive-list"].replaceChildren();
    if (!payload.tasks.length) {
      els["archive-list"].append(els["empty-template"].content.cloneNode(true));
    } else {
      payload.tasks.forEach((task) => {
        const row = document.createElement("div");
        row.className = "archive-row";
        const copy = document.createElement("div");
        const title = document.createElement("strong");
        title.textContent = task.title;
        const meta = document.createElement("span");
        meta.textContent = `${domainName(task.domain)} · ${task.cadence === "daily" ? "Daily" : "Long Term"}${task.task_type === "group" ? " · Group" : ""}`;
        copy.append(title, meta);
        const restore = document.createElement("button");
        restore.type = "button";
        restore.className = "ghost-button";
        restore.textContent = "Restore";
        restore.addEventListener("click", () => restoreArchived(task.id));
        row.append(copy, restore);
        els["archive-list"].append(row);
      });
    }
    if (!els["archive-dialog"].open) els["archive-dialog"].showModal();
  } catch (error) {
    showToast(error.message);
  }
}

async function restoreArchived(taskId) {
  try {
    await api(`/api/tasks/${taskId}/restore`, { method: "POST", body: {} });
    await openArchive();
    await refreshAll();
  } catch (error) {
    showToast(error.message);
  }
}

async function refreshCalendar() {
  const year = app.calendarCursor.getFullYear();
  const month = app.calendarCursor.getMonth() + 1;
  app.calendar = await api(`/api/calendar?month=${year}-${String(month).padStart(2, "0")}`);
  renderCalendar();
}

function renderCalendar() {
  if (!app.calendar) return;
  const { year, month, days } = app.calendar;
  const monthDate = new Date(year, month - 1, 1);
  els["calendar-heading"].textContent = new Intl.DateTimeFormat("en", { month: "long", year: "numeric" }).format(monthDate);
  els["calendar-grid"].replaceChildren();
  const mondayOffset = (monthDate.getDay() + 6) % 7;
  for (let index = 0; index < mondayOffset; index += 1) {
    const filler = document.createElement("span");
    filler.className = "calendar-day is-outside";
    els["calendar-grid"].append(filler);
  }
  days.forEach((day) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "calendar-day";
    button.textContent = Number(day.date.slice(-2));
    button.dataset.status = day.status;
    button.setAttribute("aria-label", calendarAria(day));
    if (app.state && day.date === app.state.today) button.classList.add("is-today");
    if (day.date === app.selectedCalendarDate) button.classList.add("is-selected");
    button.addEventListener("click", () => selectCalendarDay(day));
    els["calendar-grid"].append(button);
  });
}

function selectCalendarDay(day) {
  app.selectedCalendarDate = day.date;
  renderCalendar();
  if (!day.total) {
    els["calendar-detail"].textContent = `${formatLongDate(day.date)} · No active daily tasks.`;
  } else if (day.missing) {
    els["calendar-detail"].textContent = `${formatLongDate(day.date)} · ${day.completed}/${day.total} complete, ${day.missing} missed.`;
  } else {
    els["calendar-detail"].textContent = `${formatLongDate(day.date)} · All ${day.total} daily tasks complete.`;
  }
}

function calendarAria(day) {
  if (!day.total) return `${formatLongDate(day.date)}, no daily tasks`;
  return `${formatLongDate(day.date)}, ${day.completed} of ${day.total} daily tasks complete`;
}

async function shiftMonth(delta) {
  app.calendarCursor = new Date(app.calendarCursor.getFullYear(), app.calendarCursor.getMonth() + delta, 1);
  app.selectedCalendarDate = null;
  els["calendar-detail"].textContent = "Select a day to inspect its daily check-in.";
  try {
    await refreshCalendar();
  } catch (error) {
    showToast(error.message);
  }
}

function showToast(message, undoable = false) {
  clearTimeout(app.undoTimer);
  els["toast-message"].textContent = message;
  els["toast-undo"].classList.toggle("is-hidden", !undoable);
  els["toast"].classList.add("is-visible");
  app.undoTimer = setTimeout(() => {
    els["toast"].classList.remove("is-visible");
    if (undoable) app.undo = null;
  }, 5000);
}

async function performUndo() {
  if (!app.undo) return;
  const undo = app.undo;
  app.undo = null;
  clearTimeout(app.undoTimer);
  els["toast"].classList.remove("is-visible");
  try {
    if (undo.kind === "group_item") {
      await api(`/api/groups/${undo.taskId}/children/${undo.itemId}/undo`, {
        method: "POST",
        body: { date: undo.date },
      });
    } else {
      await api(`/api/tasks/${undo.id}/undo`, { method: "POST", body: { date: undo.date } });
    }
    await refreshAll();
  } catch (error) {
    showToast(error.message);
  }
}

function closeDialogFromBackdrop(event) {
  if (event.target === event.currentTarget) event.currentTarget.close();
}

function showFatal(message) {
  els["domain-stack"].innerHTML = `<section class="domain-card is-open"><div class="domain-toggle"><span class="domain-mark">!</span><span class="domain-title"><strong>Unable to load</strong><span></span></span></div><div style="padding:0 22px 22px;color:var(--danger)"></div></section>`;
  els["domain-stack"].querySelector(".domain-title span").textContent = message;
}

function domainName(id) {
  return DOMAIN_DEFS.find((domain) => domain.id === id)?.name || id;
}

function formatShortDate(value) {
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric" }).format(new Date(`${value}T12:00:00`));
}

function formatLongDate(value) {
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric", year: "numeric" }).format(new Date(`${value}T12:00:00`));
}

function localDay() {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function scheduleMidnightRefresh() {
  const now = new Date();
  const next = new Date(now);
  next.setHours(24, 0, 2, 0);
  setTimeout(async () => {
    await refreshAll();
    scheduleMidnightRefresh();
  }, next.getTime() - now.getTime());
}

function reducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function wait(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}
