"""
Agentic Invoice Dispatcher — True Agent Architecture

Uses LangChain's create_tool_calling_agent + AgentExecutor so the LLM
autonomously decides which tools to invoke based on user intent.

Tools available to the agent:
  1. extract_invoice  — OCR + parse invoice images into structured data
  2. draft_email      — Generate a professional email from extracted invoice data
  3. send_email       — Actually dispatch the email via SMTP
"""

import json
import base64
from typing import Any, Dict, List, Optional
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain_classic.agents import create_tool_calling_agent, AgentExecutor
import streamlit as st
import config
from prompts import INVOICE_VISION_PROMPT, EMAIL_DRAFT_PROMPT

# ─── LLM ─────────────────────────────────────────────────
def _get_llm():
    return ChatGroq(
        model="openai/gpt-oss-120b",
        temperature=config.TEMPERATURE,
    )


def _strip_json(text: str) -> str:
    """Remove markdown code fences if the LLM wraps its JSON."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]
    return text.strip()


# ═══════════════════════════════════════════════════════════
# TOOL DEFINITIONS — the agent decides when to call these
# ═══════════════════════════════════════════════════════════

@tool
def extract_invoice_tool(placeholder: str = "run") -> str:
    """Extract structured data from uploaded invoice images using OCR.
    Call this tool when the user wants to process, read, or extract data from
    their uploaded invoice. The invoice images are automatically loaded from
    the session. Returns the extracted invoice data as JSON.
    """
    from file_utils import file_to_images_b64, image_to_text

    all_files = st.session_state.get("all_files", [])
    if not all_files:
        return json.dumps({"error": "No invoice files uploaded yet. Please upload an invoice first."})

    try:
        # Convert all files to base64 images
        all_images_b64 = []
        for file_info in all_files:
            images_b64 = file_to_images_b64(file_info["bytes"], file_info["name"])
            all_images_b64.extend(images_b64)

        # OCR each image
        full_extracted_text = ""
        for idx, img_b64 in enumerate(all_images_b64):
            img_bytes = base64.b64decode(img_b64)
            text = image_to_text(img_bytes)
            if text.strip():
                full_extracted_text += f"\n--- Page/Image {idx+1} ---\n{text}\n"

        if not full_extracted_text.strip():
            return json.dumps({"error": "OCR failed to extract text from the invoice images."})

        # Use LLM to structure the OCR text
        llm = _get_llm()
        prompt = INVOICE_VISION_PROMPT + "\n\nExtracted invoice text:\n" + full_extracted_text
        response = llm.invoke(prompt)
        data = json.loads(_strip_json(response.content))

        # Store in session state for other tools
        st.session_state["extracted_invoice_data"] = data
        st.session_state["invoice_images_b64"] = all_images_b64

        return json.dumps({
            "status": "success",
            "extracted_data": data,
            "message": f"Successfully extracted invoice data. Invoice #{data.get('invoice_id', 'N/A')} for {data.get('client_name', 'Unknown')} — Total: {data.get('total_amount', 'N/A')}"
        })

    except Exception as e:
        return json.dumps({"error": f"Failed to extract invoice data: {e}"})


@tool
def draft_email_tool(recipient_email: str) -> str:
    """Draft a professional email from the extracted invoice data.
    Call this tool AFTER extract_invoice_tool has been run, when the user
    wants to compose/draft an email to send the invoice.

    Args:
        recipient_email: The email address to send the invoice to.
    """
    data = st.session_state.get("extracted_invoice_data")
    if not data:
        return json.dumps({"error": "No invoice data found. Please extract the invoice first using extract_invoice_tool."})

    try:
        llm = _get_llm()

        # Format line items
        items_str = ""
        for item in data.get("line_items", []):
            if isinstance(item, dict):
                items_str += f"  - {item.get('description', '?')}: {item.get('amount', '?')}\n"
            else:
                items_str += f"  - {item}\n"

        # Gather sender details from session
        company_name = st.session_state.get("company_name") or config.COMPANY_NAME or "Our Company"
        sender_name = data.get("sender_name") or st.session_state.get("sender_name") or config.SENDER_NAME or "the Billing Dept"
        sender_phone = st.session_state.get("sender_phone") or "N/A"
        sender_email = (
            st.session_state.get("sender_email")
            or config.SENDER_EMAIL
            or st.session_state.get("smtp_email")
            or config.SMTP_EMAIL
            or "N/A"
        )

        prompt = EMAIL_DRAFT_PROMPT.format(
            sender_name=sender_name,
            company_name=company_name,
            sender_phone=sender_phone,
            sender_email=sender_email,
            client_name=data.get("client_name", "Customer"),
            invoice_id=data.get("invoice_id", "N/A"),
            line_items=items_str.strip(),
            total_amount=data.get("total_amount", "N/A"),
        )

        response = llm.invoke(prompt)
        email = json.loads(_strip_json(response.content))

        subject = email.get("subject", "")
        body = email.get("body", "")

        # Store draft in session for review / send
        st.session_state["email_subject"] = subject
        st.session_state["email_body"] = body
        st.session_state["customer_email"] = recipient_email
        st.session_state["step"] = "review"

        return json.dumps({
            "status": "success",
            "subject": subject,
            "body": body,
            "recipient": recipient_email,
            "message": f"Email draft created for {recipient_email}. The user can review it in the draft panel below."
        })

    except Exception as e:
        return json.dumps({"error": f"Failed to draft email: {e}"})


@tool
def send_email_tool(placeholder: str = "run") -> str:
    """Send the drafted invoice email to the recipient via SMTP.
    Call this tool when the user confirms they want to send the email.
    The email draft, recipient, and attachments are loaded from the session.
    """
    from email_sender import send_email

    customer_email = st.session_state.get("customer_email")
    subject = st.session_state.get("email_subject") or st.session_state.get("subject")
    body = st.session_state.get("email_body") or st.session_state.get("body")
    smtp_user = st.session_state.get("smtp_email")
    smtp_password = st.session_state.get("smtp_password")
    attachments = st.session_state.get("all_files", [])

    if not customer_email:
        return json.dumps({"error": "No recipient email set. Draft the email first."})
    if not subject or not body:
        return json.dumps({"error": "No email draft found. Draft the email first."})
    if not smtp_user or not smtp_password:
        return json.dumps({"error": "SMTP credentials not configured. Please set them in the sidebar."})

    result = send_email(
        to_email=customer_email,
        subject=subject,
        body=body,
        smtp_user=smtp_user,
        smtp_password=smtp_password,
        attachments=attachments,
    )

    if result == "ok":
        st.session_state["step"] = "done"
        return json.dumps({
            "status": "success",
            "message": f"Email sent successfully to {customer_email}!"
        })
    else:
        return json.dumps({"error": result})


# ═══════════════════════════════════════════════════════════
# AGENT CREATION — create_tool_calling_agent + AgentExecutor
# ═══════════════════════════════════════════════════════════

AGENT_SYSTEM_PROMPT = """You are a helpful, professional, and friendly Conversational Billing Agent called "Invoice Dispatcher".

You have access to three tools to help users process and send invoices:

1. **extract_invoice_tool** — Extract data from uploaded invoice images (OCR + AI parsing).
   Use this when the user uploads an invoice and wants to process it.

2. **draft_email_tool** — Draft a professional email from extracted invoice data.
   Use this when the user wants to send an invoice email to someone. Requires an email address.
   Always call extract_invoice_tool FIRST if invoice data hasn't been extracted yet.

3. **send_email_tool** — Actually send the drafted email via SMTP.
   Use this ONLY when the user explicitly confirms they want to send the email
   (e.g., "yes", "send it", "go ahead", "sure", "bhejo", etc.).

IMPORTANT RULES:
- Do not accept any other requests and generate any thing except What billing agent do like - eg: generate me some code , What is the weather etc.
- When a user says something like "send this to user@example.com", you should:
  1. First call extract_invoice_tool to process the uploaded invoice
  2. Then call draft_email_tool with the provided email address
  3. Ask the user to review the draft before sending
- Do NOT call send_email_tool unless the user explicitly confirms.
- If no invoice is uploaded, ask the user to upload one first.
- For general conversation, just chat naturally without calling any tools.
- Be concise, warm, and premium in tone - like a high-end AI assistant.
Context: The user interacts via a Streamlit chat interface where they can upload
invoice files (PDF/images) using the attachment button in the chat input.
"""


def build_agent_executor() -> AgentExecutor:
    """Build and return the AgentExecutor with all tools."""
    llm = _get_llm()
    tools = [extract_invoice_tool, draft_email_tool, send_email_tool]

    prompt = ChatPromptTemplate.from_messages([
        ("system", AGENT_SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    agent = create_tool_calling_agent(llm, tools, prompt)

    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=6,        # enough to chain extract → draft → respond
        return_intermediate_steps=True,
    )

    return executor


def run_agent_chat(user_input: str, chat_history: List[Dict]) -> Dict[str, Any]:
    """
    Run the agent on a single user turn.

    Returns:
        {
            "output": str,                   # the agent's final text reply
            "intermediate_steps": list,       # tool calls + results
            "tools_used": list[str],          # names of tools invoked
        }
    """
    executor = build_agent_executor()

    # Convert chat history to LangChain message objects
    lc_history = []
    for m in chat_history:
        if m["role"] == "user":
            lc_history.append(HumanMessage(content=m["content"]))
        elif m["role"] == "assistant":
            lc_history.append(AIMessage(content=m["content"]))

    result = executor.invoke({
        "input": user_input,
        "chat_history": lc_history,
    })

    tools_used = []
    for step in result.get("intermediate_steps", []):
        action = step[0]
        tools_used.append(action.tool)

    return {
        "output": result["output"],
        "intermediate_steps": result.get("intermediate_steps", []),
        "tools_used": tools_used,
    }
