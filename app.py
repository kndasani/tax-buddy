import streamlit as st
import google.generativeai as genai
import os
import time
import math
import re
from dotenv import load_dotenv

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="TaxGuide AI", page_icon="🇮🇳", layout="centered", initial_sidebar_state="collapsed")
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    try: api_key = st.secrets["GEMINI_API_KEY"]
    except: st.error("🔑 API Key Missing."); st.stop()

genai.configure(api_key=api_key)

# --- 2. HELPER: RETRY LOGIC ---
def send_message_with_retry(chat_session, prompt, retries=3):
    for i in range(retries):
        try:
            return chat_session.send_message(prompt)
        except Exception as e:
            if "429" in str(e):
                time.sleep(2 ** (i + 1))
                continue
            else:
                raise e
    raise Exception("⚠️ Server busy. Please wait 1 minute.")

# --- 3. KNOWLEDGE LOADER ---
@st.cache_resource
def get_pdf_file(filename):
    if os.path.exists(filename):
        try:
            f = genai.upload_file(path=filename, display_name=filename)
            while f.state.name == "PROCESSING": time.sleep(1); f = genai.get_file(f.name)
            return f
        except: return None
    return None

def inject_knowledge(persona_type):
    if persona_type == "SALARY": return get_pdf_file("salary_rules.pdf")
    elif persona_type == "BUSINESS": return get_pdf_file("freelancer_rules.pdf")
    elif persona_type == "CAPITAL_GAINS": return get_pdf_file("capital_gains.pdf")
    return None

# --- 4. CALCULATOR ENGINES (Unified) ---

def safe_math_eval(expression):
    """Robust Math Tool for Spot Checks"""
    try:
        # Strip labels like "Salary:" or "x="
        if ":" in expression: expression = expression.split(":")[-1]
        if "=" in expression: expression = expression.split("=")[-1]
        
        # Normalize
        expression = expression.lower().strip()
        expression = expression.replace("\n", " ").replace("\t", " ") 
        expression = expression.replace("`", "").replace("₹", "")       
        expression = expression.replace("%", "*0.01").replace("^", "**")     
        
        # Balance Parentheses
        open_c = expression.count('(')
        close_c = expression.count(')')
        if open_c > close_c: expression += ')' * (open_c - close_c)
        elif close_c > open_c: expression = expression.rstrip(')')
        
        # Handle commas inside numbers vs args
        expression = re.sub(r'(\d),(\d)', r'\1\2', expression)
        
        # Security Whitelist
        allowed = set("0123456789+-*/()., <>=abcdefhilmnorstuwx")
        if not set(expression).issubset(allowed): return "Error: Unsafe characters"

        safe_dict = {"min": min, "max": max, "abs": abs, "round": round, "int": int, "float": float, "pow": pow, "ceil": math.ceil, "floor": math.floor}
        result = eval(expression, {"__builtins__": None}, safe_dict)
        
        if isinstance(result, (int, float)): return f"{int(result):,}"
        return str(result)
    except Exception as e: return f"Error ({e})"

def calculate_tax_detailed(age, salary, business_income, rent_paid, inv_80c, med_80d, custom_basic=0):
    """Full Tax Regime Calculator"""
    std_deduction_new = 75000; std_deduction_old = 50000
    
    # Smart Basic Logic: If not provided, assume 50% of Salary
    basic = custom_basic if custom_basic > 0 else (salary * 0.50)
    
    taxable_business = business_income * 0.50
    # HRA Rule: min(Actual HRA, Rent-10%Basic, 50%Basic) - Simplified here to max benefit
    hra_exemption = max(0, rent_paid * 12 - (0.10 * basic))
    
    gross = salary + taxable_business
    deductions_old = std_deduction_old + hra_exemption + min(inv_80c, 150000) + med_80d
    net_old = max(0, gross - deductions_old)
    net_new = max(0, gross - std_deduction_new)

    bd_new = compute_tax_breakdown(net_new, age, "new")
    bd_old = compute_tax_breakdown(net_old, age, "old")
    
    return {
        "new": {"breakdown": bd_new, "net": net_new},
        "old": {"breakdown": bd_old, "net": net_old, "deductions": {"std": std_deduction_old, "hra": hra_exemption, "80c": min(inv_80c, 150000), "80d": med_80d}}
    }

def compute_tax_breakdown(income, age, regime):
    tax = 0
    if regime == "new":
        t = income
        if t > 2400000: tax += (t-2400000)*0.30; t=2400000
        if t > 2000000: tax += (t-2000000)*0.25; t=2000000
        if t > 1600000: tax += (t-1600000)*0.20; t=1600000
        if t > 1200000: tax += (t-1200000)*0.15; t=1200000
        if t > 800000:  tax += (t-800000)*0.10;  t=800000
        if t > 400000:  tax += (t-400000)*0.05
    else:
        limit = 500000 if age >= 80 else (300000 if age >= 60 else 250000)
        t = income
        if t > 1000000: tax += (t-1000000)*0.30; t=1000000
        if t > 500000:  tax += (t-500000)*0.20;  t=500000
        if t > limit:   tax += (t-limit)*0.05

    surcharge = 0
    if income > 5000000:
        rate = 0.10 if income <= 10000000 else 0.15
        if income > 20000000: rate = 0.25
        if regime == "old" and income > 50000000: rate = 0.37
        surcharge = tax * rate
    
    cess = (tax + surcharge) * 0.04
    return {"base": int(tax), "surcharge": int(surcharge), "cess": int(cess), "total": int(tax + surcharge + cess)}

# --- 5. THE UNIFIED BRAIN ---

sys_instruction_unified = """
You are "TaxGuide AI", a smart Indian Tax Expert.

**YOUR PRIME DIRECTIVE:**
1. **Be Proactive:** If the user gives numbers, **CALCULATE**. Do not wait for a question.
2. **Be Robust:** If data is missing (e.g., Basic Salary), **ASSUME** standard defaults (Basic=50%) and proceed. Do not ask for it.
3. **Be Consistent:** Use the tools provided. Never calculate in your head.

**TOOL USAGE RULES:**

A. **FULL TAX CALCULATION** (Use `CALCULATE(...)`)
   - Trigger: User asks for "Total Tax", "Old vs New", or provides a Salary context.
   - **CRITICAL:** Check for Rent, HRA, and Investments in the user's text.
   - If User says "Rent 20k", you MUST send `rent=20000` (Monthly) or `rent=240000` (Yearly).
   - Do NOT send `rent=0` if the user mentioned rent.

B. **SPOT CHECK MATH** (Use `CALCULATE_MATH(...)`)
   - Trigger: Specific questions like "What is my HRA exemption?" or "Tax on 10L LTCG".
   - Rule: Replace ALL variables with numbers. No text allowed inside the tool.

**OUTPUT FORMAT:**
[Analysis: "Based on Salary X and Rent Y..."]
|||
[Technical Details]
"""

# --- 6. UI SETUP ---
if "chat_session" not in st.session_state:
    st.session_state.chat_session = None
    st.session_state.loaded_persona = None

col1, col2 = st.columns([5, 1])
with col1: st.markdown("### 🇮🇳 TaxGuide AI")
with col2: 
    if st.button("🔄"):
        st.session_state.clear()
        st.rerun()

# Initialize Chat
if not st.session_state.chat_session:
    model = genai.GenerativeModel('gemini-2.0-flash', system_instruction=sys_instruction_unified)
    st.session_state.chat_session = model.start_chat(history=[])
    st.session_state.chat_session.history.append({"role": "model", "parts": ["Hi! I can calculate your tax or answer rules. What is your Salary?"]})

# --- 7. CHAT LOGIC ---
def render_message(text, role, avatar):
    with st.chat_message(role, avatar=avatar):
        if "|||" in text:
            summary, details = text.split("|||", 1)
            st.markdown(summary.strip())
            with st.expander("📝 View Calculation Details"):
                st.markdown(details.strip())
        else:
            st.markdown(text)

for msg in st.session_state.chat_session.history:
    text = msg.parts[0].text if msg.parts else ""
    role = "user" if msg.role == "user" else "assistant"
    # Hide tool triggers from UI
    if text and not any(x in text for x in ["CALCULATE(", "CALCULATE_MATH(", "LOAD(", "Result:"]):
        render_message(text, role, "👤" if role == "user" else "🤖")

if prompt := st.chat_input("Ex: Salary 15L, Rent 20k..."):
    st.chat_message("user", avatar="👤").markdown(prompt)
    
    with st.spinner("Processing..."):
        try:
            response = send_message_with_retry(st.session_state.chat_session, prompt)
            text = response.text
            
            # --- TOOL 1: MATH SPOT CHECK ---
            if "CALCULATE_MATH(" in text:
                expr = text.split("CALCULATE_MATH(")[1][:-1]
                res = safe_math_eval(expr)
                st.toast(f"🧮 Computed: {res}", icon="✅")
                # Force AI to use the result
                send_message_with_retry(st.session_state.chat_session, f"Math Result: {res}. State this exact number to the user.")
                text = st.session_state.chat_session.history[-1].parts[0].text

            # --- TOOL 2: LOAD KNOWLEDGE ---
            if "LOAD(" in text:
                persona = text.split("LOAD(")[1].split(")")[0]
                if st.session_state.loaded_persona != persona:
                    f = inject_knowledge(persona)
                    if f:
                        hist = st.session_state.chat_session.history[:-1]
                        hist.append({"role": "user", "parts": [f, "Context Loaded."]})
                        hist.append({"role": "model", "parts": ["Context received."]}); 
                        # Restart with context
                        model = genai.GenerativeModel('gemini-2.0-flash', system_instruction=sys_instruction_unified)
                        st.session_state.chat_session = model.start_chat(history=hist)
                        st.session_state.loaded_persona = persona
                        st.toast(f"📚 Loaded: {persona}", icon="✅")
                        send_message_with_retry(st.session_state.chat_session, "Context loaded. Proceed.")
                        text = st.session_state.chat_session.history[-1].parts[0].text

            # --- TOOL 3: FULL CALCULATOR ---
            if "CALCULATE(" in text:
                params = text.split("CALCULATE(")[1].split(")")[0]
                d = {"age":30, "salary":0, "business":0, "rent":0, "inv80c":0, "med80d":0, "basic":0}
                for p in params.split(","):
                    if "=" in p:
                        k, v = p.split("=")
                        vc = ''.join(filter(str.isdigit, v))
                        if vc: d[k.strip()] = int(vc)
                
                # Run Python Calc
                res = calculate_tax_detailed(d['age'], d['salary'], d['business'], d['rent'], d['inv80c'], d['med80d'], d['basic'])
                tn, to = res['new']['breakdown']['total'], res['old']['breakdown']['total']
                winner, savings = ("New", to-tn) if tn < to else ("Old", tn-to)
                
                # Generate Report
                report = f"""
                ### 🧾 Tax Report
                **Recommendation:** **{winner} Regime** is better. (Save ₹{savings:,})
                
                | | **New Regime** | **Old Regime** |
                | :--- | :--- | :--- |
                | Taxable Income | ₹{res['new']['net']:,} | ₹{res['old']['net']:,} |
                | **Total Tax** | **₹{tn:,}** | **₹{to:,}** |
                
                ||| 
                **Detailed Breakdown:**
                * **Gross Income:** ₹{d['salary']:,}
                * **HRA Exemption (Old):** ₹{res['old']['deductions']['hra']:,} (Based on Rent: ₹{d['rent']:,})
                * **Standard Deduction:** ₹75k (New) / ₹50k (Old)
                """
                st.chat_message("assistant", avatar="🤖").markdown(report.split("|||")[0])
                with st.expander("📝 View Details"): st.markdown(report.split("|||")[1])
                
                st.session_state.chat_session.history.append({"role": "model", "parts": [f"Result shown: New={tn}, Old={to}"]})

            # Normal Text Response (if no tool used or after tool)
            if not any(x in text for x in ["CALCULATE(", "CALCULATE_MATH(", "LOAD("]):
                render_message(text, "assistant", "🤖")

        except Exception as e: st.error(f"Error: {e}")