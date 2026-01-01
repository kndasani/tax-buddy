# 🇮🇳 TaxGuide AI: The Conversational Tax Expert

**TaxGuide AI** is a Streamlit-based intelligent chatbot designed to help Indian taxpayers navigate the complexities of FY 2025-26 tax regimes. Unlike traditional tax calculators that look like spreadsheets, TaxGuide AI functions as an empathetic, conversational consultant.

It uses **Google Gemini 2.0 Flash** to conduct natural interviews, explain rules in plain English, and perform complex regime comparisons (New vs. Old) without overwhelming the user with jargon.


## 🎯 Target Personas

We built this application to solve specific pain points for three distinct types of users:

### 1. The Salaried Employee (The "Form 16" User)

* **The Pain Point:** Struggles with HR investment declaration portals. Doesn't know which section covers "Life Insurance" vs. "Medical Insurance." Confused by New vs. Old Regime.
* **How we help:**
* **Jargon-Free Interview:** We ask "Do you pay rent?" instead of "Enter Section 10(13A) amount."
* **HR Portal Mapping:** The final output provides a clear table mapping their inputs to specific Tax Sections (80C, 80D, HRA) for easy data entry.

### 2. The Freelancer / Gig Worker (The "44ADA" User)

* **The Pain Point:** Often overpays tax because they don't understand "Presumptive Taxation" (Section 44ADA) which allows declaring only 50% of income.
* **How we help:**
* **Context Detection:** The AI detects keywords like "Freelancer" or "Consultant" and automatically loads the specific *Freelancer Tax Rules* PDF into its context window.
* **Optimized Math:** The calculator engine automatically applies the 50% presumptive income rule for this persona.

### 3. The Tax Novice (The "Jargon-Averse" User)

* **The Pain Point:** Intimidated by terms like "Cess," "Surcharge," and "Rebate u/s 87A."
* **How we help:**
* **Educational Mode:** Users can choose to "Ask Tax Rules" instead of calculating tax.
* **Transparent Breakdown:** The final receipt breaks down the math into Base Tax, Surcharge, and Cess, with an option to expand and read *why* those numbers exist.

## 🚀 Key Features

### 🧠 1. Hybrid "Fork" Architecture

The app offers two distinct paths at launch:

* **💰 Calculate My Tax:** A structured, step-by-step interview to derive the final tax liability.
* **📚 Ask Tax Rules:** An open-ended RAG (Retrieval Augmented Generation) interface to query specific tax laws.

### ⚡ 2. Just-in-Time Knowledge Injection

To optimize for performance and token costs, the app does **not** load tax rules at startup.

* It starts with an empty context.
* As the user speaks, the AI detects their persona (e.g., "I have a job" vs "I trade stocks").
* The system **dynamically injects** only the relevant PDF (Salary Rules vs. Business Rules) into the chat history in real-time.

### 🛡️ 3. Robust "Crash-Proof" Design

* **Retry Logic:** Includes a custom wrapper that handles `429 Resource Exhausted` errors from the API by implementing exponential backoff (waiting and retrying automatically).
* **Input Sanitization:** The Python engine safely extracts numbers from the chat, ignoring currency symbols or commas.

### 📊 4. Professional-Grade Calculator

The underlying Python engine isn't just an LLM guess. It is a deterministic calculator that handles:

* **New vs. Old Regime Comparison** (Side-by-side).
* **Surcharge Slabs:** (10%, 15%, 25%, 37%) with regime-specific capping.
* **Cess:** 4% Health & Education Cess.
* **Rebates:** Section 87A rebates for income up to ₹7L (New) and ₹5L (Old).

## 🛠️ Tech Stack

* **Frontend:** [Streamlit](https://streamlit.io/) (Python)
* **LLM Engine:** Google Gemini 2.0 Flash (via `google-generativeai`)
* **Environment Management:** `python-dotenv`
* **Data Source:** Custom PDF Knowledge Base (Salary Rules, Freelancer Rules, Capital Gains).

## ⚙️ Installation & Run

1. **Clone the repository:**
```bash
git clone https://github.com/your-username/tax-guide-ai.git
cd tax-guide-ai

```
2. **Install dependencies:**
```bash
pip install -r requirements.txt

```
3. **Set up API Keys:**
Create a `.env` file in the root directory:
```env
GEMINI_API_KEY=your_google_api_key_here

```
4. **Run the App:**
```bash
streamlit run app.py

```

## ⚠️ Disclaimer

*This application is a prototype for educational and assistive purposes. While the calculation logic is based on FY 2025-26 rules, users should verify all figures with a Chartered Accountant (CA) before filing official returns.*