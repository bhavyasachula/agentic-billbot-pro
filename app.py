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
    st.subheader("Email Details") 

    config.SMTP_EMAIL = st.text_input("Your Email (Required) ", value=config.SMTP_EMAIL, help="The email address you'll use to send invoices.")
    config.SMTP_PASSWORD = st.text_input("App Password (Required)", type="password", value=config.SMTP_PASSWORD, help="Your email provider's App Password (not your regular login password).")
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
for key in ["agent_result", "subject", "body", "step", "file_bytes", "file_name", "customer_email", "chat_messages", "show_uploader", "all_files"]:
    if key not in st.session_state:
        if key == "chat_messages" or key == "all_files":
            st.session_state[key] = []
        elif key == "show_uploader":
            st.session_state[key] = False
        else:
            st.session_state[key] = None

if "step" not in st.session_state or st.session_state["step"] is None:
    st.session_state["step"] = "upload"

# ─── Extra CSS for Gemini-like feel ─────────────────────
st.markdown("""
<style>
    /* Styling the Chat Input area */
    .stChatInputContainer {
        padding-bottom: 20px;
    }
    
    /* Chat message bubble improvements */
    .stChatMessage {
        background-color: transparent !important;
        border: none !important;
    }
    
    .stChatMessage [data-testid="stChatMessageContent"] {
        background-color: #eee;
        border-radius: 18px;
        padding: 12px 18px;
        border: 1px solid #f1f5f9;
        box-shadow: 0 1px 2px rgba(0,0,0,0.02);
    }

    /* Assistant message different color */
    div[data-testid="stChatMessage"]:has(path[d*="M20"]) [data-testid="stChatMessageContent"] {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
    }
</style>
""", unsafe_allow_html=True)

# ─── Title ────────────────────────────────────────────────

st.caption("Chat with AI to Process Invoices and Send Emails.")

# ═══════════════════════════════════════════════════════════
# CHATBOT INTERFACE
# ═══════════════════════════════════════════════════════════

# Display chat messages
for msg in st.session_state["chat_messages"]:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if "attachment" in msg:
            st.info(f"📄 Attached: {msg['attachment']}")

# --- Check if credentials are filled ---
credentials_filled = bool(config.SMTP_EMAIL and config.SMTP_PASSWORD)

if not credentials_filled:
    st.warning("⚠️ **Connection Needed**: Please provide your **Email** and **App Password** in the sidebar to send invoices.")

# --- Chat input with File Attachment (Built-in) ---
prompt_res = st.chat_input(
    "Ask anything...",
    accept_file=True,
    file_type=["pdf", "png", "jpg", "jpeg"],
    disabled=not credentials_filled
)

if prompt_res:
    # 1. Handle uploaded files
    new_files = getattr(prompt_res, "files", [])
    if not new_files and isinstance(prompt_res, dict):
        new_files = prompt_res.get("files", [])
        
    if new_files:
        for f in new_files:
            if not any(existing['name'] == f.name for existing in st.session_state["all_files"]):
                file_bytes = f.read()
                st.session_state["all_files"].append({"name": f.name, "bytes": file_bytes})
                st.session_state["chat_messages"].append({
                    "role": "user", 
                    "content": f"Attached invoice: {f.name}",
                    "attachment": f.name
                })
        
        # Update primary file pointers for backward compatibility
        if st.session_state["all_files"]:
            st.session_state["file_bytes"] = st.session_state["all_files"][0]["bytes"]
            st.session_state["file_name"] = st.session_state["all_files"][0]["name"]
        
        st.toast(f"{len(new_files)} file(s) added! Ready for processing.")

    # 2. Handle text prompt
    prompt = getattr(prompt_res, "text", "")
    if not prompt and isinstance(prompt_res, dict):
        prompt = prompt_res.get("text", "")
    elif not prompt and isinstance(prompt_res, str):
        prompt = prompt_res

    if prompt:
        st.session_state["chat_messages"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)

        # Detect trigger
        import re
        match_send = re.search(r"send this to ([\w\.-]+@[\w\.-]+\.\w+)", prompt.lower())
        is_confirmation = re.search(r"\b(send|yes|send it|go ahead|yep|sure)\b", prompt.lower())
        
        from agent import chat_with_agent

        if match_send:
            target_email = match_send.group(1)
            if "all_files" not in st.session_state or not st.session_state["all_files"]:
                response = "I need an invoice first! Use the + icon inside the chat box to upload one. 📄"
            else:
                st.session_state["customer_email"] = target_email
                with st.status("I'm on it! Extracting and drafting your email...", expanded=False) as status:
                    # Process ALL uploaded files
                    all_images_b64 = []
                    for file_info in st.session_state["all_files"]:
                        images_b64 = file_to_images_b64(file_info["bytes"], file_info["name"])
                        all_images_b64.extend(images_b64)
                    
                    result = run_agent(all_images_b64)
                    
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
                        st.session_state["step"] = "review"
            
            st.session_state["chat_messages"].append({"role": "assistant", "content": response})
            with st.chat_message("assistant"):
                st.markdown(response)
                if "Should I send it?" in response:
                    st.info("💡 You can review the draft below or just say 'Yes'.")

        elif is_confirmation and st.session_state.get("agent_result") and st.session_state["step"] == "review":
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
# REVIEW & SENDING AREA
# ═══════════════════════════════════════════════════════════
if st.session_state["step"] == "review":
    st.markdown("---")
    st.markdown("### 📝 Review Email Draft")
    with st.container(border=True):
        st.markdown(f"**To:** {st.session_state.get('customer_email', '')}")
        st.session_state["subject"] = st.text_input("Subject", value=st.session_state["subject"])
        st.session_state["body"] = st.text_area("Email Body", value=st.session_state["body"], height=300)

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🚀 Send Email", use_container_width=True, type="primary", disabled=not credentials_filled):
                st.session_state["step"] = "sending"
                st.rerun()
        with col2:
            if st.button("✖️ Cancel", use_container_width=True):
                st.session_state["step"] = "upload"
                st.rerun()

elif st.session_state["step"] == "sending":
    with st.spinner("Dispatching email..."):
        result_msg = send_email(
            to_email=st.session_state["customer_email"],
            subject=st.session_state["subject"],
            body=st.session_state["body"],
            attachments=st.session_state.get("all_files", []),
        )
    if result_msg == "ok":
        st.session_state["step"] = "done"
        st.rerun()
    else:
        st.error(result_msg)
        st.session_state["step"] = "review"

elif st.session_state["step"] == "done":
    st.balloons()
    st.success(f"✅ Email sent successfully to {st.session_state['customer_email']}!")
    if st.button("Start New Case"):
        for key in ["agent_result", "subject", "body", "customer_email", "chat_messages", "file_bytes", "file_name", "all_files"]:
            st.session_state[key] = None if key != "chat_messages" else []
        st.session_state["step"] = "upload"
        st.rerun()

