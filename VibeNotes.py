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
        .section-block + .section-block {
            border-top: 1px solid rgba(212, 175, 55, 0.65);
            padding-top: 1rem;
        }
        .move-menu { min-width: 150px; }
    </style>
</head>
<body class="min-h-screen flex flex-col">

    <!-- Header / Navbar -->
    <header class="bg-[#181818] border-b border-gray-800 px-3 py-2.5 sticky top-0 z-50 flex items-center justify-between flex-wrap gap-2">
        <!-- Logo -->
        <div class="flex items-center gap-2">
            <span class="text-blue-500 font-black tracking-wider text-base uppercase bg-blue-500/10 px-2.5 py-1 rounded-lg border border-blue-500/20">VibeNotes</span>
        </div>

        <!-- Tab Bar -->
        <div class="flex items-center space-x-1 flex-wrap gap-y-2">
            {% for pid, p in pages.items() %}
                {% set rem = p | helper_remaining %}
                {% set title = (p.name ~ " (" ~ rem ~ ")") if p.is_expiring else p.name %}
                <div class="relative flex items-center px-3 py-1.5 rounded-lg whitespace-nowrap {{ 'tab-active' if current_page_id == pid else 'tab-inactive' }}">
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
            <button onclick="openCreateModal()" class="px-2.5 py-1.5 text-blue-400 hover:bg-gray-800 rounded-lg text-base font-bold" title="Add Page">+</button>
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

        {% set task_order = current_page.get('task_order', []) %}
        {% set tasks = current_page.get('tasks', {}) %}

        {% set sections = [
            ('To-Do', 'todo'),
            ('Business Performance', 'bp'),
            ('Chapter', 'chapter'),
            ('Other', 'other')
        ] %}

        <!-- Active Sections Container -->
        <div id="active-sections-container">
            {% for sec_title, sec_key in sections %}
            <!-- Section: {{ sec_title }} -->
            <section class="mb-8 section-block" id="block-{{ sec_key }}" data-key="{{ sec_key }}">
                <div class="flex justify-between items-center mb-3">
                    <div class="flex items-center gap-2">
                        <h2 class="text-xs font-semibold uppercase tracking-wider text-gray-400 m-0">{{ sec_title }}</h2>
                        <!-- Section Reorder Buttons -->
                        <div class="flex gap-0.5">
                            <button onclick="moveSection('{{ current_page_id }}', '{{ sec_key }}', 'up')" class="text-gray-500 hover:text-white text-[10px] px-1 bg-gray-900 rounded" title="Move Section Up"><i class="fa-solid fa-chevron-up"></i></button>
                            <button onclick="moveSection('{{ current_page_id }}', '{{ sec_key }}', 'down')" class="text-gray-500 hover:text-white text-[10px] px-1 bg-gray-900 rounded" title="Move Section Down"><i class="fa-solid fa-chevron-down"></i></button>
                        </div>
                    </div>
                    <label class="flex items-center gap-1.5 text-xs text-gray-400 cursor-pointer select-none bg-[#1e1e1e] px-2 py-0.5 rounded border border-gray-800 hover:border-gray-700">
                        <input type="checkbox" onchange="toggleHideSection('{{ current_page_id }}', '{{ sec_key }}', this)" class="accent-blue-500 rounded hide-checkbox-{{ sec_key }}">
                        <span>Hide</span>
                    </label>
                </div>
                <div class="space-y-2 section-content-box" id="section-content-{{ sec_key }}">
                    
                    <!-- Quick-Add Row (1 Line Height) -->
                    <div class="task-card flex items-start justify-between p-3 rounded-lg border border-blue-500/50 bg-[#252525]">
                        <div class="flex items-start gap-3 flex-1 mr-3">
                            <span class="w-5 h-5 flex items-center justify-center text-blue-400 text-sm mt-1"><i class="fa-solid fa-plus"></i></span>
                            <textarea id="quick-add-{{ sec_key }}" placeholder="New {{ sec_title | lower }} task... " 
                                      rows="1"
                                      onblur="quickAddTask('{{ current_page_id }}', '{{ sec_key }}', this)" 
                                      onkeydown="if(event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); this.blur(); }"
                                      class="bg-transparent border-none text-white w-full focus:outline-none placeholder-gray-500 resize-y min-h-[44px]"></textarea>
                        </div>
                    </div>

                    {% set sec_tasks = [] %}
                    {% for tid in task_order %}
                        {% if tid in tasks and tasks[tid].status == sec_key %}
                            {% set _ = sec_tasks.append((tid, tasks[tid])) %}
                        {% endif %}
                    {% endfor %}
                    {% for tid, t in tasks.items() %}
                        {% if t.status == sec_key and tid not in task_order %}
                            {% set _ = sec_tasks.append((tid, t)) %}
                        {% endif %}
                    {% endfor %}

                    {% for tid, task in sec_tasks %}
                    <div class="task-card flex items-center justify-between p-3 rounded-lg border border-gray-800" data-id="{{ tid }}">
                        <div class="flex items-start gap-3 flex-1 mr-3">
                            <div class="relative flex flex-col items-stretch justify-center gap-2 shrink-0 self-center">
                                <button type="button" onclick="markDone('{{ current_page_id }}', '{{ tid }}')" class="min-w-[42px] px-2 py-1 text-[10px] text-blue-400 hover:text-blue-300 bg-gray-800 hover:bg-gray-700 rounded text-center whitespace-nowrap">Mark Done</button>
                                <button type="button" onclick="toggleMoveMenu(event, '{{ tid }}')" class="min-w-[42px] px-2 py-1 text-[10px] text-amber-300 hover:text-amber-200 bg-gray-800 hover:bg-gray-700 rounded text-center whitespace-nowrap">Move to</button>
                                <div id="move-menu-{{ tid }}" class="move-menu hidden absolute left-0 top-full mt-1 bg-[#242424] border border-gray-700 rounded-lg shadow-2xl py-1 z-[100]">
                                    {% for target_title, target_key in sections %}
                                        {% if target_key != sec_key %}
                                        <button type="button" onclick="moveTaskToSection('{{ current_page_id }}', '{{ tid }}', '{{ target_key }}')" class="w-full text-left px-3 py-2 text-xs text-gray-300 hover:bg-gray-700">{{ target_title }}</button>
                                        {% endif %}
                                    {% endfor %}
                                </div>
                            </div>
                            <textarea oninput="autoResizeTask(this)" onblur="updateTask('{{ current_page_id }}', '{{ tid }}', this.value)" rows="1" class="task-textarea bg-transparent border-none text-white w-full focus:outline-none focus:ring-1 focus:ring-blue-500 rounded px-1 resize-none overflow-hidden leading-6" style="height: 24px">{{ task.text }}</textarea>
                        </div>
                        <div class="flex items-center gap-3 shrink-0">
                            <!-- Days counter and delete button stacked to match -->
                            <div class="flex flex-col items-stretch gap-2">
                                <span class="min-w-[42px] text-center text-xs text-gray-400 font-mono bg-gray-800 px-2 py-1 rounded" title="Days in Task">{{ task.todo_days }}d</span>
                                <button type="button" onclick="deleteTask('{{ current_page_id }}', '{{ tid }}')"
                                        class="min-w-[42px] px-2 py-1 text-xs text-gray-500 hover:text-red-400 bg-gray-800 hover:bg-gray-700 rounded"
                                        title="Delete" aria-label="Delete">
                                    <i class="fa-solid fa-xmark"></i>
                                </button>
                            </div>

                            <!-- Two-by-two task reorder controls -->
                            <div class="grid grid-cols-2 gap-2">
                                <button type="button" onclick="moveTask('{{ current_page_id }}', '{{ tid }}', 'up')"
                                        class="min-w-[76px] px-2 py-2 text-[10px] text-gray-300 hover:text-white bg-gray-900 hover:bg-gray-700 rounded"
                                        title="Move Above" aria-label="Move Above">
                                    <i class="fa-solid fa-chevron-up mr-1"></i>
                                </button>
                                <button type="button" onclick="pushToTop('{{ current_page_id }}', '{{ tid }}')"
                                        class="min-w-[76px] px-2 py-2 text-[10px] text-blue-400 hover:text-white bg-gray-900 hover:bg-gray-700 rounded"
                                        title="Move to Top" aria-label="Move to Top">
                                    <i class="fa-solid fa-angles-up mr-1"></i>
                                </button>
                                <button type="button" onclick="moveTask('{{ current_page_id }}', '{{ tid }}', 'down')"
                                        class="min-w-[76px] px-2 py-2 text-[10px] text-gray-300 hover:text-white bg-gray-900 hover:bg-gray-700 rounded"
                                        title="Move Below" aria-label="Move Below">
                                    <i class="fa-solid fa-chevron-down mr-1"></i>
                                </button>
                                <button type="button" onclick="pushToBottom('{{ current_page_id }}', '{{ tid }}')"
                                        class="min-w-[76px] px-2 py-2 text-[10px] text-blue-400 hover:text-white bg-gray-900 hover:bg-gray-700 rounded"
                                        title="Move to Bottom" aria-label="Move to Bottom">
                                    <i class="fa-solid fa-angles-down mr-1"></i>
                                </button>
                            </div>

                        </div>
                    </div>
                    {% endfor %}
                </div>
            </section>
            {% endfor %}
        </div>

        <!-- Done List Section -->
        <section class="mb-6" id="done-section-block">
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
                        <div class="relative flex flex-col items-center gap-1 shrink-0">
                            <button type="button" onclick="markTodo('{{ current_page_id }}', '{{ tid }}')" class="text-[10px] text-blue-400 hover:text-blue-300 whitespace-nowrap">Mark Not Done</button>
                            <button type="button" onclick="toggleMoveMenu(event, '{{ tid }}')" class="text-[10px] text-amber-300 hover:text-amber-200 whitespace-nowrap">Move to</button>
                            <div id="move-menu-{{ tid }}" class="move-menu hidden absolute left-0 top-full mt-1 bg-[#242424] border border-gray-700 rounded-lg shadow-2xl py-1 z-[100]">
                                {% for target_title, target_key in sections %}
                                <button type="button" onclick="moveTaskToSection('{{ current_page_id }}', '{{ tid }}', '{{ target_key }}')" class="w-full text-left px-3 py-2 text-xs text-gray-300 hover:bg-gray-700">{{ target_title }}</button>
                                {% endfor %}
                            </div>
                        </div>
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

        <!-- Hidden Sections Container (Appears below Done) -->
        <div id="hidden-sections-container" class="space-y-4"></div>

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
        function quickAddTask(pageId, sectionKey, inputElem) {
            let text = inputElem.value.trim();
            if (text.length > 0) {
                inputElem.value = ""; 
                fetch(`/page/${pageId}/task/add`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({text: text, section: sectionKey})
                }).then(() => location.reload());
            }
        }
        function markDone(pageId, taskId) {
            fetch(`/page/${pageId}/task/${taskId}/done`, {method: 'POST'}).then(() => location.reload());
        }
        function markTodo(pageId, taskId) {
            fetch(`/page/${pageId}/task/${taskId}/todo`, {method: 'POST'}).then(() => location.reload());
        }

        function toggleMoveMenu(event, taskId) {
            event.stopPropagation();
            document.querySelectorAll('.move-menu').forEach(menu => {
                if (menu.id !== 'move-menu-' + taskId) menu.classList.add('hidden');
            });
            document.getElementById('move-menu-' + taskId).classList.toggle('hidden');
        }

        function moveTaskToSection(pageId, taskId, section) {
            fetch(`/page/${pageId}/task/${taskId}/move-section`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({section: section})
            }).then(() => location.reload());
        }

        document.addEventListener('click', function(event) {
            if (!event.target.closest('.move-menu') &&
                !event.target.closest('button[onclick^="toggleMoveMenu"]')) {
                document.querySelectorAll('.move-menu').forEach(menu => menu.classList.add('hidden'));
            }
        });
        function autoResizeTask(textarea) {
            // Reset first so the height can also shrink when text is deleted.
            textarea.style.height = 'auto';
            textarea.style.height = textarea.scrollHeight + 'px';
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
        function pushToTop(pageId, taskId) {
            fetch(`/page/${pageId}/task/${taskId}/push-top`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'}
            }).then(() => location.reload());
        }
        function pushToBottom(pageId, taskId) {
            fetch(`/page/${pageId}/task/${taskId}/push-bottom`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'}
            }).then(() => location.reload());
        }

        // Section Order & Hide / Move Logic
        function getOrderStorageKey(pageId) {
            return 'vibenotes_section_order_' + pageId;
        }

        function getHideStorageKey(pageId) {
            return 'vibenotes_hidden_sections_' + pageId;
        }

        function getDefaultSectionKeys() {
            return ['todo', 'bp', 'chapter', 'other'];
        }

        function loadSectionOrder(pageId) {
            try {
                let stored = localStorage.getItem(getOrderStorageKey(pageId));
                let keys = stored ? JSON.parse(stored) : getDefaultSectionKeys();
                let defaults = getDefaultSectionKeys();
                // Ensure all current keys are present if updated in code
                defaults.forEach(k => { if (!keys.includes(k)) keys.push(k); });
                return keys.filter(k => defaults.includes(k));
            } catch(e) {
                return getDefaultSectionKeys();
            }
        }

        function saveSectionOrder(pageId, orderArr) {
            localStorage.setItem(getOrderStorageKey(pageId), JSON.stringify(orderArr));
        }

        function loadHiddenSections(pageId) {
            try {
                let stored = localStorage.getItem(getHideStorageKey(pageId));
                return stored ? JSON.parse(stored) : [];
            } catch(e) {
                return [];
            }
        }

        function saveHiddenSections(pageId, hiddenArr) {
            localStorage.setItem(getHideStorageKey(pageId), JSON.stringify(hiddenArr));
        }

        function applySectionState(pageId) {
            let order = loadSectionOrder(pageId);
            let hidden = loadHiddenSections(pageId);
            let activeContainer = document.getElementById('active-sections-container');
            let hiddenContainer = document.getElementById('hidden-sections-container');

            // Reorder DOM elements according to stored section order
            order.forEach(key => {
                let block = document.getElementById('block-' + key);
                if (block) {
                    let checkbox = block.querySelector('input[type="checkbox"]');
                    let contentBox = block.querySelector('.section-content-box');
                    
                    if (hidden.includes(key)) {
                        if (checkbox) checkbox.checked = true;
                        if (contentBox) contentBox.classList.add('hidden');
                        block.classList.add('mb-2');
                        block.classList.remove('mb-8');
                        hiddenContainer.appendChild(block);
                    } else {
                        if (checkbox) checkbox.checked = false;
                        if (contentBox) contentBox.classList.remove('hidden');
                        block.classList.remove('mb-2');
                        block.classList.add('mb-8');
                        activeContainer.appendChild(block);
                    }
                }
            });
        }

        function toggleHideSection(pageId, sectionKey, checkbox) {
            let hidden = loadHiddenSections(pageId);
            if (checkbox.checked) {
                if (!hidden.includes(sectionKey)) hidden.push(sectionKey);
            } else {
                hidden = hidden.filter(k => k !== sectionKey);
            }
            saveHiddenSections(pageId, hidden);
            applySectionState(pageId);
        }

        function moveSection(pageId, sectionKey, direction) {
            let order = loadSectionOrder(pageId);
            let idx = order.indexOf(sectionKey);
            if (idx > -1) {
                if (direction === 'up' && idx > 0) {
                    order.splice(idx, 1);
                    order.splice(idx - 1, 0, sectionKey);
                } else if (direction === 'down' && idx < order.length - 1) {
                    order.splice(idx, 1);
                    order.splice(idx + 1, 0, sectionKey);
                }
                saveSectionOrder(pageId, order);
                applySectionState(pageId);
            }
        }

        document.addEventListener('DOMContentLoaded', function() {
            let currentPageId = "{{ current_page_id }}";
            if (currentPageId) {
                applySectionState(currentPageId);
            }
            document.querySelectorAll('.task-textarea').forEach(autoResizeTask);
        });
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
      # Aging logic for active tasks
      if t["status"] in ["todo", "bp", "chapter", "other"]:
        last_active = datetime.fromisoformat(t["last_active_date"])
        if (now - last_active).days >= 1:
          t["todo_days"] += 1
          t["last_active_date"] = now.isoformat()
          changed = True
      # Cleanup completed tasks after 60 days
      elif t["status"] == "done" and t.get("completed_at"):
        completed = datetime.fromisoformat(t["completed_at"])
        if (now - completed).days >= 60:
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

  task_order = page.get("task_order", [])
  tasks = page.get("tasks", {})

  for sec_name, sec_key in [
      ("TO-DO", "todo"),
      ("BUSINESS PERFORMANCE", "bp"),
      ("CHAPTER", "chapter"),
      ("MISC", "other"),
  ]:
    lines.append(f"\n[ {sec_name} ]")
    sec_tasks = [
        tasks[tid]
        for tid in task_order
        if tid in tasks and tasks[tid]["status"] == sec_key
    ]
    for tid, t in tasks.items():
      if t["status"] == sec_key and tid not in task_order:
        sec_tasks.append(t)

    if not sec_tasks:
      lines.append("  (No active tasks)")
    for t in sec_tasks:
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
    section = req.get("section", "todo")
    if text:
      tid = str(data.get("next_task_id", 1))
      data["next_task_id"] = int(tid) + 1

      data["pages"][page_id]["tasks"][tid] = {
          "text": text,
          "status": section,
          "todo_days": 0,
          "completed_at": None,
          "last_active_date": datetime.utcnow().isoformat(),
      }
      if "task_order" not in data["pages"][page_id]:
        data["pages"][page_id]["task_order"] = []
      data["pages"][page_id]["task_order"].insert(0, tid)
      save_data(data)
  return jsonify({"success": True})


@app.route("/page/<page_id>/task/<tid>/done", methods=["POST"])
def mark_done(page_id, tid):
  data = load_data()
  if page_id in data["pages"] and tid in data["pages"][page_id]["tasks"]:
    t = data["pages"][page_id]["tasks"][tid]
    # Remember the active section so "Mark Not Done" can restore it.
    if t.get("status") != "done" and t.get("status") in {"todo", "bp", "chapter", "other"}:
      t["return_status"] = t["status"]
    t["status"] = "done"
    t["completed_at"] = datetime.utcnow().isoformat()
    save_data(data)
  return jsonify({"success": True})


@app.route("/page/<page_id>/task/<tid>/todo", methods=["POST"])
def mark_todo(page_id, tid):
  data = load_data()
  if page_id in data["pages"] and tid in data["pages"][page_id]["tasks"]:
    t = data["pages"][page_id]["tasks"][tid]
    previous_section = t.get("return_status", "todo")
    if previous_section not in {"todo", "bp", "chapter", "other"}:
      previous_section = "todo"
    t["status"] = previous_section
    t.pop("return_status", None)
    t["completed_at"] = None
    t["last_active_date"] = datetime.utcnow().isoformat()
    if "task_order" not in data["pages"][page_id]:
      data["pages"][page_id]["task_order"] = []
    if tid not in data["pages"][page_id]["task_order"]:
      data["pages"][page_id]["task_order"].insert(0, tid)
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


@app.route("/page/<page_id>/task/<tid>/move-section", methods=["POST"])
def move_task_to_section(page_id, tid):
  data = load_data()
  valid_sections = {"todo", "bp", "chapter", "other"}
  target = (request.get_json(silent=True) or {}).get("section")

  if target not in valid_sections:
    return jsonify({"success": False, "error": "Invalid section"}), 400

  if page_id in data["pages"] and tid in data["pages"][page_id]["tasks"]:
    page = data["pages"][page_id]
    task = page["tasks"][tid]
    task["status"] = target
    task["completed_at"] = None
    task["last_active_date"] = datetime.utcnow().isoformat()

    if "task_order" not in page:
      page["task_order"] = list(page.get("tasks", {}).keys())
    if tid in page["task_order"]:
      page["task_order"].remove(tid)
    page["task_order"].insert(0, tid)
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


@app.route("/page/<page_id>/task/<tid>/push-top", methods=["POST"])
def push_top(page_id, tid):
  data = load_data()
  if page_id in data["pages"]:
    page = data["pages"][page_id]
    if "task_order" not in page:
      page["task_order"] = list(page.get("tasks", {}).keys())

    order = page["task_order"]
    if tid in order:
      order.remove(tid)
      order.insert(0, tid)
      save_data(data)
  return jsonify({"success": True})


@app.route("/page/<page_id>/task/<tid>/push-bottom", methods=["POST"])
def push_bottom(page_id, tid):
  data = load_data()
  if page_id in data["pages"]:
    page = data["pages"][page_id]
    if "task_order" not in page:
      page["task_order"] = list(page.get("tasks", {}).keys())

    order = page["task_order"]
    if tid in order:
      order.remove(tid)
      order.append(tid)
      save_data(data)
  return jsonify({"success": True})


if __name__ == "__main__":
  app.run(host="0.0.0.0", port=5000, debug=True)