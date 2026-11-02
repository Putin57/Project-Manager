# 🚀 Project Manager

<p align="center">
  **A Simple, Secure & Efficient Project Management System**
  
  Manage projects, organize tasks, assign developers, track deadlines, and collaborate — all in one place.
</p>

<p align="center">
  ![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
  ![Flask](https://img.shields.io/badge/Flask-3.x-black?logo=flask&logoColor=white)
  ![SQLite](https://img.shields.io/badge/Database-SQLite-003B57?logo=sqlite&logoColor=white)
  ![License](https://img.shields.io/badge/License-MIT-green.svg)
</p>

---

## 📌 Overview

**Project Manager** is a lightweight, web-based project and task management application built with Python, Flask, and SQLite.

It provides a centralized workspace where administrators can manage users, managers can organize projects and assign tasks, and developers can track their work, create subtasks, and communicate through comments.

The application features a responsive dark-green interface, role-based access control, and deadline monitoring.

## ✨ Features

### 🔐 Administration
- One-time browser-based registration of the first Admin account.
- Secure password hashing.
- Admin dashboard for managing users.
- Create Manager and Developer accounts.
- Manage project ownership and user assignments.

### 📊 Manager
- Create and manage projects.
- Divide projects into manageable tasks.
- Assign tasks to developers.
- Set task deadlines.
- Monitor project and task progress.
- View project details and updates.

### 💻 Developer
- View assigned tasks.
- Create and manage subtasks.
- Update task and subtask completion status.
- Add comments to tasks and subtasks.
- Track deadlines and assigned work.

### ⚙️ General
- Role-based access control.
- SQLite database.
- CSRF protection.
- Secure password storage.
- Responsive dark-green user interface.
- Deadline status indicators.
- Task and project management in one application.

## 🖥️ Interface Preview

<!-- Add screenshots of your application here -->
<!-- Example:
![Login Page](screenshots/login.png)
![Admin Dashboard](screenshots/admin-dashboard.png)
![Project Dashboard](screenshots/dashboard.png)
-->

*Application screenshots coming soon.*

## 🛠️ Technology Stack

| Technology | Purpose |
|---|---|
| Python | Backend programming |
| Flask | Web application framework |
| SQLite | Database |
| HTML5 | Page structure |
| CSS3 | Styling and responsive interface |

## 📥 Installation & Setup

Follow these steps to run the application locally.

### 1. Clone the repository

```bash
git clone https://github.com/putin57/Project-Manager.git
cd Project-Manager
```

### 2. Create a virtual environment

```bash
python3 -m venv venv
```

### 3. Activate the virtual environment

**Linux / macOS:**

```bash
source venv/bin/activate
```

**Windows:**

```bash
venv\Scripts\activate
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Start the application

```bash
python app.py
```

### 6. Open the application

Visit the following address in your browser:

**http://127.0.0.1:5000**

## 👑 Initial Admin Setup

The application supports browser-based registration of the first administrator.

1. Open the application in your browser.
2. Navigate to the login page.
3. Click **Create the first Admin account**.
4. Enter your username and full name.
5. Create a strong password (at least 12 characters).
6. Submit the registration form.
7. Sign in using your new Admin credentials.

**Important:** The initial Admin registration page becomes unavailable after the first Admin account is created.

## 👥 User Roles

| Role | Responsibilities |
|---|---|
| Admin | Manage users and oversee the application |
| Manager | Create projects, assign tasks, and monitor progress |
| Developer | Work on assigned tasks, create subtasks, and add comments |

## 📁 Project Structure

```text
Project-Manager/
│
├── app.py
├── requirements.txt
├── README.md
├── LICENSE
│
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── setup_admin.html
│   ├── admin.html
│   ├── dashboard.html
│   ├── project.html
│   ├── project_new.html
│   └── error.html
│
└── static/
    └── style.css
```

## 🔒 Security Notes

- Passwords are stored using secure password hashing.
- CSRF protection is enabled for form submissions.
- User access is controlled through roles.
- The first Admin account can only be registered once.

For production deployment, configure a persistent, secret `SECRET_KEY`, use HTTPS, and avoid exposing development demo credentials.

## 🗺️ Future Improvements

- Advanced project analytics and reporting.
- Email notifications for task assignments and deadlines.
- Improved project progress visualization.
- File attachments for tasks.
- Team activity tracking.

## 🤝 Contributing

Contributions, suggestions, and bug reports are welcome!

1. Fork this repository.
2. Create a new branch.
3. Make your changes.
4. Test your changes.
5. Submit a Pull Request.

## 📄 License

This project is licensed under the **MIT License**.

See the [LICENSE](LICENSE) file for details.

## 👨‍💻 Author

**Mahidul Islam**

- GitHub: [@putin57](https://github.com/putin57)

---

<p align="center">
  ⭐ If you find this project useful, consider giving it a star!
</p>
