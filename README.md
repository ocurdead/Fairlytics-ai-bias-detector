# 🚀 Fairlytics — AI Bias Detection & Fairness Audit Tool

🔗 Live App: https://fairlytics-ai-bias-detector.netlify.app/  
⚙️ API Backend: https://fairlytics.onrender.com  

---

## 🧠 Overview

Fairlytics is an AI-powered fairness auditing system that detects bias in datasets and machine learning models.

It analyzes outcomes across demographic groups and highlights disparities using industry-standard fairness metrics — all translated into simple, human-readable explanations.

---

## ⚡ Key Features

- 📊 Upload CSV datasets for bias analysis  
- 🤖 Upload ML models for fairness validation  
- 📉 Detect bias using:
  - Disparate Impact
  - Statistical Parity Difference
  - Equalized Odds (if model available)
- 🔍 Automatic sensitive attribute detection  
- 🧾 Plain-English explanations (non-technical users)  
- 📈 Bias attribution (data vs model)  
- 🧪 Counterfactual fairness checks  
- 📦 Downloadable audit reports  

---

## 🏗️ Architecture


Frontend (Netlify)
↓
FastAPI Backend (Render)
↓
Orchestrator
↓
Agents:
• Data Bias Agent
• Model Bias Agent
• Counterfactual Agent
↓
Explanation Engine (Rule-based + Groq LLM)


---

## 🧰 Tech Stack

**Frontend**
- HTML, CSS, Vanilla JS
- Netlify (Hosting)

**Backend**
- Python, FastAPI
- Pandas, NumPy
- Render (Deployment)

**AI / LLM**
- Groq API (LLaMA 3.1)

---

## 📂 Project Structure


fairlytics/
│
├── frontend/
│ ├── index.html
│ ├── result.html
│ ├── main.js
│ └── styles.css
│
├── core/
│ ├── orchestrator.py
│ ├── explanation_agent.py
│ └── agents/
│ ├── data_bias_agent.py
│ ├── model_bias_agent.py
│ └── counterfactual_agent.py
│
├── services/
│ └── input_processor.py
│
├── config.py
├── main.py
└── requirements.txt


---

## 🔍 How It Works

1. Upload dataset  
2. Select:
   - Protected attribute (e.g. gender)
   - Label column (e.g. treatment_given)
3. System:
   - Computes group outcome rates
   - Measures fairness gaps
   - Identifies most affected group
4. Generates:
   - Risk score
   - Bias explanation
   - Actionable recommendations  

---

## 📊 Example Insight

> Female patients received treatment significantly less often than male patients (20% vs 100%), indicating a high fairness risk and potential unequal access to care.

---

## 🚀 Running Locally

```bash
git clone https://github.com/your-username/fairlytics.git
cd fairlytics

pip install -r requirements.txt
uvicorn main:app --reload --port 8001

Frontend:

cd frontend
python -m http.server 5500
🔐 Environment Variables

Create .env file:

GROQ_API_KEY=your_api_key
GROQ_MODEL=llama-3.1-8b-instant

⚠️ Limitations
Small datasets may skip model fairness checks
Requires labeled data
Binary outcomes work best
🏁 Future Improvements
Dashboard analytics
Multi-attribute fairness
Real-time model monitoring
Explainable AI visualizations