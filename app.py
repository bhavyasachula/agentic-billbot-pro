"""
Streamlit app — Agentic Invoice Dispatcher

Flow:
  1. User uploads invoice (PDF / image) + enters customer email
  2. Agent extracts data & drafts email
  3. User reviews → can edit subject & body (human-in-the-loop)
  4. User clicks Send → email dispatched with invoice attached
"""

import json
import streamlit as st
import os

from agent import run_agent  # AFTER setting env ✅
import config
from file_utils import file_to_images_b64
from email_sender import send_email

# ─── Page config ──────────────────────────────────────────
st.set_page_config(
    page_title="Invoice Dispatcher",
    page_icon="📨",
    layout="centered",
)

# ─── Minimal custom CSS ──────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    .block-container { max-width: 720px; }

    .step-label {
        display: inline-block;
        background: #2563eb;
        color: white;
        border-radius: 50%;
        width: 28px; height: 28px;
        text-align: center;
        line-height: 28px;
        font-weight: 600;
        font-size: 0.85rem;
        margin-right: 8px;
    }
</style>
""", unsafe_allow_html=True)

# ─── Sidebar — settings ──────────────────────────────────
with st.sidebar:
    st.header("Settings")

    

    st.markdown("---")
    st.subheader("SMTP (Email)") 

    config.SMTP_EMAIL = st.text_input("Your Email", value=config.SMTP_EMAIL)
    config.SMTP_PASSWORD = st.text_input("App Password", type="password", value=config.SMTP_PASSWORD)
    # config.SMTP_HOST = st.text_input("SMTP Host", value=config.SMTP_HOST)
    # config.SMTP_PORT = int(st.text_input("SMTP Port", value=str(config.SMTP_PORT)))

    st.markdown("---")
    st.subheader("Sender Details")
    config.COMPANY_NAME = st.text_input("Company Name", value=config.COMPANY_NAME)
    config.SENDER_NAME = st.text_input("Your Name", value=config.SENDER_NAME)
    config.SENDER_PHONE = st.text_input("Phone Number", value=config.SENDER_PHONE)
    config.SENDER_EMAIL = st.text_input("Sender Email (for sign-off)", value=config.SENDER_EMAIL or config.SMTP_EMAIL)

# ─── Title ────────────────────────────────────────────────
st.title("Invoice Dispatcher Agent")
st.caption("Upload an invoice → AI drafts an email → Review & send.")
st.markdown("---")

# ─── Session state init ──────────────────────────────────
for key in ["agent_result", "subject", "body", "step", "file_bytes", "file_name", "customer_email", "chat_messages"]:
    if key not in st.session_state:
        st.session_state[key] = None if key != "chat_messages" else []
if "step" not in st.session_state or st.session_state["step"] is None:
    st.session_state["step"] = "upload"

# ═══════════════════════════════════════════════════════════
# CHATBOT INTERFACE
# ═══════════════════════════════════════════════════════════
st.markdown("### 💬 Chat with Agentic Chatbot")

for msg in st.session_state["chat_messages"]:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

prompt = st.chat_input("Say 'Send this to customer@email.com' after uploading an invoice")

if prompt:
    st.session_state["chat_messages"].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    # Detect trigger
    import re
    match_send = re.search(r"send this to ([\w\.-]+@[\w\.-]+\.\w+)", prompt.lower())
    is_confirmation = re.search(r"\b(yes|send it|go ahead|yep|sure)\b", prompt.lower())
    
    from agent import chat_with_agent

    if match_send:
        target_email = match_send.group(1)
        if not st.session_state.get("file_bytes"):
            response = "Please upload an invoice first so I can process it! 📄"
        else:
            st.session_state["customer_email"] = target_email
            with st.status("I'm on it! Extracting and drafting your email...", expanded=False) as status:
                images_b64 = file_to_images_b64(st.session_state["file_bytes"], st.session_state["file_name"])
                result = run_agent(images_b64)
                
                if result.get("error"):
                    response = f"I ran into a bit of a snag: {result['error']}"
                    status.update(label="Oops, something went wrong.", state="error")
                else:
                    st.session_state["agent_result"] = result
                    st.session_state["subject"] = result.get("email_subject", "")
                    st.session_state["body"] = result.get("email_body", "")
                    sender_name = result.get("extracted_data", {}).get("sender_name", "the Sender")
                    
                    response = f"I've tailored the email based on the {sender_name} receipt. Should I send it?"
                    
                    status.update(label="Draft ready!", state="complete")
                    st.session_state["step"] = "review" # Allow sending via button too
        
        st.session_state["chat_messages"].append({"role": "assistant", "content": response})
        with st.chat_message("assistant"):
            st.markdown(response)
            if "Should I send it?" in response:
                if st.button("Yes, Send it now!", key="chat_send_btn_dynamic"):
                    st.session_state["step"] = "sending"
                    st.rerun()

    elif is_confirmation and st.session_state.get("agent_result") and st.session_state["step"] == "review":
        # Confirmed via chat
        st.session_state["step"] = "sending"
        st.rerun()
    else:
        # General dynamic chat
        with st.spinner("Thinking..."):
            has_invoice = st.session_state.get("file_bytes") is not None
            response = chat_with_agent(st.session_state["chat_messages"], has_invoice=has_invoice)
        
        st.session_state["chat_messages"].append({"role": "assistant", "content": response})
        with st.chat_message("assistant"):
            st.markdown(response)

# ═══════════════════════════════════════════════════════════
# ORIGINAL FLOW (FOR UPLOAD)
# ═══════════════════════════════════════════════════════════
st.markdown("---")

if st.session_state["step"] == "upload":
    st.markdown('<span class="step-label">1</span> **Upload Invoice**', unsafe_allow_html=True)
    uploaded = st.file_uploader("Upload invoice (PDF, PNG, JPG, JPEG)", type=["pdf", "png", "jpg", "jpeg"])

    if uploaded:
        st.session_state["file_bytes"] = uploaded.read()
        st.session_state["file_name"] = uploaded.name
        st.success(f"File '{uploaded.name}' uploaded! Now tell me where to send it in the chat above.")

elif st.session_state["step"] == "review":
    st.markdown('<span class="step-label">2</span> **Review & Edit Draft**', unsafe_allow_html=True)
    st.markdown(f"**To:** {st.session_state.get('customer_email', '')}")
    
    st.session_state["subject"] = st.text_input("Subject", value=st.session_state["subject"])
    st.session_state["body"] = st.text_area("Email Body", value=st.session_state["body"], height=300)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Send Email", use_container_width=True, type="primary"):
            st.session_state["step"] = "sending"
            st.rerun()
    with col2:
        if st.button("Cancel", use_container_width=True):
            st.session_state["step"] = "upload"
            st.rerun()

elif st.session_state["step"] == "sending":
    with st.spinner("Dispatching email..."):
        result_msg = send_email(
            to_email=st.session_state["customer_email"],
            subject=st.session_state["subject"],
            body=st.session_state["body"],
            attachment_bytes=st.session_state["file_bytes"],
            attachment_filename=st.session_state["file_name"],
        )
    if result_msg == "ok":
        st.session_state["step"] = "done"
        st.rerun()
    else:
        st.error(result_msg)
        st.session_state["step"] = "review"

elif st.session_state["step"] == "done":
    st.balloons()
    st.success(f"Email sent successfully to {st.session_state['customer_email']}!")
    if st.button("Start New"):
        for key in ["agent_result", "subject", "body", "customer_email", "chat_messages"]:
            st.session_state[key] = None if key != "chat_messages" else []
        st.session_state["step"] = "upload"
        st.rerun()
