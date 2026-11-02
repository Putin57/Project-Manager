import os, sqlite3, secrets
from datetime import date
from functools import wraps
from flask import Flask, g, session, request, redirect, url_for, render_template, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
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
    if c: c.close()

def init_db():
    c = sqlite3.connect(DB)
    c.executescript("""
    PRAGMA foreign_keys=ON;
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, full_name TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('manager','developer')));
    CREATE TABLE IF NOT EXISTS projects(id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT, deadline TEXT NOT NULL, manager_id INTEGER NOT NULL REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE, title TEXT NOT NULL, description TEXT, assigned_to INTEGER NOT NULL REFERENCES users(id), deadline TEXT NOT NULL, completed INTEGER DEFAULT 0, completed_at TEXT);
    CREATE TABLE IF NOT EXISTS subtasks(id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE, title TEXT NOT NULL, description TEXT, created_by INTEGER NOT NULL REFERENCES users(id), deadline TEXT NOT NULL, completed INTEGER DEFAULT 0, completed_at TEXT);
    CREATE TABLE IF NOT EXISTS comments(id INTEGER PRIMARY KEY, task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE, subtask_id INTEGER REFERENCES subtasks(id) ON DELETE CASCADE, user_id INTEGER NOT NULL REFERENCES users(id), body TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP, CHECK((task_id IS NOT NULL AND subtask_id IS NULL) OR (task_id IS NULL AND subtask_id IS NOT NULL)));
    """)
    if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        c.executemany("INSERT INTO users(username,password_hash,full_name,role) VALUES(?,?,?,?)", [
            ("manager", generate_password_hash("manager123"), "Project Manager", "manager"),
            ("developer1", generate_password_hash("dev123"), "Alice", "developer"),
            ("developer2", generate_password_hash("dev123"), "Bob", "developer")])
    c.commit(); c.close()

@app.before_request
def csrf():
    if request.method == "POST":
        if not session.get("csrf") or not secrets.compare_digest(session["csrf"], request.form.get("_csrf","")):
            abort(400, "Invalid form token. Refresh and try again.")

@app.context_processor
def globals():
    session.setdefault("csrf", secrets.token_urlsafe(24))
    return {"csrf": session["csrf"], "today": date.today().isoformat()}

def login_required(f):
    @wraps(f)
    def w(*a, **kw):
        if not session.get("uid"): return redirect(url_for("login"))
        return f(*a, **kw)
    return w

def role_required(role):
    def dec(f):
        @wraps(f)
        @login_required
        def w(*a, **kw):
            if session.get("role") != role: abort(403)
            return f(*a, **kw)
        return w
    return dec

def task_status(x):
    if x["completed"]:
        return "green" if (x["completed_at"] or "9999")[:10] <= x["deadline"] else "red"
    return "red" if x["deadline"] < date.today().isoformat() else "pending"

def task_access(tid):
    t = conn().execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    if not t: abort(404)
    if session["role"] == "developer" and t["assigned_to"] != session["uid"]: abort(403)
    return t

@app.route("/")
def home(): return redirect(url_for("dashboard") if session.get("uid") else url_for("login"))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = conn().execute("SELECT * FROM users WHERE username=?", (request.form.get("username","").strip(),)).fetchone()
        if u and check_password_hash(u["password_hash"], request.form.get("password","")):
            session.clear(); session.update(uid=u["id"], role=u["role"], csrf=secrets.token_urlsafe(24))
            return redirect(url_for("dashboard"))
        flash("Incorrect username or password.", "error")
    return render_template("login.html")

@app.post("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    c=conn()
    if session["role"]=="manager":
        projects=c.execute("SELECT p.*, (SELECT COUNT(*) FROM tasks t WHERE t.project_id=p.id) n FROM projects p ORDER BY deadline").fetchall()
        tasks=c.execute("SELECT t.*,p.name project,u.full_name developer FROM tasks t JOIN projects p ON p.id=t.project_id JOIN users u ON u.id=t.assigned_to ORDER BY t.deadline").fetchall()
    else:
        projects=c.execute("SELECT DISTINCT p.*, (SELECT COUNT(*) FROM tasks t WHERE t.project_id=p.id AND t.assigned_to=?) n FROM projects p JOIN tasks x ON x.project_id=p.id WHERE x.assigned_to=?",(session["uid"],session["uid"])).fetchall()
        tasks=c.execute("SELECT t.*,p.name project,u.full_name developer FROM tasks t JOIN projects p ON p.id=t.project_id JOIN users u ON u.id=t.assigned_to WHERE t.assigned_to=? ORDER BY t.deadline",(session["uid"],)).fetchall()
    return render_template("dashboard.html", projects=projects, tasks=tasks, status=task_status)

@app.route("/projects/new", methods=["GET","POST"])
@role_required("manager")
def project_new():
    if request.method=="POST":
        name=request.form.get("name","").strip(); deadline=request.form.get("deadline","")
        if not name or not deadline: flash("Project name and deadline are required.","error")
        else:
            cur=conn().execute("INSERT INTO projects(name,description,deadline,manager_id) VALUES(?,?,?,?)",(name,request.form.get("description","").strip(),deadline,session["uid"]))
            conn().commit(); return redirect(url_for("project",pid=cur.lastrowid))
    return render_template("project_new.html")

@app.route("/projects/<int:pid>")
@login_required
def project(pid):
    c=conn()
    p=c.execute("SELECT p.*,u.full_name manager FROM projects p JOIN users u ON u.id=p.manager_id WHERE p.id=?",(pid,)).fetchone()
    if not p: abort(404)
    if session["role"]=="developer" and not c.execute("SELECT 1 FROM tasks WHERE project_id=? AND assigned_to=?",(pid,session["uid"])).fetchone(): abort(403)
    ts=c.execute("SELECT t.*,u.full_name developer FROM tasks t JOIN users u ON u.id=t.assigned_to WHERE t.project_id=? ORDER BY t.deadline",(pid,)).fetchall()
    if session["role"]=="developer": ts=[t for t in ts if t["assigned_to"]==session["uid"]]
    subs={t["id"]:c.execute("SELECT s.*,u.full_name creator FROM subtasks s JOIN users u ON u.id=s.created_by WHERE s.task_id=? ORDER BY s.deadline",(t["id"],)).fetchall() for t in ts}
    devs=c.execute("SELECT id,full_name FROM users WHERE role='developer' ORDER BY full_name").fetchall()
    return render_template("project.html",p=p,tasks=ts,subs=subs,devs=devs,status=task_status)

@app.post("/projects/<int:pid>/tasks")
@role_required("manager")
def task_new(pid):
    if not conn().execute("SELECT id FROM projects WHERE id=?",(pid,)).fetchone(): abort(404)
    title=request.form.get("title","").strip(); deadline=request.form.get("deadline",""); who=request.form.get("assigned_to",type=int)
    valid=conn().execute("SELECT id FROM users WHERE id=? AND role='developer'",(who,)).fetchone()
    if title and deadline and valid:
        conn().execute("INSERT INTO tasks(project_id,title,description,assigned_to,deadline) VALUES(?,?,?,?,?)",(pid,title,request.form.get("description","").strip(),who,deadline)); conn().commit()
        flash("Task assigned.","success")
    else: flash("Provide a title, deadline and valid developer.","error")
    return redirect(url_for("project",pid=pid))

@app.post("/tasks/<int:tid>/complete")
@login_required
def task_complete(tid):
    t=task_access(tid); done=request.form.get("done")=="1"
    conn().execute("UPDATE tasks SET completed=?,completed_at=? WHERE id=?",(int(done),date.today().isoformat() if done else None,tid)); conn().commit()
    return redirect(url_for("project",pid=t["project_id"]))

@app.post("/tasks/<int:tid>/subtasks")
@role_required("developer")
def subtask_new(tid):
    t=task_access(tid); title=request.form.get("title","").strip(); deadline=request.form.get("deadline","")
    if title and deadline:
        conn().execute("INSERT INTO subtasks(task_id,title,description,created_by,deadline) VALUES(?,?,?,?,?)",(tid,title,request.form.get("description","").strip(),session["uid"],deadline)); conn().commit()
        flash("Subtask added.","success")
    else: flash("Subtask title and deadline are required.","error")
    return redirect(url_for("project",pid=t["project_id"]))

@app.post("/subtasks/<int:sid>/complete")
@login_required
def subtask_complete(sid):
    s=conn().execute("SELECT s.*,t.project_id,t.assigned_to FROM subtasks s JOIN tasks t ON t.id=s.task_id WHERE s.id=?",(sid,)).fetchone()
    if not s: abort(404)
    if session["role"]=="developer" and s["assigned_to"]!=session["uid"]: abort(403)
    done=request.form.get("done")=="1"
    conn().execute("UPDATE subtasks SET completed=?,completed_at=? WHERE id=?",(int(done),date.today().isoformat() if done else None,sid)); conn().commit()
    return redirect(url_for("project",pid=s["project_id"]))

def add_comment(task_id=None, subtask_id=None):
    body=request.form.get("body","").strip()
    if body:
        conn().execute("INSERT INTO comments(task_id,subtask_id,user_id,body) VALUES(?,?,?,?)",(task_id,subtask_id,session["uid"],body[:3000])); conn().commit()

@app.post("/tasks/<int:tid>/comments")
@login_required
def task_comment(tid):
    t=task_access(tid); add_comment(task_id=tid); return redirect(url_for("project",pid=t["project_id"]))

@app.post("/subtasks/<int:sid>/comments")
@login_required
def sub_comment(sid):
    s=conn().execute("SELECT s.id,t.project_id,t.assigned_to FROM subtasks s JOIN tasks t ON t.id=s.task_id WHERE s.id=?",(sid,)).fetchone()
    if not s: abort(404)
    if session["role"]=="developer" and s["assigned_to"]!=session["uid"]: abort(403)
    add_comment(subtask_id=sid); return redirect(url_for("project",pid=s["project_id"]))

@app.context_processor
def helpers():
    def comments(task_id=None,subtask_id=None):
        key="task_id" if task_id is not None else "subtask_id"; val=task_id if task_id is not None else subtask_id
        return conn().execute(f"SELECT c.*,u.full_name FROM comments c JOIN users u ON u.id=c.user_id WHERE c.{key}=? ORDER BY c.created_at",(val,)).fetchall()
    return {"comments":comments}

@app.errorhandler(403)
def forbidden(e): return render_template("error.html",code=403,message="You do not have permission to view this page."),403
@app.errorhandler(404)
def missing(e): return render_template("error.html",code=404,message="That item could not be found."),404
@app.errorhandler(400)
def bad(e): return render_template("error.html",code=400,message=getattr(e,"description","Bad request.")),400

if __name__=="__main__":
    init_db()
    app.run(debug=True)


