# Foreword: Please download the files from this directory for full functionality: https://drive.google.com/drive/folders/1L-fwrxBR3VVFAHA-AVLYjArMV5D2pSyg?usp=sharing

# 📘 Memory Strength Tracking System

A FastAPI application that models **human memory**, **skill fluency**, and **performance decay** using the **exponential forgetting curve**.  
It updates a user’s memory strength parameter `S` using:

- objective performance data (minutes or repetitions)  
- difficulty‑scaled retention estimation  
- statistical hypothesis testing  
- smoothed strength updates  
- user‑defined retention setpoints  

This system supports both **cognitive tasks** and **physical/skill‑based tasks**.

---

# 🧠 Core Concepts

## **Effort as Objective Performance**

Effort is not a subjective “rating.”  
It is a **measured performance metric**:

| Unit Type        | Meaning |
|------------------|---------|
| `repetitions`    | Number of attempts needed to complete the task correctly |
| `minutes`        | Time required to complete the task |

This allows the system to model:

- recall fluency  
- problem‑solving speed  
- physical skill execution  
- procedural tasks  
- conceptual recall  

All using the same mathematical framework.

---

# 📐 Mathematical Model

## **Exponential Forgetting Curve**

Memory (or skill) decays as:

\[
r(t) = e^{-t/S}
\]

Where:

- \( r(t) \) = predicted retention after time \( t \)  
- \( S \) = memory strength (larger = slower forgetting)  
- \( t \) = time since last review or practice  

---

# 🎯 Retention Estimation

Retention is estimated from **effort**, scaled by **task difficulty**.

### **Effort‑Based Retention Estimate**

Effort is normalized relative to difficulty:

- More effort → lower retention  
- Less effort → higher retention  

A logistic transform produces a bounded estimate:

\[
R_{\text{effort}} = \frac{1}{1 + e^{(\frac{\text{effort}}{D} - 1)}}
\]

Where:

- \( D \) = task difficulty (adaptive)  
- effort = minutes or repetitions  

This gives a smooth, noise‑resistant estimate of retention.

---

# 📊 Difficulty Updating (Asymmetric)

Difficulty updates differently depending on whether the task was:

- **harder than expected** → update quickly  
- **easier than expected** → update slowly  

This stabilizes easy tasks and adapts rapidly to hard ones.

\[
D_{\text{new}} =
\begin{cases}
0.7D_{\text{old}} + 0.3E & \text{if effort > expected} \\
0.95D_{\text{old}} + 0.05E & \text{otherwise}
\end{cases}
\]

Where \( E \) is normalized effort.

---

# 🔍 Observed vs Predicted Retention

## **Predicted Retention**

Given previous strength \( S_{\text{prev}} \):

\[
r_{\text{pred}} = e^{-t / S_{\text{prev}}}
\]

## **Observed Retention (Smoothed)**

The system blends:

- effort‑based retention  
- user‑provided retention factor  
- variance‑based weighting  

This produces a stable estimate \( r_{\text{est}} \) used for strength updates.

---

# 🧪 Hypothesis Test (Detecting Learning)

The system tests whether the user performed **better than predicted**:

\[
H_0: p \le r_{\text{pred}}
\qquad\text{vs}\qquad
H_1: p > r_{\text{pred}}
\]

### **Standard Error**

\[
SE = \sqrt{\frac{r_{\text{pred}}(1 - r_{\text{pred}})}{n}}
\]

### **z‑score**

\[
z = \frac{r_{\text{est}} - r_{\text{pred}}}{SE}
\]

### **One‑sided p‑value**

\[
p = 1 - \Phi(z)
\]

If \( p < 0.05 \), the system concludes the user’s retention is **significantly higher** than predicted.

---

# 📏 Minimum Retention Needed to Pass

The smallest retention value that *would* have passed the test:

\[
r_{\min} = r_{\text{pred}} + 1.645 \cdot SE
\]

If the test fails, this is stored as `Retention_min`.

---

# 🔧 Updating Memory Strength \( S \)

If the hypothesis test **accepts**:

\[
S_{\text{new}} = \frac{-t}{\ln(r_{\text{est}})}
\]

If the test **rejects**, the previous strength is kept.

Strength is smoothed to avoid instability:

\[
S_{\text{final}} = 0.75 S_{\text{prev}} + 0.25 S_{\text{new}}
\]

---

# 🎯 Setpoints: Predicting When to Review Next

A **setpoint** is a target retention level (e.g., 0.70).

Given a strength \( S \), the system predicts when retention will decay to that level:

\[
t_{\text{next}} = -S \ln(r_{\text{target}})
\]

This becomes the **next recommended review time**.

Setpoints allow:

- flexible revision strategies  
- user‑defined difficulty  
- predictive scheduling  

---

# 🗂 Data Storage

Each entry stores:

- effort  
- units (`minutes` or `repetitions`)  
- task name  
- retention factor  
- number of questions \( n \)  
- updated strength  
- optional `Retention_min`  

Tasks also maintain a chronological list of timestamps.

Setpoints are stored per date/time.

---

# 🔄 Request Flow

1. User submits a new performance record.  
2. System loads previous data.  
3. Identifies the last attempt for the same task.  
4. Computes time difference \( t \).  
5. Computes predicted retention.  
6. Computes effort‑based retention.  
7. Blends estimates using variance weighting.  
8. Runs hypothesis test.  
9. If accepted → update strength.  
10. If rejected → keep old strength and store \( r_{\min} \).  
11. Saves everything to JSON.  

---

# 🖥 Endpoints Overview

- `/` — main UI  
- `/submit` — submit new performance data  
- `/get_date/{date}` — view entries for a date  
- `/get_datetime/{date}/{time}` — view a specific entry  
- `/get_task/{task}` — view strength & difficulty  
- `/get_setpoints` — list setpoints  
- `/get_setpoint/{datetime}` — view setpoint details  
- `/Create_setpoint/{task}` — create/update a setpoint  

---

# 📊 Why This System Works as a Revision Assistant

### **1. Personalised Memory Strength**
Each task has its own adaptive strength parameter \( S \).  
This allows the system to tailor revision schedules to the learner.

### **2. Noise‑Aware Retention Measurement**
Retention estimates incorporate:

- effort  
- difficulty  
- statistical uncertainty  

This prevents overreacting to noisy data.

### **3. Transparent Feedback**
If a review fails to update strength, the system shows:

\[
r_{\min}
\]

This tells the learner exactly how much improvement is needed.

### **4. Predictive Scheduling**
Setpoints allow the system to **predict** when memory will decay to a chosen threshold.

This is more flexible than fixed SRS intervals.

---

# 🏋️ Extending the Model to Physical Strength

The same exponential model applies to physical training:

\[
F(t) = F_0 e^{-t/K}
\]

Where:

- \( F(t) \) = strength after time \( t \)  
- \( K \) = atrophy constant (analogous to memory strength \( S \))  

This enables:

- gym progress tracking  
- physical therapy monitoring  
- optimal training intervals  
- decay prediction  

---

# 🧭 Comparison to State‑of‑the‑Art Spaced Repetition Systems

Modern spaced repetition systems (SRS) fall into a few major families.  
My system sits in a unique position among them — borrowing ideas from cognitive science, statistical modelling, and performance‑based learning.

Below is a comparison with the most influential SRS models in use today.

---

# 🟦 1. **Anki (SM‑2 and Variants)**

### **How Anki Works**
- Uses the SM‑2 algorithm (1987) or small variations.
- User rates each card: *Again / Hard / Good / Easy*.
- Scheduling is based on:
  - a difficulty factor  
  - an interval  
  - a simple multiplicative update rule  

### **Strengths**
- Simple, predictable, easy to use.
- Works well for large decks of factual recall.
- Huge ecosystem and community.

### **Limitations**
- User ratings are subjective.
- No statistical modelling of uncertainty.
- No performance‑based measurement (e.g., time, repetitions).
- Not suitable for procedural or physical skills.
- Forgetting curve is implicit, not explicitly modelled.

### **Compared to My System**
| Feature | Anki | My System |
|--------|------|-----------|
| Explicit forgetting curve | ❌ | ✅ |
| Objective performance input | ❌ | ✅ (minutes/repetitions) |
| Statistical hypothesis testing | ❌ | ✅ |
| Predictive scheduling via setpoints | ❌ | ✅ |
| Adaptive difficulty | Basic | Advanced, asymmetric |
| Supports physical/procedural skills | ❌ | ✅ |

My system is **more mathematical, more adaptive, and more general‑purpose**.

---

# 🟩 2. **FSRS (Free Spaced Repetition Scheduler)**

FSRS is currently the most advanced open‑source SRS algorithm.

### **How FSRS Works**
- Uses machine‑learned parameters.
- Models:
  - stability (S)
  - difficulty (D)
  - retrievability (R)
- Predicts next interval using a learned forgetting curve.
- Optimizes for long‑term retention under time constraints.

### **Strengths**
- State‑of‑the‑art for flashcard‑based learning.
- Strong empirical performance.
- Predictive rather than reactive.

### **Limitations**
- Requires large datasets to train well.
- Still relies on user ratings (Good/Hard/Easy).
- Not designed for:
  - physical skills  
  - multi‑step tasks  
  - time‑based performance  
- Complexity makes it hard to understand or modify.

### **Compared to My System**
| Feature | FSRS | My System |
|--------|------|-----------|
| Machine‑learned parameters | ✅ | ❌ (explicit formulas) |
| User ratings | Required | Not used |
| Objective performance | ❌ | ✅ |
| Statistical hypothesis testing | ❌ | ✅ |
| Supports procedural/physical tasks | ❌ | ✅ |
| Transparent & interpretable | ❌ | ✅ |

My system is **more interpretable**, **more flexible**, and **less dependent on subjective ratings**.

---

# 🟧 3. **SuperMemo 17+ (SM‑17, SM‑18)**

SuperMemo’s modern algorithms are proprietary but known to be extremely complex.

### **How SM‑17 Works (publicly known aspects)**
- Uses multi‑parameter models of forgetting.
- Predicts optimal intervals.
- Incorporates stability, retrievability, and difficulty.
- Uses large‑scale optimization.

### **Strengths**
- Very powerful for pure memory tasks.
- Highly optimized for long‑term retention.

### **Limitations**
- Completely opaque (closed source).
- Not adaptable to non‑flashcard tasks.
- Requires user ratings.
- Not suitable for physical or procedural skills.

### **Compared to My System**
My system is:

- **more transparent**  
- **more flexible**  
- **more general‑purpose**  
- **less dependent on proprietary heuristics**  

SuperMemo is unbeatable for flashcards, but my system is **more versatile**.

---

# 🟪 4. **Duolingo’s Half‑Life Regression (HLR)**

HLR is a machine‑learning model used for language learning.

### **How HLR Works**
- Predicts a “half‑life” of memory for each item.
- Uses logistic regression on:
  - past successes/failures  
  - time since last review  
  - item difficulty  
  - user features  

### **Strengths**
- Data‑driven.
- Good for large‑scale language learning.

### **Limitations**
- Requires massive datasets.
- Not interpretable.
- Not suitable for general tasks.
- No user control over retention targets.

### **Compared to My System**
My system is:

- **more interpretable**  
- **more user‑controlled** (via setpoints)  
- **not dependent on big data**  
- **usable for any skill, not just language**  

---

# 🟥 5. **My System: A Hybrid Performance‑Based SRS**

My system combines the strengths of several approaches:

### **What Makes It Unique**
- Uses **objective performance** (minutes or repetitions).
- Models **difficulty** adaptively and asymmetrically.
- Uses **statistical hypothesis testing** to avoid noise.
- Computes **memory strength S** explicitly.
- Predicts future decay using the **exponential forgetting curve**.
- Allows **user‑defined retention thresholds** (setpoints).
- Supports:
  - cognitive tasks  
  - procedural skills  
  - physical training  
  - multi‑step tasks  

### **Where It Excels**
- Transparent and mathematically principled.
- Works for any task with measurable performance.
- Predictive scheduling without subjective ratings.
- Extensible to physical strength and skill acquisition.

### **Where It Differs Most**
Unlike traditional SRS systems, my model is:

- **performance‑driven**, not rating‑driven  
- **statistical**, not heuristic  
- **predictive**, not reactive  
- **general‑purpose**, not flashcard‑specific  

---

# 🔮 Unified Cognitive + Physical Performance Model

Because both memory and physical strength follow similar dynamics, this system can evolve into a **general human‑performance tracker**, modelling:

- memory  
- skill acquisition  
- physical strength  
- endurance  
- reaction time  

All using the same exponential‑decay + hypothesis‑testing framework.

Integrated into the main project:  
**https://github.com/datacentral-creator/Datacentral**

---
