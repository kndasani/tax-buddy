import streamlit as st
import google.generativeai as genai
import pickle
import numpy as np
import os

# 1. PAGE SETUP
st.set_page_config(page_title="TaxGuide AI", page_icon="📊")
st.title("📊 TaxGuide AI: Intelligent Tax Assistant")

# 1.1 DISCLAIMER
with st.sidebar:
    st.header("⚠️ Disclaimer")
    st.warning(
        "This tool is designed for **Indian Income Tax (FY 2025-26)** only.\n\n"
        "It is an AI-powered helper, not a substitute for professional advice. "
        "Please consult a **Chartered Accountant (CA)** before filing your taxes."
    )
    st.markdown("---")

# 2. SETUP API
if "GOOGLE_API_KEY" in st.secrets:
    api_key = st.secrets["GOOGLE_API_KEY"]
else:
    api_key = st.text_input("Enter Google API Key:", type="password")

if not api_key:
    st.info("Please enter your API Key to continue.")
    st.stop()

genai.configure(api_key=api_key)

# 3. DEFINE THE BRAIN (The Interviewer Logic)
# We define this ONCE so the model knows how to behave from the start.
system_instruction = """
You are a friendly Tax Assistant.
Your goal is to have a simple chat first, and then do the complex math.

--- PHASE 1: THE INTERVIEW (Step-by-Step) ---
Do NOT ask for everything at once. Follow this strict order:

1. **The Basics:**
   - Ask: "What is your annual salary?"
   - Ask: "How old are you?" (Crucial for Senior Citizen slabs).
   - *Immediate:* Once you have these, show the **New Regime Tax** baseline.

2. **The "One Question" Rule:**
   - Ask these ONE BY ONE. Wait for the answer.
   A. "Do you live in a rented house? If yes, how much is the monthly rent?"
   B. "Do you have 80C investments (PPF, LIC, ELSS)?"
   C. "Do you pay for medical insurance (80D)?"

--- PHASE 2: THE CALCULATION (Strict Rules) ---
When calculating the final comparison, you MUST follow these logic steps:

**STEP 1: SANITIZE INPUTS (CRITICAL)**
Before calculating Old Regime tax, apply these limits:
- **80C CAP:** If user input > 1.5 Lakhs (e.g., 2.5L), USE **1.5 Lakhs**.
  - *Required Output:* You MUST write: "⚠️ *Note: I limited your 80C deduction to ₹1.5 Lakhs as per tax laws.*"
- **80D CAP:** Limit to 25k (Self) or 50k (Parents/Senior).

**STEP 2: HRA MATH**
- If Rent is paid: HRA Exemption = Rent Paid - (10% of Assumed Basic).
- *Assume Basic = 50% of Total Income.*
- Show this formula in the output.

**STEP 3: TAX SLABS (FY 2025-26)**
- **New Regime:** 0-12L Tax Free (Rebate). Standard Deduction 75k.
- **Old Regime:** Standard Deduction 50k.
  - Age < 60: Exempt up to 2.5L.
  - Age 60+: Exempt up to 3L.

--- EXECUTION ---
Calculate accurately. If inputs are messy, fix them (Sanitize) before calculating.
"""
# 4. INITIALIZE CHAT MEMORY
# We use a persistent chat session so it remembers your previous answers (like Salary or Rent).
if "chat_session" not in st.session_state:
    model = genai.GenerativeModel('gemini-2.0-flash', system_instruction=system_instruction)
    st.session_state.chat_session = model.start_chat(history=[])

# 5. DISPLAY CHAT HISTORY

# Check if history is empty (User just opened the app)
if not st.session_state.chat_session.history:
    with st.container():
        st.markdown("### 👋 Welcome to TaxGuide AI!")
        st.markdown("I can help you choose the best tax regime (Old vs New).")
        st.info("👇 **To get started, just tell me your salary:**")
        st.code("My salary is 18 Lakhs", language=None) 
        st.markdown("*I will ask you about rent and investments later!*")

for message in st.session_state.chat_session.history:
    role = "user" if message.role == "user" else "assistant"
    with st.chat_message(role):
        st.markdown(message.parts[0].text)

# 6. HANDLE USER INPUT
if prompt := st.chat_input("Ask a question (e.g., Calculate tax for 15 Lakhs)..."):
    # Display user message
    st.chat_message("user").markdown(prompt)

    # Send to Gemini
    with st.spinner("Thinking..."):
        try:
            response = st.session_state.chat_session.send_message(prompt)
            st.chat_message("assistant").markdown(response.text)
        except Exception as e:
            st.error(f"An error occurred: {e}")