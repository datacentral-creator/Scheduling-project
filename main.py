import datetime
import hashlib
import json
import math
import os
import re
from pathlib import Path

import aiofiles
from asyncio import Lock
from fastapi import FastAPI, Form
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.templating import Jinja2Templates
from llama_cpp import Llama
from cpuinfo import get_cpu_info
import psutil
from functools import lru_cache

# ============================================================
#  Global Configuration
# ============================================================

MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"

TASKS_FILE = Path("tasks.json")
SETPOINTS_FILE = Path("setpoints.json")

# Directory tracking
with Path("Directories.json").open() as f:
    file = json.load(f)
    file.setdefault("Latest_directory", "")
    globals()["Directory"] = Path(file["Latest_directory"])

# ============================================================
#  Model Configuration (CPU-only, llama.cpp only)
# ============================================================

SMALL_MODEL_PATH = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
BIG_MODEL_PATH   = "qwen2.5-7b-instruct-q4_k_m.gguf"

MODEL = None
BIG_MODEL = None
model_lock = Lock()
bigmodel_lock = Lock()

@lru_cache()
def detect_cpu_strength():
    info = get_cpu_info()
    model = info.get("brand_raw", "").lower()
    print("Model: ",model)
    threads = psutil.cpu_count(logical=True)

    if "i3" in model or "pentium" in model or threads <= 6:
        return "weak"
    if "i5" in model or "ryzen 5" in model:
        return "medium"
    return "strong"

@lru_cache()
def choose_model():
    cpu = detect_cpu_strength()

    if cpu == "weak":
        return {
            "model_path": SMALL_MODEL_PATH,
            "size": "small"
        }

    return {
        "model_path": BIG_MODEL_PATH,
        "size": "large"
    }

async def get_llm():
    global MODEL
    async with model_lock:
        if MODEL is None:
            config = choose_model()
            MODEL = Llama(
                model_path=config["model_path"],
                n_ctx=4096 if config["size"] == "small" else 8192,
                n_threads=psutil.cpu_count(logical=True),
                use_mmap=True,
                use_mlock=False
            )
    return MODEL

async def get_big_llm():
    global BIG_MODEL
    async with bigmodel_lock:
        if BIG_MODEL is not None:
            return BIG_MODEL

        BIG_MODEL = Llama(
            model_path=BIG_MODEL_PATH,
            n_ctx=8192,
            n_threads=psutil.cpu_count(logical=True),
            use_mmap=True,
            use_mlock=False
        )

    return BIG_MODEL
# ============================================================
#  LLM Wrapper
# ============================================================
async def run_llm(prompt: str, max_new_tokens=512, temperature=0.2) -> str:
    llm = await get_llm()

    full_prompt = (
        "You are a helpful assistant.\n\n"
        f"User: {prompt}\nAssistant:"
    )

    response = llm(
        full_prompt,
        max_tokens=max_new_tokens,
        temperature=temperature,
    )

    return response["choices"][0]["text"]

async def run_big_llm(prompt: str, max_new_tokens=800, temperature=0.2) -> str:
    llm = await get_big_llm()

    full_prompt = (
        "You are a highly capable assistant. "
        "Follow the instructions exactly and do not invent information.\n\n"
        f"User: {prompt}\nAssistant:"
    )

    response = llm(
        full_prompt,
        max_tokens=max_new_tokens,
        temperature=temperature,
    )

    return response["choices"][0]["text"]

# ============================================================
#  Unified Document Analysis
# ============================================================

async def analyse_document(text: str) -> dict:
    prompt = f"""
You are analysing a study document.

Important:
Numbered headings such as "1.", "1.1.", "1.2.", "2.", "2.1." are NOT questions.
They are section or subsection labels.
Do NOT classify a document as a questions-and-answers document unless it contains
actual questions (ending with a question mark) AND answers written by the user or numbered answers signified by ticks (./) or crosses (x/X).

Classify the document as exactly one of:
- "Informational document"
- "Questions and answers document"

Definitions:
- A "Questions and answers document" contains real questions (with ? or interrogatives)
  AND answers written by the user or a list of attempted answers signified by ./ or x/X
- An "Informational document" contains explanations, notes, summaries, or descriptions.

If the document is a questions-and-answers document, extract per-question metrics:
- effort
- units ("minutes" or "repetitions")
- retention_factor (X/n)
- n (number of attempts or subparts)
- feedback: Include the users strengths, weaknesses and inferred mark scheme 

Return ONLY valid JSON.
Wrap the JSON inside <json> ... </json> tags.


Document:
{text}
"""

    raw = await run_llm(prompt, max_new_tokens=900)
    print("Model output: ",raw)
    return safe_json_extract(raw)

def safe_json_extract(raw: str):
    # 1. Extract <json>...</json>
    match = re.search(r"<json>(.*?)</json>", raw, re.DOTALL)

    # 2. Fallback: ```json ... ```
    if not match:
        match = re.search(r"```json(.*?)```", raw, re.DOTALL)

    # 3. If still nothing, return safe default
    if not match:
        print("MODEL OUTPUT (no JSON block found):", raw)
        return {
            "classification": "Informational document",
            "questions": [],
            "feedback": ""
        }

    json_text = match.group(1).strip()

    # 4. Remove invalid LaTeX escapes
    json_text = json_text.replace("\\(", "(").replace("\\)", ")")

    # 5. First attempt: strict JSON
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        # 6. Attempt repair
        repaired = repair_json(json_text)
        try:
            data = json.loads(repaired)
        except json.JSONDecodeError as e:
            print("MODEL OUTPUT (unparseable JSON):", raw)
            print("JSON ERROR:", e)
            return {
                "classification": "Informational document",
                "questions": [],
                "feedback": ""
            }

    # 7. Normalise structure

    # Case A: new structure with "metrics"
    if "metrics" in data:
        metrics = data["metrics"]
        return {
            "classification": data.get("classification", "Informational document"),
            "questions": [],
            "feedback": metrics.get("feedback", "")
        }

    # Case B: fallback structure with "document_type"
    if "document_type" in data:
        return {
            "classification": data["document_type"],
            "questions": [],
            "feedback": ""
        }

    # Case C: old structure (questions + feedback)
    if "classification" in data and "questions" in data and "feedback" in data:
        return data

    # Case D: anything else → safe fallback
    return {
        "classification": data.get("classification", "Informational document"),
        "questions": data.get("questions", []),
        "feedback": data.get("feedback", "")
    }

def repair_json(text: str) -> str:
    # Remove trailing commas
    text = re.sub(r",\s*([}\]])", r"\1", text)

    # Add missing commas between string fields
    text = re.sub(r'"\s*([a-zA-Z0-9_]+)"\s*"', r'", "\1"', text)

    # Remove comments or backticks
    text = text.replace("```", "")

    return text


async def Refine_synthesis(synthesis_text,task):
    prompt = f"""
    You are refining a synthesis of documents. Your job is to extract information relating to the task "{task}". This information should include:
    -User strengths
    -User weaknesses
    -Inferred mark schemes
    DO NOT fabricate information that is not in the synthesis.
    Synthesis:
    {synthesis_text}
    """
    return await run_llm(prompt)

async def Generate_question(information):
    prompt = f"""
    Use this information to create a set of questions and answers. The questions should focus on the users weaknesses and avoid their strengths. If a sense of a mark scheme is provided use this to allocate marks to the questions.
    Information:
    {information}
    """
    return await run_big_llm(prompt,max_new_tokens=1300)
# ============================================================
#  File Hashing
# ============================================================

async def compute_hash(path: Path) -> str:
    """
    Compute SHA-256 hash of a file asynchronously.
    """
    h = hashlib.sha256()
    async with aiofiles.open(path, "rb") as f:
        while chunk := await f.read(8192):
            h.update(chunk)
    return h.hexdigest()


# ============================================================
#  Cache Handling
# ============================================================

async def load_cache(directory: Path) -> dict:
    """
    Load analysis_cache.json from the directory.
    """
    cache_path = directory / "analysis_cache.json"
    if not cache_path.exists():
        return {}
    async with aiofiles.open(cache_path, "r", encoding="utf-8") as f:
        return json.loads(await f.read())


async def save_cache(directory: Path, cache: dict):
    """
    Save updated cache back to disk.
    """
    cache_path = directory / "analysis_cache.json"
    async with aiofiles.open(cache_path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(cache, indent=2))

# ============================================================
#  Synthesis Cache Handling
# ============================================================

def load_synthesis_cache(directory: Path):
    path = directory / "synthesis_cache.json"
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def save_synthesis_cache(directory: Path, data: dict):
    path = directory / "synthesis_cache.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)



# ============================================================
#  Task & Setpoint File Handling
# ============================================================

def load_tasks() -> dict:
    with TASKS_FILE.open(encoding="utf-8") as f:
        return json.load(f)

def save_tasks(data: dict):
    with TASKS_FILE.open("w",encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def load_setpoints() -> dict:
    with SETPOINTS_FILE.open(encoding="utf-8") as f:
        return json.load(f)

def save_setpoints(data: dict):
    with SETPOINTS_FILE.open("w",encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ============================================================
#  Time Parsing
# ============================================================

def parse_dt(dt_str: str) -> datetime.datetime:
    return datetime.datetime.strptime(dt_str, "%Y-%m-%d:%H:%M")


def get_entry(data, dt_str):
    date, time = dt_str.split(":")[0], ":".join(dt_str.split(":")[1:])
    return data[date][time]


# ============================================================
#  Strength & Difficulty Logic (Preserved)
# ============================================================

def update_difficulty(data, task, effort_val, units):
    D_old = data["difficulty"][task]

    if units == "minutes":
        effort_norm = min(float(effort_val) / 10, 5)
    else:
        effort_norm = min(float(effort_val) / 5, 5)

    if effort_norm > D_old:
        D_new = 0.7 * D_old + 0.3 * effort_norm
    else:
        D_new = 0.95 * D_old + 0.05 * effort_norm

    data["difficulty"][task] = D_new
    return D_new


def compute_strength(prev_dt, current_dt, retention_factor_estimate, difficulty):
    delta = parse_dt(prev_dt) - parse_dt(current_dt)
    S_raw = 1 / (-math.log(float(retention_factor_estimate)) / delta.total_seconds())
    return S_raw / difficulty


def test_retention_factor(r_obs, r_pred, n, alpha=0.05):
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
#  Synthesis
# ============================================================
async def synthesise_results(results: list) -> str:
    prompt = f"""
You are synthesising results from multiple analysed question-and-answer documents.

Each item contains:
- metrics_json: a list of per-question metric objects
- feedback: qualitative feedback text

Your task:
Write a structured report that includes ONLY information present in the input.
Do NOT invent marks, questions, or metrics.

Sections:
1. Evaluation of the users strengths and weaknesses
2. Evaluation of what marks are awarded for

Write in clear paragraphs. Do NOT output JSON.

Data:
{json.dumps(results, indent=2)}
"""

    return await run_llm(prompt, max_new_tokens=800)

# ============================================================
#  FastAPI App
# ============================================================

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="static")


# ============================================================
#  Routes
# ============================================================
@app.on_event("startup")
async def preload_model():
    await get_llm()
@app.get("/")
@app.post("/")
async def root(request: Request):
    return templates.TemplateResponse("main.html", {"request": request})


@app.get("/get_setpoints")
async def get_setpoints():
    data = load_setpoints()
    return list(data.get("setpoints", {}).keys())


@app.get("/get_setpoint/{dt}")
async def get_setpoint(req: Request, dt: str):
    data = load_setpoints()
    setpoint = data["setpoints"][dt]

    keys = list(setpoint.keys())
    entries = [[k, v] for d in setpoint.values() for k, v in d.items()]

    return templates.TemplateResponse(
        "view_setpoints.html",
        {"request": req, "Keys": keys, "Entries": entries},
    )


# ============================================================
#  Submit Logic (Preserved)
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
    data = load_tasks()
    dt_key = f"{date}:{time}"

    data.setdefault("difficulty", {})
    data["difficulty"].setdefault(tasks, 1.0)

    data.setdefault(date, {})
    data[date][time] = {
        "effort": effort,
        "units": units,
        "task": tasks,
        "retention_factor": retention_factor,
        "n": n,
    }

    data.setdefault(tasks, [])
    data[tasks].append(dt_key)

    reps = [dt for dt in data[tasks] if get_entry(data, dt)["units"] == "repetitions"]
    mins = [dt for dt in data[tasks] if get_entry(data, dt)["units"] == "minutes"]

    D = update_difficulty(data, tasks, effort, units)

    def update_strength(history_array):
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

    save_tasks(data)
    return RedirectResponse("/", status_code=303)


# ============================================================
#  Task Display Routes
# ============================================================

@app.get("/get_date/{date}")
async def get_data(date: str):
    data = load_tasks()
    return data.get(date)


@app.get("/get_datetime/{date}/{time}")
async def get_datetime(req: Request, date: str, time: str):
    data = load_tasks()
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
    data = load_tasks()
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


# ============================================================
#  Setpoint Creation
# ============================================================

@app.post("/Create_setpoint/{task}")
async def create_setpoint(req: Request, task: str, retention_input: str = Form(...), date: str = Form(...), time: str = Form(...)):
    data = load_setpoints()
    data.setdefault("setpoints", {})
    data["setpoints"].setdefault(date, {})
    data["setpoints"][date][time] = {task: float(retention_input) / 100}

    save_setpoints(data)
    return RedirectResponse(req.headers.get("Referer"), status_code=303)


# ============================================================
#  Directory Setting
# ============================================================

@app.post("/Set_directory")
async def set_directory(req: Request, directory: str):
    globals()["Directory"] = Path(directory)
    Path("Directories.json").open("w").write(
        json.dumps({"Latest_directory": directory})
    )


# ============================================================
#  Fully Rewritten /Generate_question Route
# ============================================================

@app.get("/Generate_question/{task}")
async def generate_question(req: Request, task: str):
    """
    Analyse all files in the selected directory.
    Only re-analyse files whose hash has changed or are new.
    """
    directory = globals()["Directory"]
    files = [f for f in os.listdir(directory) if not f.endswith(".json")]

    cache = await load_cache(directory)
    updated_cache = dict(cache)
    results = []

    for filename in files:
        path = directory / filename

        # Compute hash
        file_hash = await compute_hash(path)

        # Check cache
        if filename in cache and cache[filename]["hash"] == file_hash:
            # Reuse cached result
            results.append({
                "metrics_json": cache[filename]["questions"],
                "feedback": cache[filename]["feedback"]
            })
            continue
        async with aiofiles.open(path,encoding="utf-8") as f:
            text = await f.read()
        # Analyse new/changed file
        analysis = await analyse_document(text)

        updated_cache[filename] = {
            "hash": file_hash,
            "classification": analysis["classification"],
            "questions": analysis["questions"],  # NEW: per-question metrics
            "feedback": analysis["feedback"],
        }

        results.append({
            "metrics_json": analysis["questions"],  # NEW: per-question list
            "feedback": analysis["feedback"]
        })

    # Save updated per-file cache
    await save_cache(directory, updated_cache)

    # ============================================================
    #  Synthesis Cache Check
    # ============================================================

    # Load existing synthesis cache
    synth_cache = load_synthesis_cache(directory)

    # Build current file state
    current_state = {
        "files": sorted(files),
        "hashes": {fn: updated_cache[fn]["hash"] for fn in files}
    }

    # If synthesis exists AND matches current files + hashes → reuse it
    if synth_cache:
        if (
                synth_cache.get("files") == current_state["files"] and
                synth_cache.get("hashes") == current_state["hashes"]
        ):
            print("Using cached synthesis.")
            return synth_cache["synthesis"]

    # Otherwise → generate new synthesis
    print("Generating new synthesis...")
    synthesis_text = await synthesise_results(results)

    # Save synthesis cache
    save_synthesis_cache(directory, {
        "files": current_state["files"],
        "hashes": current_state["hashes"],
        "synthesis": synthesis_text
    })

    Task_related_synthesis = await Refine_synthesis(synthesis_text,task)
    return await Generate_question(Task_related_synthesis)
