import os
import sqlite3
import secrets
import sys
from datetime import date
from functools import wraps

from flask import (
    Flask, g, session, request, redirect, url_for,
    render_template, flash, abort
)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
DB = os.path.join(os.path.dirname(__file__), "taskflow.db")


def conn():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    c = g.pop("db", None)
    if c:
        c.close()


def init_db():
    """Create tables and safely migrate the old manager/developer schema."""
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=OFF")
    c.execute("DROP TABLE IF EXISTS users_new")
    # Create the users table only when this is a fresh database.
    exists = c.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()
    if not exists:
        c.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin','manager','developer'))
            )
        """)
    else:
        sql = c.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()[0] or ""
        if "'admin'" not in sql:
            c.execute("""
                CREATE TABLE users_new (
                    id INTEGER PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('admin','manager','developer'))
                )
            """)
            c.execute("""
                INSERT INTO users_new(id,username,password_hash,full_name,role)
                SELECT id,username,password_hash,full_name,role FROM users
            """)
            c.execute("DROP TABLE users")
            c.execute("ALTER TABLE users_new RENAME TO users")

    c.executescript("""
        CREATE TABLE IF NOT EXISTS projects(
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            deadline TEXT NOT NULL,
            manager_id INTEGER NOT NULL REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS tasks(
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            description TEXT,
            assigned_to INTEGER NOT NULL REFERENCES users(id),
            deadline TEXT NOT NULL,
            completed INTEGER DEFAULT 0,
            completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS subtasks(
            id INTEGER PRIMARY KEY,
            task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            description TEXT,
            created_by INTEGER NOT NULL REFERENCES users(id),
            deadline TEXT NOT NULL,
            completed INTEGER DEFAULT 0,
            completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS comments(
            id INTEGER PRIMARY KEY,
            task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
            subtask_id INTEGER REFERENCES subtasks(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id),
            body TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            CHECK((task_id IS NOT NULL AND subtask_id IS NULL) OR
                  (task_id IS NULL AND subtask_id IS NOT NULL))
        );
    """)
    # Snapshot names preserve historical attribution if an account is removed.
    sub_cols = {r[1] for r in c.execute("PRAGMA table_info(subtasks)")}
    if "creator_name" not in sub_cols:
        c.execute("ALTER TABLE subtasks ADD COLUMN creator_name TEXT")
    comment_cols = {r[1] for r in c.execute("PRAGMA table_info(comments)")}
    if "author_name" not in comment_cols:
        c.execute("ALTER TABLE comments ADD COLUMN author_name TEXT")

    # Preserve the original demo accounts only for a brand-new database.
    if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        c.executemany(
            "INSERT INTO users(username,password_hash,full_name,role) VALUES(?,?,?,?)",
            [
                ("manager", generate_password_hash("manager123"), "Project Manager", "manager"),
                ("developer1", generate_password_hash("dev123"), "Alice", "developer"),
                ("developer2", generate_password_hash("dev123"), "Bob", "developer"),
            ],
        )
    c.commit()
    c.execute("PRAGMA foreign_keys=ON")
    c.close()


@app.before_request
def csrf():
    if request.method == "POST":
        token = request.form.get("_csrf", "")
        if not session.get("csrf") or not secrets.compare_digest(session["csrf"], token):
            abort(400, "Invalid form token. Refresh and try again.")


@app.context_processor
def globals():
    session.setdefault("csrf", secrets.token_urlsafe(24))
    return {"csrf": session["csrf"], "today": date.today().isoformat()}


def login_required(f):
    @wraps(f)
    def w(*a, **kw):
        if not session.get("uid"):
            return redirect(url_for("login"))
        return f(*a, **kw)
    return w


def role_required(*roles):
    def dec(f):
        @wraps(f)
        @login_required
        def w(*a, **kw):
            if session.get("role") not in roles:
                abort(403)
            return f(*a, **kw)
        return w
    return dec


def task_status(x):
    if x["completed"]:
        return "green" if (x["completed_at"] or "9999")[:10] <= x["deadline"] else "red"
    return "red" if x["deadline"] < date.today().isoformat() else "pending"


def task_access(tid):
    t = conn().execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    if not t:
        abort(404)
    if session["role"] == "developer" and t["assigned_to"] != session["uid"]:
        abort(403)
    return t


@app.route("/")
def home():
    return redirect(url_for("dashboard") if session.get("uid") else url_for("login"))


@app.route("/setup-admin", methods=["GET", "POST"])
def setup_admin():
    """Allow browser setup of the first admin only."""
    c = conn()
    if c.execute("SELECT 1 FROM users WHERE role='admin' LIMIT 1").fetchone():
        flash("Admin setup is already complete. Please sign in.", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        full_name = request.form.get("full_name", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        if (not username or len(username) > 80 or not full_name or
                len(full_name) > 120 or len(password) < 12 or password != confirm):
            flash("Enter a username and full name. Passwords must match and be at least 12 characters.", "error")
            return render_template("setup_admin.html")

        try:
            # Lock the database before checking again, preventing two first admins.
            c.execute("BEGIN IMMEDIATE")
            exists = c.execute(
                "SELECT 1 FROM users WHERE role='admin' LIMIT 1"
            ).fetchone()
            if exists:
                c.rollback()
                flash("Admin setup has already been completed. Please sign in.", "error")
                return redirect(url_for("login"))

            c.execute(
                "INSERT INTO users(username,password_hash,full_name,role) VALUES(?,?,?,'admin')",
                (username, generate_password_hash(password), full_name),
            )
            c.commit()
            flash("Admin account created successfully. Please sign in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            c.rollback()
            flash("That username is already in use.", "error")

    return render_template("setup_admin.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = conn().execute(
            "SELECT * FROM users WHERE username=?",
            (request.form.get("username", "").strip(),),
        ).fetchone()
        if u and check_password_hash(u["password_hash"], request.form.get("password", "")):
            session.clear()
            session.update(uid=u["id"], role=u["role"], csrf=secrets.token_urlsafe(24))
            return redirect(url_for("dashboard"))
        flash("Incorrect username or password.", "error")
    setup_available = not conn().execute(
        "SELECT 1 FROM users WHERE role='admin' LIMIT 1"
    ).fetchone()
    return render_template("login.html", setup_available=setup_available)


@app.post("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    c = conn()
    if session["role"] in ("admin", "manager"):
        projects = c.execute("""
            SELECT p.*, (SELECT COUNT(*) FROM tasks t WHERE t.project_id=p.id) n
            FROM projects p ORDER BY deadline
        """).fetchall()
        tasks = c.execute("""
            SELECT t.*,p.name project,u.full_name developer
            FROM tasks t JOIN projects p ON p.id=t.project_id
            JOIN users u ON u.id=t.assigned_to ORDER BY t.deadline
        """).fetchall()
    else:
        projects = c.execute("""
            SELECT DISTINCT p.*,
              (SELECT COUNT(*) FROM tasks t WHERE t.project_id=p.id AND t.assigned_to=?) n
            FROM projects p JOIN tasks x ON x.project_id=p.id
            WHERE x.assigned_to=? ORDER BY p.deadline
        """, (session["uid"], session["uid"])).fetchall()
        tasks = c.execute("""
            SELECT t.*,p.name project,u.full_name developer
            FROM tasks t JOIN projects p ON p.id=t.project_id
            JOIN users u ON u.id=t.assigned_to
            WHERE t.assigned_to=? ORDER BY t.deadline
        """, (session["uid"],)).fetchall()
    return render_template("dashboard.html", projects=projects, tasks=tasks, status=task_status)


@app.route("/admin", methods=["GET"])
@role_required("admin")
def admin_panel():
    c = conn()
    users = c.execute("""
        SELECT u.*,
          (SELECT COUNT(*) FROM tasks t WHERE t.assigned_to=u.id) assigned_tasks,
          (SELECT COUNT(*) FROM projects p WHERE p.manager_id=u.id) managed_projects
        FROM users u ORDER BY
          CASE u.role WHEN 'admin' THEN 0 WHEN 'manager' THEN 1 ELSE 2 END,
          u.full_name
    """).fetchall()
    projects = c.execute("""
        SELECT p.*,u.full_name manager FROM projects p
        JOIN users u ON u.id=p.manager_id ORDER BY p.deadline
    """).fetchall()
    return render_template("admin.html", users=users, projects=projects)


@app.post("/admin/users")
@role_required("admin")
def admin_user_new():
    username = request.form.get("username", "").strip()
    full_name = request.form.get("full_name", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "")
    if role not in ("manager", "developer") or not username or not full_name or len(password) < 8:
        flash("Enter a username, full name, valid role, and password of at least 8 characters.", "error")
        return redirect(url_for("admin_panel"))
    try:
        conn().execute(
            "INSERT INTO users(username,password_hash,full_name,role) VALUES(?,?,?,?)",
            (username, generate_password_hash(password), full_name, role),
        )
        conn().commit()
        flash(f"{role.title()} account created.", "success")
    except sqlite3.IntegrityError:
        conn().rollback()
        flash("That username is already in use.", "error")
    return redirect(url_for("admin_panel"))


@app.post("/admin/users/<int:uid>/delete")
@role_required("admin")
def admin_user_delete(uid):
    if uid == session["uid"]:
        flash("You cannot delete the account you are currently using.", "error")
        return redirect(url_for("admin_panel"))
    c = conn()
    target = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not target or target["role"] == "admin":
        flash("That account cannot be deleted.", "error")
        return redirect(url_for("admin_panel"))
    if target["role"] == "developer":
        assigned = c.execute("SELECT COUNT(*) FROM tasks WHERE assigned_to=?", (uid,)).fetchone()[0]
        if assigned:
            flash(f"Cannot remove {target['full_name']}: reassign their {assigned} task(s) first.", "error")
            return redirect(url_for("admin_panel"))
    if target["role"] == "manager":
        owned = c.execute("SELECT COUNT(*) FROM projects WHERE manager_id=?", (uid,)).fetchone()[0]
        if owned:
            flash(f"Cannot remove {target['full_name']}: reassign their {owned} project(s) first.", "error")
            return redirect(url_for("admin_panel"))
    # Preserve comment/subtask attribution while moving required foreign keys to the acting admin.
    c.execute("UPDATE comments SET author_name=COALESCE(author_name, (SELECT full_name FROM users WHERE id=?)), user_id=? WHERE user_id=?", (uid, session["uid"], uid))
    c.execute("UPDATE subtasks SET creator_name=COALESCE(creator_name, (SELECT full_name FROM users WHERE id=?)), created_by=? WHERE created_by=?", (uid, session["uid"], uid))
    c.execute("DELETE FROM users WHERE id=?", (uid,))
    c.commit()
    flash(f"{target['role'].title()} account removed. Historical comments and subtasks were preserved.", "success")
    return redirect(url_for("admin_panel"))


@app.route("/projects/new", methods=["GET", "POST"])
@role_required("admin", "manager")
def project_new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        deadline = request.form.get("deadline", "")
        if not name or not deadline:
            flash("Project name and deadline are required.", "error")
        else:
            cur = conn().execute(
                "INSERT INTO projects(name,description,deadline,manager_id) VALUES(?,?,?,?)",
                (name, request.form.get("description", "").strip(), deadline, session["uid"]),
            )
            conn().commit()
            return redirect(url_for("project", pid=cur.lastrowid))
    return render_template("project_new.html")


@app.post("/projects/<int:pid>/delete")
@role_required("admin", "manager")
def project_delete(pid):
    c = conn()
    p = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    if not p:
        abort(404)
    c.execute("DELETE FROM projects WHERE id=?", (pid,))
    c.commit()
    flash("Project and its tasks, subtasks, and comments were deleted.", "success")
    return redirect(url_for("dashboard"))


@app.post("/admin/projects/<int:pid>/reassign")
@role_required("admin")
def project_reassign(pid):
    manager_id = request.form.get("manager_id", type=int)
    valid = conn().execute(
        "SELECT id FROM users WHERE id=? AND role='manager'", (manager_id,)
    ).fetchone()
    if not valid:
        flash("Choose a valid project manager.", "error")
    else:
        conn().execute("UPDATE projects SET manager_id=? WHERE id=?", (manager_id, pid))
        conn().commit()
        flash("Project ownership updated.", "success")
    return redirect(url_for("admin_panel"))


@app.route("/projects/<int:pid>")
@login_required
def project(pid):
    c = conn()
    p = c.execute("""
        SELECT p.*,u.full_name manager FROM projects p
        JOIN users u ON u.id=p.manager_id WHERE p.id=?
    """, (pid,)).fetchone()
    if not p:
        abort(404)
    if session["role"] == "developer" and not c.execute(
        "SELECT 1 FROM tasks WHERE project_id=? AND assigned_to=?", (pid, session["uid"])
    ).fetchone():
        abort(403)
    ts = c.execute("""
        SELECT t.*,u.full_name developer FROM tasks t
        JOIN users u ON u.id=t.assigned_to WHERE t.project_id=? ORDER BY t.deadline
    """, (pid,)).fetchall()
    if session["role"] == "developer":
        ts = [t for t in ts if t["assigned_to"] == session["uid"]]
    subs = {
        t["id"]: c.execute("""
            SELECT s.*,COALESCE(s.creator_name,u.full_name) creator
            FROM subtasks s JOIN users u ON u.id=s.created_by
            WHERE s.task_id=? ORDER BY s.deadline
        """, (t["id"],)).fetchall()
        for t in ts
    }
    devs = c.execute("SELECT id,full_name FROM users WHERE role='developer' ORDER BY full_name").fetchall()
    return render_template("project.html", p=p, tasks=ts, subs=subs, devs=devs, status=task_status)


@app.post("/projects/<int:pid>/tasks")
@role_required("manager", "admin")
def task_new(pid):
    if not conn().execute("SELECT id FROM projects WHERE id=?", (pid,)).fetchone():
        abort(404)
    title = request.form.get("title", "").strip()
    deadline = request.form.get("deadline", "")
    who = request.form.get("assigned_to", type=int)
    valid = conn().execute("SELECT id FROM users WHERE id=? AND role='developer'", (who,)).fetchone()
    if title and deadline and valid:
        conn().execute(
            "INSERT INTO tasks(project_id,title,description,assigned_to,deadline) VALUES(?,?,?,?,?)",
            (pid, title, request.form.get("description", "").strip(), who, deadline),
        )
        conn().commit()
        flash("Task assigned.", "success")
    else:
        flash("Provide a title, deadline and valid developer.", "error")
    return redirect(url_for("project", pid=pid))


@app.post("/tasks/<int:tid>/complete")
@login_required
def task_complete(tid):
    t = task_access(tid)
    done = request.form.get("done") == "1"
    conn().execute(
        "UPDATE tasks SET completed=?,completed_at=? WHERE id=?",
        (int(done), date.today().isoformat() if done else None, tid),
    )
    conn().commit()
    return redirect(url_for("project", pid=t["project_id"]))


@app.post("/tasks/<int:tid>/subtasks")
@role_required("developer")
def subtask_new(tid):
    t = task_access(tid)
    title = request.form.get("title", "").strip()
    deadline = request.form.get("deadline", "")
    if title and deadline:
        conn().execute(
            "INSERT INTO subtasks(task_id,title,description,created_by,deadline) VALUES(?,?,?,?,?)",
            (tid, title, request.form.get("description", "").strip(), session["uid"], deadline),
        )
        conn().commit()
        flash("Subtask added.", "success")
    else:
        flash("Subtask title and deadline are required.", "error")
    return redirect(url_for("project", pid=t["project_id"]))


@app.post("/subtasks/<int:sid>/complete")
@login_required
def subtask_complete(sid):
    s = conn().execute("""
        SELECT s.*,t.project_id,t.assigned_to FROM subtasks s
        JOIN tasks t ON t.id=s.task_id WHERE s.id=?
    """, (sid,)).fetchone()
    if not s:
        abort(404)
    if session["role"] == "developer" and s["assigned_to"] != session["uid"]:
        abort(403)
    done = request.form.get("done") == "1"
    conn().execute(
        "UPDATE subtasks SET completed=?,completed_at=? WHERE id=?",
        (int(done), date.today().isoformat() if done else None, sid),
    )
    conn().commit()
    return redirect(url_for("project", pid=s["project_id"]))


def add_comment(task_id=None, subtask_id=None):
    body = request.form.get("body", "").strip()
    if body:
        conn().execute(
            "INSERT INTO comments(task_id,subtask_id,user_id,body) VALUES(?,?,?,?)",
            (task_id, subtask_id, session["uid"], body[:3000]),
        )
        conn().commit()


@app.post("/tasks/<int:tid>/comments")
@login_required
def task_comment(tid):
    t = task_access(tid)
    add_comment(task_id=tid)
    return redirect(url_for("project", pid=t["project_id"]))


@app.post("/subtasks/<int:sid>/comments")
@login_required
def sub_comment(sid):
    s = conn().execute("""
        SELECT s.id,t.project_id,t.assigned_to FROM subtasks s
        JOIN tasks t ON t.id=s.task_id WHERE s.id=?
    """, (sid,)).fetchone()
    if not s:
        abort(404)
    if session["role"] == "developer" and s["assigned_to"] != session["uid"]:
        abort(403)
    add_comment(subtask_id=sid)
    return redirect(url_for("project", pid=s["project_id"]))


@app.context_processor
def helpers():
    def comments(task_id=None, subtask_id=None):
        key = "task_id" if task_id is not None else "subtask_id"
        val = task_id if task_id is not None else subtask_id
        return conn().execute(f"""
            SELECT c.*,COALESCE(c.author_name,u.full_name) full_name
            FROM comments c JOIN users u ON u.id=c.user_id
            WHERE c.{key}=? ORDER BY c.created_at
        """, (val,)).fetchall()
    return {"comments": comments}


@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", code=403, message="You do not have permission to view this page."), 403


@app.errorhandler(404)
def missing(e):
    return render_template("error.html", code=404, message="That item could not be found."), 404


@app.errorhandler(400)
def bad(e):
    return render_template("error.html", code=400, message=getattr(e, "description", "Bad request.")), 400


def create_admin():
    """Create the first admin interactively; never ship a default admin password."""
    import getpass
    init_db()
    username = input("Admin username: ").strip()
    full_name = input("Admin full name: ").strip()
    password = getpass.getpass("Admin password (minimum 12 characters): ")
    confirm = getpass.getpass("Confirm password: ")
    if not username or not full_name or len(password) < 12 or password != confirm:
        print("Invalid details or passwords do not match. No admin created.")
        return
    c = sqlite3.connect(DB)
    try:
        c.execute(
            "INSERT INTO users(username,password_hash,full_name,role) VALUES(?,?,?,'admin')",
            (username, generate_password_hash(password), full_name),
        )
        c.commit()
        print("Admin account created. Sign in using the username you chose.")
    except sqlite3.IntegrityError:
        print("That username already exists.")
    finally:
        c.close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "create-admin":
        create_admin()
    else:
        init_db()
        app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
