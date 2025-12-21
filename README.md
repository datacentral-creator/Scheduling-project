# 📘 Memory Strength Tracking System

A FastAPI application that models human memory using the **exponential forgetting curve** and updates a user’s memory strength parameter `S` using **statistical hypothesis testing**.

---

## 📐 Mathematical Model

### **Forgetting Curve**

The system assumes memory decays exponentially:

$$
r(t) = e^{-t/S}
$$

Where:

- \( r(t) \) = predicted retention after time \( t \)
- \( S \) = memory strength
- \( t \) = time since last exposure

---

## **Observed Retention**

When the user answers \( n \) questions and gets \( X \) correct:

$$
r_{\text{obs}} = \frac{X}{n}
$$

Because \( X \) is a count:

$$
X \sim \text{Binomial}(n, p)
$$

Retention is therefore a **noisy estimate** of the true probability \( p \).

---

## **Predicted Retention**

Given previous strength S<sub>prev</sub> and time gap \( t \):

$$
r_{\text{pred}} = e^{-t / S_{\text{prev}}}
$$

---

## 🧪 Hypothesis Test (Detecting Learning)

We test whether the user performed **better than predicted**:

$$
H_0: p \le r_{\text{pred}}
\qquad\text{vs}\qquad
H_1: p > r_{\text{pred}}
$$

### **Standard Error under H<sub>0</sub>**

$$
SE = \sqrt{\frac{r_{\text{pred}}(1 - r_{\text{pred}})}{n}}
$$

### **z‑score**

$$
z = \frac{r_{\text{obs}} - r_{\text{pred}}}{SE}
$$

### **One‑sided p‑value**

$$
p = 1 - \Phi(z)
$$

If \( p < 0.05 \), the system concludes the user’s retention is **significantly higher** than predicted.

---

## 📏 Confidence Interval for Observed Retention

$$
SE_{\text{obs}} = \sqrt{\frac{r_{\text{obs}}(1 - r_{\text{obs}})}{n}}
$$

$$
CI = \left[
r_{\text{obs}} - 1.96\, SE_{\text{obs}},\;
r_{\text{obs}} + 1.96\, SE_{\text{obs}}
\right]
$$

This quantifies uncertainty in the measurement.

---

## 🎯 Minimum Retention Needed to Pass

The smallest retention value that *would* have passed the hypothesis test is:

$$
r_{\min} = r_{\text{pred}} + 1.645 \cdot SE
$$

If the user fails the test, this value is stored as `Retention_min`.

---

## 🔧 Updating Memory Strength \(S\)

If the hypothesis test **accepts**:

$$
S_{\text{new}} = \frac{-t}{\ln(r_{\text{obs}})}
$$

If the test **rejects**, the previous strength is kept.

---

## 🗂 Data Storage

Each entry stores:

- effort  
- units (`minutes` or `repetitions`)  
- task name  
- retention factor  
- number of questions \( n \)  
- updated strength \( S \)  
- optional `Retention_min`  

Tasks also maintain a chronological list of timestamps.

---

## 🔄 Request Flow

1. User submits a new retention measurement.  
2. System loads previous data from `data.json`.  
3. Identifies the last attempt for the same task.  
4. Computes time difference \( t \).  
5. Computes predicted retention r<sub>pred</sub>
6. Runs hypothesis test.  
7. If accepted → update \( S \).  
8. If rejected → keep old \( S \) and store r<sub>min</sub>
9. Saves everything back to JSON.

---

## 🖥 Endpoints Overview

- `/` — main UI  
- `/submit` — submit new retention data  
- `/get_date/{date}` — view all entries for a date  
- `/get_datetime/{date}/{time}` — view a specific entry  
- `/get_task/{task}` — view current strength for a task  
- `/get_setpoints` — list setpoints  
- `/get_setpoint/{datetime}` — view setpoint details  
- `/Create_setpoint/{task}` — create a new setpoint

---

## 📊 Usefulness as a Revision Assistant

This system provides a mathematically principled way to track how well a learner retains information over time.  
By combining the exponential forgetting curve with statistical hypothesis testing, it offers several advantages over traditional revision tools:

### **1. Personalised Memory Strength**
Each task receives its own memory‑strength parameter \( S \), which adapts based on the learner’s performance.  
A larger \( S \) means slower forgetting, while a smaller \( S \) indicates faster decay.

This allows the system to tailor revision schedules to the individual rather than using fixed intervals.

### **2. Noise‑Aware Retention Measurement**
Because retention is estimated from \( X/n \) correct answers, the system models:

$$
X \sim \text{Binomial}(n, p)
$$

This means the system understands that small quizzes (small \( n \)) produce noisy estimates, while larger quizzes give more reliable information.  
The hypothesis test ensures that **S only updates when the evidence is strong**, preventing overreaction to random fluctuations.

### **3. Transparent Feedback**
When a retention measurement is too low to justify updating \( S \), the system computes the minimum value needed to pass:

$$
r_{\min} = r_{\text{pred}} + 1.645 \cdot SE
$$

This gives the learner clear, actionable insight into how much improvement is required.

### **4. Adaptive and Self‑Correcting**
Because the system compares predicted retention to observed retention, it naturally detects:

- learning progress  
- overestimation of memory  
- underestimation of memory  

This makes it a powerful engine for spaced repetition, revision planning, and long‑term knowledge tracking.

---

## 🏋️ Future Potential: Modelling Muscle Strength and Atrophy

The same mathematical framework can be extended beyond cognitive memory to **physical strength**.

Research in sports science shows that muscle atrophy and strength decay can also be approximated by exponential models:

$$
F(t) = F_0 \, e^{-t / K}
$$

Where:

- \( F(t) \) = strength after time \( t \) without training  
- \( F_0 \) = baseline strength  
- \( K \) = atrophy constant (analogous to memory strength \( S \))

This mirrors the forgetting curve:

$$
r(t) = e^{-t/S}
$$

### **Why this works**
Both memory and muscle strength:

- improve with training  
- decay over time without reinforcement  
- follow diminishing‑returns learning curves  
- can be modelled with exponential dynamics  

### **What your system could do in the future**
By reusing the same architecture, the system could:

- track gym performance or physical therapy progress  
- estimate a user’s atrophy constant \( K \)  
- predict when strength will fall below a target threshold  
- schedule optimal training intervals  
- detect statistically significant improvements in physical performance  

### **Unified Cognitive + Physical Model**
Because both domains use the same mathematical structure, your system could evolve into a **generalised human‑performance tracker**, capable of modelling:

- memory retention  
- skill acquisition  
- physical strength  
- endurance  
- reaction time  

All using the same exponential‑decay + hypothesis‑testing framework.

I also plan to integrate this into my main project <a href="https://github.com/datacentral-creator/Datacentral">datacentral</a> as an addon.

---
