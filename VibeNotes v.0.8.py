from datetime import datetime, timedelta
import json
import os
import subprocess
import sys
import threading
from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template_string,
    request,
    url_for,
)

app = Flask("VibeNotes")
app.secret_key = "vibenotes_secret_key"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_PATH = os.path.join(BASE_DIR, "vibenotes_data.json")

# Debounced git push variables
_git_timer = None


def delayed_git_push():
  global _git_timer
  try:
    commit_message = f"Auto-update VibeNotes data at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
    subprocess.run(["git", "add", FILE_PATH], cwd=BASE_DIR, check=True)
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
    )
    if status.stdout.strip():
      subprocess.run(
          ["git", "commit", "-m", commit_message], cwd=BASE_DIR, check=True
      )
      subprocess.run(
          ["git", "push", "origin", "main"], cwd=BASE_DIR, check=True
      )
      print(f"Successfully pushed VibeNotes updates to GitHub", file=sys.stderr)
    else:
      print(
          "No changes detected in vibenotes_data.json; skipping push.",
          file=sys.stderr,
      )
  except Exception as e:
    print(f"Git push failed: {e}", file=sys.stderr)
  finally:
    _git_timer = None


def auto_push_to_github():
  global _git_timer
  if _git_timer is not None:
    _git_timer.cancel()
  _git_timer = threading.Timer(30.0, delayed_git_push)
  _git_timer.start()


def init_json():
  if not os.path.exists(FILE_PATH):
    default_data = {
        "pages": {
            "1": {
                "id": 1,
                "name": "My First List",
                "is_expiring": False,
                "created_at": datetime.utcnow().isoformat(),
                "tasks": {},
                "task_order": [],
            }
        },
        "next_page_id": 2,
        "next_task_id": 1,
    }
    with open(FILE_PATH, "w") as f:
      json.dump(default_data, f, indent=4)


init_json()


def load_data():
  with open(FILE_PATH, "r") as f:
    return json.load(f)


def save_data(data):
  with open(FILE_PATH, "w") as f:
    json.dump(data, f, indent=4)
  auto_push_to_github()


# --- HELPER LOGIC FOR PAGES & TASKS ---
def get_page_remaining_days(page):
  if not page.get("is_expiring", False):
    return None
  created_at = datetime.fromisoformat(page["created_at"])
  elapsed = (datetime.utcnow() - created_at).days
  left = 7 - elapsed
  return max(0, left)


@app.template_filter("helper_remaining")
def helper_remaining(page):
  return get_page_remaining_days(page)


@app.template_filter("parse_date_str")
def parse_date_str(date_str):
  if not date_str:
    return None
  try:
    return datetime.fromisoformat(date_str)
  except Exception:
    return None


# --- FRONTEND TEMPLATE (HTML + CSS + JS) ---
TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VibeNotes</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body { background-color: #121212; color: #e0e0e0; font-family: system-ui, -apple-system, sans-serif; }
        .tab-active { background-color: #1e1e1e; border-bottom: 2px solid #3b82f6; color: #ffffff; }
        .tab-inactive { background-color: #181818; color: #9ca3af; }
        .task-card { background-color: #1e1e1e; transition: transform 0.2s ease, opacity 0.2s ease; }
    </style>
</head>
<body class="min-h-screen flex flex-col">

    <!-- Header / Tab Bar -->
    <header class="bg-[#181818] border-b border-gray-800 px-2 py-2 sticky top-0 z-50">
        <div class="flex items-center space-x-1 flex-wrap gap-y-2">
            {% for pid, p in pages.items() %}
                {% set rem = p | helper_remaining %}
                {% set title = (p.name ~ " (" ~ rem ~ ")") if p.is_expiring else p.name %}
                <div class="relative flex items-center px-4 py-2 rounded-lg whitespace-nowrap {{ 'tab-active' if current_page_id == pid else 'tab-inactive' }}">
                    <a href="{{ url_for('index', page_id=pid) }}" class="text-sm font-medium mr-1">{{ title }}</a>
                    
                    <!-- Page Settings Dropdown Trigger (⌄) -->
                    <button onclick="toggleMenu(event, '{{ pid }}')" class="text-gray-400 hover:text-white px-1.5 py-0.5 text-xs font-mono font-bold rounded hover:bg-gray-700/50" title="Page Settings">⌄</button>

                    <!-- Dropdown Menu -->
                    <div id="menu-{{ pid }}" class="hidden absolute top-full left-0 mt-1 bg-[#242424] border border-gray-700 rounded-lg shadow-2xl py-1.5 z-[9999] text-xs min-w-[140px]">
                        <button onclick="renamePage('{{ pid }}', '{{ p.name }}')" class="w-full text-left px-3 py-2 text-gray-300 hover:bg-gray-700 flex items-center gap-2"><i class="fa-solid fa-pen w-3"></i> Rename</button>
                        <button onclick="duplicatePage('{{ pid }}')" class="w-full text-left px-3 py-2 text-gray-300 hover:bg-gray-700 flex items-center gap-2"><i class="fa-solid fa-copy w-3"></i> Duplicate</button>
                        <button onclick="toggleType('{{ pid }}')" class="w-full text-left px-3 py-2 text-gray-300 hover:bg-gray-700 flex items-center gap-2"><i class="fa-solid fa-clock w-3"></i> Toggle Type</button>
                        {% if pages | length > 1 %}
                        <div class="border-t border-gray-700 my-1"></div>
                        <button onclick="deletePage('{{ pid }}')" class="w-full text-left px-3 py-2 text-red-400 hover:bg-gray-700 flex items-center gap-2"><i class="fa-solid fa-trash w-3"></i> Delete</button>
                        {% endif %}
                    </div>
                </div>
            {% endfor %}
            <button onclick="openCreateModal()" class="px-3 py-2 text-blue-400 hover:bg-gray-800 rounded-lg text-lg font-bold" title="Add Page">+</button>
        </div>
    </header>

    <!-- Page Creation Modal -->
    <div id="create-modal" class="hidden fixed inset-0 bg-black/70 flex items-center justify-center z-[99999] p-4">
        <div class="bg-[#1e1e1e] border border-gray-700 rounded-xl p-5 w-full max-w-sm shadow-2xl">
            <h3 class="text-lg font-bold text-white mb-4">Create New Page</h3>
            <input type="text" id="modal-page-name" placeholder="Page name..." class="w-full bg-[#121212] border border-gray-700 rounded-lg px-3 py-2.5 text-white mb-4 focus:outline-none focus:border-blue-500 text-sm">
            <label class="flex items-center gap-2.5 mb-5 cursor-pointer select-none">
                <input type="checkbox" id="modal-is-expiring" class="w-4 h-4 accent-blue-500 rounded">
                <span class="text-sm text-gray-300">Expiring page (expires in 7 days)</span>
            </label>
            <div class="flex justify-end gap-2">
                <button onclick="closeCreateModal()" class="px-4 py-2 rounded-lg text-sm bg-gray-800 text-gray-300 hover:bg-gray-700">Cancel</button>
                <button onclick="submitCreatePage()" class="px-4 py-2 rounded-lg text-sm bg-blue-600 text-white hover:bg-blue-500 font-medium">Create</button>
            </div>
        </div>
    </div>

    <!-- Main Content -->
    {% if current_page %}
    <main class="flex-1 max-w-2xl w-full mx-auto p-4 pb-24">
        <div class="flex justify-between items-center mb-6">
            <h1 class="text-xl font-bold text-white">
                {{ current_page.name }} 
                <span class="text-xs font-normal px-2 py-0.5 rounded {{ 'bg-amber-900 text-amber-200' if current_page.is_expiring else 'bg-blue-900 text-blue-200' }}">
                    {{ ('Expiring (' ~ (current_page | helper_remaining) ~ 'd left)') if current_page.is_expiring else 'Permanent' }}
                </span>
            </h1>
        </div>

        <!-- To-Do List Section -->
        <section class="mb-8">
            <h2 class="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-3">To-Do</h2>
            <div class="space-y-2" id="todo-list">
                
                <!-- Google Keep Style Quick-Add Row -->
                <div class="task-card flex items-center justify-between p-3 rounded-lg border border-blue-500/50 bg-[#252525]">
                    <div class="flex items-center gap-3 flex-1 mr-3">
                        <span class="w-5 h-5 flex items-center justify-center text-blue-400 text-sm"><i class="fa-solid fa-plus"></i></span>
                        <input type="text" id="quick-add-input" placeholder="New task..." 
                               onblur="quickAddTask('{{ current_page_id }}', this)" 
                               onkeydown="if(event.key === 'Enter') { this.blur(); }"
                               class="bg-transparent border-none text-white w-full focus:outline-none placeholder-gray-500">
                    </div>
                </div>

                {% set task_order = current_page.get('task_order', []) %}
                {% set tasks = current_page.get('tasks', {}) %}
                
                {# Build ordered list of todo tasks #}
                {% set todo_tasks = [] %}
                {% for tid in task_order %}
                    {% if tid in tasks and tasks[tid].status == 'todo' %}
                        {% set _ = todo_tasks.append((tid, tasks[tid])) %}
                    {% endif %}
                {% endfor %}
                {# Catch any tasks missing from task_order #}
                {% for tid, t in tasks.items() %}
                    {% if t.status == 'todo' and tid not in task_order %}
                        {% set _ = todo_tasks.append((tid, t)) %}
                    {% endif %}
                {% endfor %}

                {% for tid, task in todo_tasks %}
                <div class="task-card flex items-center justify-between p-3 rounded-lg border border-gray-800" data-id="{{ tid }}">
                    <div class="flex items-center gap-3 flex-1 mr-3">
                        <input type="checkbox" onchange="markDone('{{ current_page_id }}', '{{ tid }}')" class="w-5 h-5 accent-blue-500 cursor-pointer">
                        <input type="text" value="{{ task.text }}" onblur="updateTask('{{ current_page_id }}', '{{ tid }}', this.value)" class="bg-transparent border-none text-white w-full focus:outline-none focus:ring-1 focus:ring-blue-500 rounded px-1">
                    </div>
                    <div class="flex items-center gap-2">
                        <span class="text-xs text-gray-400 font-mono bg-gray-800 px-2 py-1 rounded" title="Days in To-Do">{{ task.todo_days }}d</span>
                        
                        <!-- Reorder Buttons -->
                        <div class="flex flex-col gap-0.5">
                            <button onclick="moveTask('{{ current_page_id }}', '{{ tid }}', 'up')" class="text-gray-500 hover:text-white text-[10px] px-1 bg-gray-900 rounded" title="Move Up"><i class="fa-solid fa-chevron-up"></i></button>
                            <button onclick="moveTask('{{ current_page_id }}', '{{ tid }}', 'down')" class="text-gray-500 hover:text-white text-[10px] px-1 bg-gray-900 rounded" title="Move Down"><i class="fa-solid fa-chevron-down"></i></button>
                        </div>

                        <button onclick="deleteTask('{{ current_page_id }}', '{{ tid }}')" class="text-gray-500 hover:text-red-400 text-sm ml-1"><i class="fa-solid fa-xmark"></i></button>
                    </div>
                </div>
                {% endfor %}
            </div>
        </section>

        <!-- Done List Section -->
        <section class="mb-6">
            <h2 class="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-3">Done (Most Recent)</h2>
            <div class="space-y-2" id="done-container">
                {% set done_tasks = [] %}
                {% for tid, t in tasks.items() %}
                    {% if t.status == 'done' %}
                        {% set _ = done_tasks.append((tid, t)) %}
                    {% endif %}
                {% endfor %}
                {% set sorted_done = done_tasks | sort(attribute='1.completed_at', reverse=True) %}

                {% if not sorted_done %}
                    <p class="text-sm text-gray-500 italic">No completed tasks.</p>
                {% endif %}
                
                {% for tid, task in sorted_done %}
                {% set c_date = task.completed_at | parse_date_str %}
                <div class="task-card done-item flex items-center justify-between p-3 rounded-lg border border-gray-800 opacity-75 {{ 'hidden' if loop.index > 5 and not show_all else '' }}">
                    <div class="flex items-center gap-3 flex-1 mr-3">
                        <input type="checkbox" checked onchange="markTodo('{{ current_page_id }}', '{{ tid }}')" class="w-5 h-5 accent-blue-500 cursor-pointer" title="Move back to To-Do">
                        <span class="line-through text-gray-400 text-sm">{{ task.text }}</span>
                    </div>
                    <div class="flex items-center gap-3">
                        <span class="text-xs text-gray-500 font-mono bg-gray-900 px-2 py-1 rounded" title="Completion Date">{{ c_date.strftime('%d/%m/%Y') if c_date else '' }}</span>
                        <button onclick="deleteTask('{{ current_page_id }}', '{{ tid }}')" class="text-gray-500 hover:text-red-400 text-sm"><i class="fa-solid fa-xmark"></i></button>
                    </div>
                </div>
                {% endfor %}

                {% if sorted_done | length > 5 %}
                <div class="text-center pt-2">
                    {% if show_all %}
                        <a href="{{ url_for('index', page_id=current_page_id, show_all=0) }}" class="text-xs text-blue-400 hover:underline">Show Less</a>
                    {% else %}
                        <a href="{{ url_for('index', page_id=current_page_id, show_all=1) }}" class="text-xs text-blue-400 hover:underline font-medium bg-gray-800 px-4 py-2 rounded-lg inline-block">Show More ({{ (sorted_done | length) - 5 }} older)</a>
                    {% endif %}
                </div>
                {% endif %}
            </div>
        </section>

        <!-- Export PDF Button -->
        <div class="mt-8 pt-4 border-t border-gray-800 text-center">
            <a href="{{ url_for('export_pdf', page_id=current_page_id) }}" class="inline-flex items-center gap-2 bg-[#252525] hover:bg-[#303030] text-gray-300 hover:text-white px-4 py-2.5 rounded-lg text-sm font-medium border border-gray-700 shadow transition">
                <i class="fa-solid fa-file-pdf text-red-400"></i> Export Current Page to PDF
            </a>
        </div>
    </main>
    {% endif %}

    <script>
        window.addEventListener('click', function(e) {
            document.querySelectorAll('[id^="menu-"]').forEach(menu => {
                if (!menu.contains(e.target) && !e.target.closest('button[onclick^="toggleMenu"]')) {
                    menu.classList.add('hidden');
                }
            });
        });

        function toggleMenu(event, id) {
            event.stopPropagation();
            document.querySelectorAll('[id^="menu-"]').forEach(m => {
                if (m.id !== 'menu-' + id) m.classList.add('hidden');
            });
            let menu = document.getElementById('menu-' + id);
            menu.classList.toggle('hidden');
        }

        function openCreateModal() {
            document.getElementById('modal-page-name').value = 'New List';
            document.getElementById('modal-is-expiring').checked = false;
            document.getElementById('create-modal').classList.remove('hidden');
            let input = document.getElementById('modal-page-name');
            input.focus();
            input.select();
        }

        function closeCreateModal() {
            document.getElementById('create-modal').classList.add('hidden');
        }

        function submitCreatePage() {
            let name = document.getElementById('modal-page-name').value.trim();
            let isExpiring = document.getElementById('modal-is-expiring').checked;
            if (name) {
                fetch('/page/create', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({name: name, is_expiring: isExpiring})
                }).then(() => location.reload());
            }
        }

        function renamePage(id, oldName) {
            let name = prompt("Rename page:", oldName);
            if (name) {
                fetch(`/page/${id}/rename`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({name: name})
                }).then(() => location.reload());
            }
        }
        function duplicatePage(id) {
            fetch(`/page/${id}/duplicate`, {method: 'POST'}).then(() => location.reload());
        }
        function toggleType(id) {
            fetch(`/page/${id}/toggle-type`, {method: 'POST'}).then(() => location.reload());
        }
        function deletePage(id) {
            if (confirm("Delete this page and all its tasks?")) {
                fetch(`/page/${id}/delete`, {method: 'POST'}).then(() => location.reload());
            }
        }
        function quickAddTask(pageId, inputElem) {
            let text = inputElem.value.trim();
            if (text.length > 0) {
                inputElem.value = ""; 
                fetch(`/page/${pageId}/task/add`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({text: text})
                }).then(() => location.reload());
            }
        }
        function markDone(pageId, taskId) {
            fetch(`/page/${pageId}/task/${taskId}/done`, {method: 'POST'}).then(() => location.reload());
        }
        function markTodo(pageId, taskId) {
            fetch(`/page/${pageId}/task/${taskId}/todo`, {method: 'POST'}).then(() => location.reload());
        }
        function updateTask(pageId, taskId, text) {
            fetch(`/page/${pageId}/task/${taskId}/update`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({text: text})
            });
        }
        function deleteTask(pageId, taskId) {
            fetch(`/page/${pageId}/task/${taskId}/delete`, {method: 'POST'}).then(() => location.reload());
        }
        function moveTask(pageId, taskId, direction) {
            fetch(`/page/${pageId}/task/${taskId}/move`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({direction: direction})
            }).then(() => location.reload());
        }
    </script>
</body>
</html>
"""


# --- BACKEND ROUTES ---
@app.route("/")
def index():
  data = load_data()
  pages = data.get("pages", {})
  if not pages:
    default_id = "1"
    pages[default_id] = {
        "id": 1,
        "name": "List",
        "is_expiring": False,
        "created_at": datetime.utcnow().isoformat(),
        "tasks": {},
        "task_order": [],
    }
    data["pages"] = pages
    data["next_page_id"] = 2
    save_data(data)

  page_id = request.args.get("page_id")
  if not page_id or page_id not in pages:
    page_id = list(pages.keys())[0]

  show_all = request.args.get("show_all", 0, type=int)
  current_page = pages[page_id]

  now = datetime.utcnow()
  changed = False

  for pid, p in pages.items():
    if "task_order" not in p:
      p["task_order"] = list(p.get("tasks", {}).keys())
      changed = True

    for tid, t in list(p.get("tasks", {}).items()):
      if t["status"] == "todo":
        last_active = datetime.fromisoformat(t["last_active_date"])
        if (now - last_active).days >= 1:
          t["todo_days"] += 1
          t["last_active_date"] = now.isoformat()
          changed = True
      elif t["status"] == "done" and t.get("completed_at"):
        completed = datetime.fromisoformat(t["completed_at"])
        if (now - completed).days >= 30:
          del p["tasks"][tid]
          if tid in p["task_order"]:
            p["task_order"].remove(tid)
          changed = True

  if changed:
    save_data(data)

  return render_template_string(
      TEMPLATE,
      pages=pages,
      current_page_id=page_id,
      current_page=current_page,
      show_all=show_all,
  )


@app.route("/page/<page_id>/export_pdf")
def export_pdf(page_id):
  data = load_data()
  pages = data.get("pages", {})
  if page_id not in pages:
    return redirect(url_for("index"))

  page = pages[page_id]
  lines = []
  lines.append(f"VibeNotes Export: {page['name']}")
  lines.append(
      f"Type: {'Expiring (7 days)' if page['is_expiring'] else 'Permanent'}"
  )
  lines.append("=" * 40)
  lines.append("\n[ TO-DO LIST ]")

  task_order = page.get("task_order", [])
  tasks = page.get("tasks", {})
  ordered_todos = [
      tasks[tid]
      for tid in task_order
      if tid in tasks and tasks[tid]["status"] == "todo"
  ]
  # Add any missing
  for tid, t in tasks.items():
    if t["status"] == "todo" and tid not in task_order:
      ordered_todos.append(t)

  if not ordered_todos:
    lines.append("  (No active tasks)")
  for t in ordered_todos:
    lines.append(f"  [ ] {t['text']}  ({t['todo_days']} days)")

  lines.append("\n[ DONE LIST ]")
  done_items = [t for t in tasks.values() if t["status"] == "done"]
  done_items.sort(key=lambda x: x.get("completed_at", ""), reverse=True)
  if not done_items:
    lines.append("  (No completed tasks)")
  for t in done_items:
    c_date = (
        datetime.fromisoformat(t["completed_at"]).strftime("%d/%m/%Y")
        if t.get("completed_at")
        else ""
    )
    lines.append(f"  [x] {t['text']}  (Completed: {c_date})")

  report_content = "\n".join(lines)
  filename = f"{page['name'].replace(' ', '_')}_export.txt"

  return Response(
      report_content,
      mimetype="text/plain",
      headers={"Content-Disposition": f"attachment; filename={filename}"},
  )


@app.route("/page/create", methods=["POST"])
def create_page():
  data = load_data()
  req = request.json or {}
  name = req.get("name", "Untitled")
  is_expiring = req.get("is_expiring", False)

  new_id = str(data.get("next_page_id", 2))
  data["next_page_id"] = int(new_id) + 1

  data["pages"][new_id] = {
      "id": int(new_id),
      "name": name,
      "is_expiring": is_expiring,
      "created_at": datetime.utcnow().isoformat(),
      "tasks": {},
      "task_order": [],
  }
  save_data(data)
  return jsonify({"success": True, "id": new_id})


@app.route("/page/<id>/rename", methods=["POST"])
def rename_page(id):
  data = load_data()
  if id in data["pages"]:
    data["pages"][id]["name"] = request.json.get(
        "name", data["pages"][id]["name"]
    )
    save_data(data)
  return jsonify({"success": True})


@app.route("/page/<id>/duplicate", methods=["POST"])
def duplicate_page(id):
  data = load_data()
  if id in data["pages"]:
    orig = data["pages"][id]
    new_id = str(data["next_page_id"])
    data["next_page_id"] += 1

    duplicated_tasks = {}
    for tid, t in orig["tasks"].items():
      duplicated_tasks[tid] = dict(t)

    data["pages"][new_id] = {
        "id": int(new_id),
        "name": f"{orig['name']} (Copy)",
        "is_expiring": orig["is_expiring"],
        "created_at": datetime.utcnow().isoformat(),
        "tasks": duplicated_tasks,
        "task_order": list(orig.get("task_order", [])),
    }
    save_data(data)
  return jsonify({"success": True})


@app.route("/page/<id>/toggle-type", methods=["POST"])
def toggle_type(id):
  data = load_data()
  if id in data["pages"]:
    p = data["pages"][id]
    p["is_expiring"] = not p["is_expiring"]
    p["created_at"] = datetime.utcnow().isoformat()
    save_data(data)
  return jsonify({"success": True})


@app.route("/page/<id>/delete", methods=["POST"])
def delete_page(id):
  data = load_data()
  if id in data["pages"] and len(data["pages"]) > 1:
    del data["pages"][id]
    save_data(data)
  return jsonify({"success": True})


@app.route("/page/<page_id>/task/add", methods=["POST"])
def add_task(page_id):
  data = load_data()
  if page_id in data["pages"]:
    req = request.get_json(silent=True) or {}
    text = req.get("text") or request.form.get("text")
    if text:
      tid = str(data.get("next_task_id", 1))
      data["next_task_id"] = int(tid) + 1

      data["pages"][page_id]["tasks"][tid] = {
          "text": text,
          "status": "todo",
          "todo_days": 0,
          "completed_at": None,
          "last_active_date": datetime.utcnow().isoformat(),
      }
      if "task_order" not in data["pages"][page_id]:
        data["pages"][page_id]["task_order"] = []
      data["pages"][page_id]["task_order"].append(tid)
      save_data(data)
  return jsonify({"success": True})


@app.route("/page/<page_id>/task/<tid>/done", methods=["POST"])
def mark_done(page_id, tid):
  data = load_data()
  if page_id in data["pages"] and tid in data["pages"][page_id]["tasks"]:
    t = data["pages"][page_id]["tasks"][tid]
    t["status"] = "done"
    t["completed_at"] = datetime.utcnow().isoformat()
    save_data(data)
  return jsonify({"success": True})


@app.route("/page/<page_id>/task/<tid>/todo", methods=["POST"])
def mark_todo(page_id, tid):
  data = load_data()
  if page_id in data["pages"] and tid in data["pages"][page_id]["tasks"]:
    t = data["pages"][page_id]["tasks"][tid]
    t["status"] = "todo"
    t["todo_days"] = 0
    t["completed_at"] = None
    t["last_active_date"] = datetime.utcnow().isoformat()
    if "task_order" not in data["pages"][page_id]:
      data["pages"][page_id]["task_order"] = []
    if tid not in data["pages"][page_id]["task_order"]:
      data["pages"][page_id]["task_order"].append(tid)
    save_data(data)
  return jsonify({"success": True})


@app.route("/page/<page_id>/task/<tid>/update", methods=["POST"])
def update_task(page_id, tid):
  data = load_data()
  if page_id in data["pages"] and tid in data["pages"][page_id]["tasks"]:
    text = request.json.get("text")
    if text is not None:
      data["pages"][page_id]["tasks"][tid]["text"] = text
      save_data(data)
  return jsonify({"success": True})


@app.route("/page/<page_id>/task/<tid>/delete", methods=["POST"])
def delete_task(page_id, tid):
  data = load_data()
  if page_id in data["pages"] and tid in data["pages"][page_id]["tasks"]:
    del data["pages"][page_id]["tasks"][tid]
    if tid in data["pages"][page_id].get("task_order", []):
      data["pages"][page_id]["task_order"].remove(tid)
    save_data(data)
  return jsonify({"success": True})


@app.route("/page/<page_id>/task/<tid>/move", methods=["POST"])
def move_task(page_id, tid):
  data = load_data()
  if page_id in data["pages"]:
    page = data["pages"][page_id]
    if "task_order" not in page:
      page["task_order"] = list(page.get("tasks", {}).keys())

    order = page["task_order"]
    if tid in order:
      idx = order.index(tid)
      direction = request.json.get("direction")
      if direction == "up" and idx > 0:
        order[idx], order[idx - 1] = order[idx - 1], order[idx]
        save_data(data)
      elif direction == "down" and idx < len(order) - 1:
        order[idx], order[idx + 1] = order[idx + 1], order[idx]
        save_data(data)
  return jsonify({"success": True})


if __name__ == "__main__":
  app.run(host="0.0.0.0", port=5000, debug=True)