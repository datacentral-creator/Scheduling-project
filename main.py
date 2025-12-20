import datetime
import json
import math

from fastapi import FastAPI, Form
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.templating import Jinja2Templates

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="static")

def Open_data(file):
    return json.load(open(file))

def Save_data(file, data):
    open(file, "w").write(json.dumps(data,indent=1))

@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse("main.html",{"request":request})

@app.post("/")
async def root(request: Request):
    return templates.TemplateResponse("main.html",{"request":request})

@app.get("/get_setpoints")
async def get_setpoints():
    data = Open_data("data.json")
    return list(data["setpoints"].keys())

@app.get("/get_setpoint/{datetime}")
async def get_setpoint(req:Request,datetime:str):
    data = Open_data("data.json")
    Setpoint = data["setpoints"][datetime]
    Keys = list(Setpoint.keys())
    Entries= [[list(el.keys())[0],list(el.values())[0]] for el in list(Setpoint.values())]
    return templates.TemplateResponse("view_setpoints.html",{"request":req,"Keys":Keys,"Entries":Entries})
@app.post("/submit")
async def submit_form(
    effort: str = Form(...),
    units: str = Form(...),
    date: str = Form(...),
    time: str = Form(...),
    tasks: str = Form(...),
    retention_factor:str=Form(...),
    n:str=Form(...)
):
    data = Open_data("data.json")
    if date in data:
        data[date][time] = {"effort":effort, "units":units,"task":tasks,"retention_factor":retention_factor,"n":n}
    else:
        data[date] = {time:{"effort":effort, "units":units,"task":tasks,"retention_factor":retention_factor,"n":n}}
    if tasks in data:
        data[tasks].append(date+":"+time)
        reps = [el for el in data[tasks] if data[el.split(":")[0]][el.split(":")[1]+":"+el.split(":")[2]]["units"] == "reps"]
        times = [el for el in data[tasks] if data[el.split(":")[0]][el.split(":")[1]+":"+el.split(":")[2]]["units"] == "minutes"]
        print(times,len(times) > 1,times[0],date+":"+time,datetime.datetime.strptime(times[0], "%Y-%m-%d:%H:%M") -
                                                 datetime.datetime.strptime(date + ":" + time,
                                                                       "%Y-%m-%d:%H:%M"))
        if units == "minutes" and (len(times) > 1):
            Last_times_entry = data[times[-1].split(":")[0]][times[-1].split(":")[1] + ":" + times[-1].split(":")[2]]
            Current_datetime = datetime.datetime.strptime(date + ":" + time,
                                                          "%Y-%m-%d:%H:%M")
            if "strength" in Last_times_entry:
                Strength_prev = Last_times_entry["strength"]
                Time_difference = (Current_datetime-datetime.datetime.strptime(times[-1],"%Y-%m-%d:%H:%M")).total_seconds()
                r_pred = math.exp(-(Time_difference)/Strength_prev)
                accept,ci,p_value = test_retention_factor(float(retention_factor),r_pred,n)
                if accept:
                    data[date][time]["strength"] = 1 / (-math.log(float(effort), math.e) /
                                                    (datetime.datetime.strptime(times[0], "%Y-%m-%d:%H:%M") - Current_datetime
                                                     ).total_seconds())
                else:
                    data[date][time]["strength"] = Strength_prev
            else:
                data[date][time]["strength"] = 1 / (-math.log(float(effort), math.e) /
                                                    (datetime.datetime.strptime(times[0],
                                                                                "%Y-%m-%d:%H:%M") - Current_datetime
                                                     ).total_seconds())
        if units == "repetitions" and (len(reps) > 1):
            Last_reps_entry = data[reps[-1].split(":")[0]][reps[-1].split(":")[1] + ":" + reps[-1].split(":")[2]]
            Current_datetime = datetime.datetime.strptime(date + ":" + time,"%Y-%m-%d:%H:%M")
            if "strength" in Last_reps_entry:
                Strength_prev = Last_reps_entry["strength"]
                Time_difference = (Current_datetime-datetime.datetime.strptime(reps[-1], "%Y-%m-%d:%H:%M")).total_seconds()
                r_pred = math.exp(-(Time_difference) / Strength_prev)
                accept, ci, p_value,r_min = test_retention_factor(float(retention_factor), r_pred, n)
                if accept:
                    data[date][time]["strength"] = 1 / (-math.log(float(effort), math.e) /
                                                        (datetime.datetime.strptime(reps[0], "%Y-%m-%d:%H:%M") -
                                                         datetime.datetime.strptime(date + ":" + time,
                                                                                    "%Y-%m-%d:%H:%M")).total_seconds())
                else:
                    data[date][time]["strength"] = Strength_prev
                    data[date][time]["Retention_min"] = r_min
            else:
                data[date][time]["strength"] = 1 / (-math.log(float(effort), math.e) /
                                                    (datetime.datetime.strptime(reps[0], "%Y-%m-%d:%H:%M") -
                                                     datetime.datetime.strptime(date + ":" + time,
                                                                                "%Y-%m-%d:%H:%M")).total_seconds())
    else:
        data[tasks] = [date+":"+time]
    Save_data(file="data.json", data=data)
    return RedirectResponse("/")

def test_retention_factor(r_obs, r_pred, n, alpha=0.05):
    """
    r_obs  = observed retention (X/n)
    r_pred = predicted retention from old S
    n      = number of questions
    """

    # --- 1. Hypothesis test: is r_obs > r_pred? ---
    # Standard error under H0
    se = math.sqrt(r_pred * (1 - r_pred) / n)

    # Avoid division by zero
    if se == 0:
        return False, (r_obs, r_obs), 0

    z = (r_obs - r_pred) / se

    # One-sided p-value
    # p-value = 1 - Φ(z)
    p_value = 1 - 0.5 * (1 + math.erf(z / math.sqrt(2)))

    # --- 2. Confidence interval for r_obs ---
    zcrit = 1.96
    se_obs = math.sqrt(r_obs * (1 - r_obs) / n)
    margin = zcrit * se_obs
    ci = (r_obs - margin, r_obs + margin)

    # Accept if p-value < alpha
    accept = p_value < alpha

    # --- 6. Compute minimum r that WOULD be accepted ---
    # Critical z-value for one-sided test
    z_alpha = 1.645  # Φ^{-1}(0.95)

    r_min = r_pred + z_alpha * se

    # Clip to valid probability range
    r_min = max(0.0, min(1.0, r_min))

    return accept, ci, p_value,r_min


@app.get("/get_date/{date}")
async def get_data(date: str):
    data = Open_data("data.json")
    if date in data:
        return data[date]
    else:
        return None

@app.get("/get_datetime/{date}/{time}")
async def get_datetime(req:Request,date: str, time: str):
    data = Open_data("data.json")
    chunk = data[date][time]
    if "Retention_min" in chunk:
        return templates.TemplateResponse("view_entry.html",
                                          {"request": req, "date": date, "time": time, "effort": chunk["effort"],
                                           "units": chunk["units"], "task": chunk["task"], "retention_factor": float
                                          (chunk["retention_factor"]),"Retention_min":float(chunk["Retention_min"])})
    return templates.TemplateResponse("view_entry.html",{"request":req,"date":date,"time":time,"effort":chunk["effort"],"units":chunk["units"],"task":chunk["task"],"retention_factor":float
    (chunk["retention_factor"]),"Retention_min":None})

@app.get("/get_task/{task}")
async def get_task(req:Request,task: str,scale="hours",period="50"):
    data = Open_data("data.json")
    if task in data:
        strength = data[task][-1]
        strength = data[strength.split(":")[0]][strength.split(":")[1]+":"+strength.split(":")[2]]
        if "strength" in strength:
            strength = strength["strength"]
        else:
            strength = None
        return templates.TemplateResponse("view_task.html",{"request":req,"task":task,"Strength":strength,"scale":scale,"period":int(period)})

@app.get("/get_task/{task}/{scale}/{period}")
async def get_task_with_scale(req:Request,task: str, scale: str,period:str):
    return await get_task(req,task,scale,period)

@app.post("/get_task/{task}")
async def post_task(req:Request,task: str):
    return await get_task(req,task)
@app.post("/get_task/{task}/{scale}/{period}")
async def get_task_with_scale(req:Request,task: str, scale: str,period:str):
    return await get_task(req,task,scale,period)

@app.post("/Create_setpoint/{task}")
async def Create_setpoint(req:Request,task:str,retention_input:str=Form(...),date:str=Form(...),time:str=Form(...)):
    data = Open_data("data.json")
    if "setpoints" in data:
        if date in data["setpoints"]:
            data["setpoints"][date][time] = {task: float(retention_input)/100}
        else:
            data["setpoints"][date] = {time:{task:float(retention_input)/100}}
    else:
        data["setpoints"] = {date:{time:{task:float(retention_input)/100}}}

    Save_data(file="data.json", data=data)
    return RedirectResponse(req.headers.get("Referer"))

