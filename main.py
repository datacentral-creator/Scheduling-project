import datetime
import json
import math
import statistics
from pathlib import Path

from fastapi import FastAPI, Form
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.templating import Jinja2Templates

DATA_FILE = Path("data.json")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="static")


# ============================================================
# Utility Functions
# ============================================================

def load_data() -> dict:
    """Load the entire JSON dataset from disk."""
    with DATA_FILE.open() as f:
        return json.load(f)


def save_data(data: dict):
    """Save the full dataset back to disk."""
    with DATA_FILE.open("w") as f:
        json.dump(data, f, indent=2)


def parse_dt(dt_str: str) -> datetime.datetime:
    """Convert a 'YYYY-MM-DD:HH:MM' string into a datetime object."""
    return datetime.datetime.strptime(dt_str, "%Y-%m-%d:%H:%M")


def get_entry(data, dt_str):
    """Retrieve a specific entry from the dataset using a combined datetime key."""
    date, time = dt_str.split(":")[0], ":".join(dt_str.split(":")[1:])
    return data[date][time]


# ============================================================
# Routes
# ============================================================

@app.get("/")
@app.post("/")
async def root(request: Request):
    """Render the main interface."""
    return templates.TemplateResponse("main.html", {"request": request})


@app.get("/get_setpoints")
async def get_setpoints():
    """Return a list of all setpoint dates."""
    data = load_data()
    return list(data.get("setpoints", {}).keys())


@app.get("/get_setpoint/{dt}")
async def get_setpoint(req: Request, dt: str):
    """Return the setpoint information for a specific datetime."""
    data = load_data()
    setpoint = data["setpoints"][dt]

    keys = list(setpoint.keys())
    entries = [[k, v] for d in setpoint.values() for k, v in d.items()]

    return templates.TemplateResponse(
        "view_setpoints.html",
        {"request": req, "Keys": keys, "Entries": entries},
    )


# ============================================================
# Core Submit Logic
# ============================================================

@app.post("/submit")
async def submit_form(
    effort: str = Form(...),
    units: str = Form(...),
    date: str = Form(...),
    time: str = Form(...),
    tasks: str = Form(...),
    retention_factor: str = Form(...),
    n: str = Form(...),
):
    """
    Main endpoint for recording a study session.
    """

    data = load_data()
    dt_key = f"{date}:{time}"

    # Ensure difficulty dictionary exists
    data.setdefault("difficulty", {})
    data["difficulty"].setdefault(tasks, 1.0)  # initialize difficulty

    # --------------------------------------------------------
    # Store the raw entry
    # --------------------------------------------------------
    data.setdefault(date, {})
    data[date][time] = {
        "effort": effort,
        "units": units,
        "task": tasks,
        "retention_factor": retention_factor,
        "n": n,
    }

    # --------------------------------------------------------
    # Track task history
    # --------------------------------------------------------
    data.setdefault(tasks, [])
    data[tasks].append(dt_key)

    # Separate time-based vs repetition-based tasks
    reps = [dt for dt in data[tasks] if get_entry(data, dt)["units"] == "repetitions"]
    mins = [dt for dt in data[tasks] if get_entry(data, dt)["units"] == "minutes"]

    # --------------------------------------------------------
    # Difficulty Update (Asymmetric)
    # --------------------------------------------------------

    def update_difficulty(task, effort_val, units):
        """
        Update difficulty using an asymmetric rule:

        - If the item was harder than expected → update difficulty quickly
        - If the item was easier than expected → update difficulty slowly

        This makes difficulty stable for easy items (noise-prone)
        and adaptive for hard items (informative).
        """

        D_old = data["difficulty"][task]

        # Normalize effort
        if units == "minutes":
            effort_norm = min(float(effort_val) / 10, 5)
        else:
            effort_norm = min(float(effort_val) / 5, 5)

        # Asymmetric update:
        if effort_norm > D_old:
            # Harder than expected → update quickly
            D_new = 0.7 * D_old + 0.3 * effort_norm
        else:
            # Easier than expected → update slowly
            D_new = 0.95 * D_old + 0.05 * effort_norm

        data["difficulty"][task] = D_new
        return D_new

    D = update_difficulty(tasks, effort, units)

    # --------------------------------------------------------
    # Strength Update Logic
    # --------------------------------------------------------

    def compute_strength(prev_dt, current_dt,retention_factor_estimate, difficulty):
        """
        Compute memory strength using the previous review as the anchor.
        Difficulty scales the inferred strength.
        """
        delta = parse_dt(prev_dt) - parse_dt(current_dt)
        S_raw = 1 / (-math.log(float(retention_factor_estimate)) / delta.total_seconds())
        return S_raw / difficulty

    def update_strength(history_array):
        """Update memory strength using smoothing and difficulty."""

        anchor_dt = history_array[-2]
        last_dt = history_array[-1]
        last_entry = get_entry(data, last_dt)
        current_dt = parse_dt(dt_key)
        R_effort = 1 / (1 + math.exp((float(effort)/D) - 1))
        var_effort = R_effort * (1 - R_effort)
        k = 1 / var_effort
        w = int(n) / (int(n) + k)
        R_est = w * retention_factor + (1 - w) * R_effort

        new_raw_strength = compute_strength(anchor_dt, dt_key, R_est, D)

        if "strength" in last_entry:
            prev_strength = last_entry["strength"]

            time_diff = (current_dt - parse_dt(last_dt)).total_seconds()
            r_pred = math.exp(-time_diff / prev_strength)

            accept, _, _, r_min = test_retention_factor(
                float(retention_factor), r_pred, int(n)
            )

            if accept:
                data[date][time]["strength"] = (
                    0.75 * prev_strength + 0.25 * new_raw_strength
                )
            else:
                data[date][time]["strength"] = prev_strength
                data[date][time]["Retention_min"] = r_min

        else:
            data[date][time]["strength"] = new_raw_strength

    if units == "minutes" and len(mins) > 1:
        update_strength(mins)

    if units == "repetitions" and len(reps) > 1:
        update_strength(reps)

    save_data(data)
    return RedirectResponse("/", status_code=303)


# ============================================================
# Statistical Test
# ============================================================

def test_retention_factor(r_obs, r_pred, n, alpha=0.05):
    """Hypothesis test for retention improvement."""
    se = math.sqrt(r_pred * (1 - r_pred) / n)
    if se == 0:
        return False, (r_obs, r_obs), 0, r_pred

    z = (r_obs - r_pred) / se
    p_value = 1 - 0.5 * (1 + math.erf(z / math.sqrt(2)))

    zcrit = 1.96
    se_obs = math.sqrt(r_obs * (1 - r_obs) / n)
    margin = zcrit * se_obs
    ci = (r_obs - margin, r_obs + margin)

    accept = p_value < alpha

    z_alpha = 1.645
    r_min = max(0.0, min(1.0, r_pred + z_alpha * se))

    return accept, ci, p_value, r_min


# ============================================================
# Other Routes
# ============================================================

@app.get("/get_date/{date}")
async def get_data(date: str):
    """Return all entries for a given date."""
    data = load_data()
    return data.get(date)


@app.get("/get_datetime/{date}/{time}")
async def get_datetime(req: Request, date: str, time: str):
    """Return a specific entry for display."""
    data = load_data()
    chunk = data[date][time]

    return templates.TemplateResponse(
        "view_entry.html",
        {
            "request": req,
            "date": date,
            "time": time,
            "effort": chunk["effort"],
            "units": chunk["units"],
            "task": chunk["task"],
            "retention_factor": float(chunk["retention_factor"]),
            "Retention_min": float(chunk["Retention_min"]) if "Retention_min" in chunk else None,
        },
    )


@app.get("/get_task/{task}")
async def get_task(req: Request, task: str, scale="hours", period="50"):
    """Display the current strength and difficulty of a task."""
    data = load_data()
    if task not in data:
        return None

    last_dt = data[task][-1]
    last_entry = get_entry(data, last_dt)
    strength = last_entry.get("strength")
    difficulty = data["difficulty"].get(task, None)

    return templates.TemplateResponse(
        "view_task.html",
        {
            "request": req,
            "task": task,
            "Strength": strength,
            "Difficulty": difficulty,
            "scale": scale,
            "period": int(period),
        },
    )


@app.get("/get_task/{task}/{scale}/{period}")
async def get_task_with_scale(req: Request, task: str, scale: str, period: str):
    return await get_task(req, task, scale, period)


@app.post("/get_task/{task}")
async def post_task(req: Request, task: str):
    return await get_task(req, task)


@app.post("/get_task/{task}/{scale}/{period}")
async def post_task_with_scale(req: Request, task: str, scale: str, period: str):
    return await get_task(req, task, scale, period)


@app.post("/Create_setpoint/{task}")
async def create_setpoint(req: Request, task: str, retention_input: str = Form(...), date: str = Form(...), time: str = Form(...)):
    """Create or update a setpoint for a task."""
    data = load_data()
    data.setdefault("setpoints", {})
    data["setpoints"].setdefault(date, {})
    data["setpoints"][date][time] = {task: float(retention_input) / 100}

    save_data(data)
    return RedirectResponse(req.headers.get("Referer"), status_code=303)
