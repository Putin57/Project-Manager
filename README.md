
# Project Manager

A lightweight project and task management web application built with Python, Flask, and SQLite.

## Features

### Manager
- Create and manage projects.
- Create tasks and assign them to developers.
- Set task deadlines.
- Monitor task progress.
- View project and task information.

### Developer
- View assigned tasks.
- Create and manage subtasks.
- Update task and subtask completion status.
- Add comments to tasks and subtasks.

### General
- Role-based access control.
- SQLite database.
- Password hashing.
- CSRF protection.
- Responsive dark-green user interface.
- Deadline status indicators.

## Technology Stack
- Python
- Flask
- SQLite
- HTML
- CSS

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/putin57/Project-Manager.git
cd Project-Manager
```

### 2. Create a virtual environment

```bash
python3 -m venv venv
```

### 3. Activate the environment

```bash
source venv/bin/activate
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Run the application

```bash
python app.py
```

Open http://127.0.0.1:5000 in your browser.

## Demo Accounts

| Role | Username | Password |
|---|---|---|
| Manager | manager | manager123 |
| Developer | developer1 | dev123 |
| Developer | developer2 | dev123 |

These are development demo credentials. Change them before any real deployment.

## Contributing

Contributions are welcome!

1. Fork this repository.
2. Create a new branch.
3. Make your changes.
4. Test your changes.
5. Submit a Pull Request.

## License

This project is licensed under the MIT License.

See the [LICENSE](LICENSE) file.

## Author

**Mahidul Islam**

GitHub: [@putin57](https://github.com/putin57)
