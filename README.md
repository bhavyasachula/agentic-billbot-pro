# 📨 Agentic BillBot Pro

**Agentic BillBot Pro** is a high-performance, agent-driven invoice processing and email dispatching system. Built with **LangGraph** and powered by **GPT-OSS-120B**, it transforms raw invoice PDFs and images into professional, context-aware email drafts ready for human-in-the-loop validation and one-click dispatching.

---

## ✨ Key Features

- **🧠 Agentic Intelligence**: Orchestrated by a multi-node LangGraph pipeline for robust extraction and drafting.
- **📄 Advanced Vision/OCR**: Seamlessly processes PDF, PNG, and JPEG invoices using high-accuracy OCR.
- **💬 Conversational UX**: A premium, Gemini-inspired chat interface for managing billing workflows.
- **✍️ Human-in-the-Loop**: Full control to review and edit AI-generated drafts (subject & body) before sending.
- **🚀 Integrated SMTP**: Built-in secure email dispatching with automatic invoice attachments.
- **📂 Bulk Processing**: Support for multiple invoice attachments in a single session.

---

## 🛠️ Technology Stack

| Component | Technology |
| :--- | :--- |
| **Orchestration** | [LangGraph](https://github.com/langchain-ai/langgraph) |
| **Framework** | [LangChain](https://github.com/langchain-ai/langchain) |
| **Frontend** | [Streamlit](https://streamlit.io/) |
| **OCR & Vision** | Pytesseract, PyMuPDF, Pillow |
| **Email Protocol** | SMTP (smtplib) |

---

## 🧠 How It Works

The system utilizes a two-node **LangGraph** pipeline:

1.  **Extract Node**: Uses Vision/OCR to identify the Sender, Client, Invoice ID, Line Items, and Total Amount.
2.  **Draft Node**: Consumes the extracted JSON to generate a professional, branded email body and subject line.
3.  **Human Review**: The user validates the draft within the Streamlit UI, making any necessary tweaks.
4.  **Dispatch**: The email is sent via the configured SMTP server with the original invoice(s) attached.

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10+
- Tesseract OCR installed on your system.

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/bhavyasachula/Agentic-BillBot-Pro.git
cd Agentic-BillBot-Pro

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration
Create a `.env` file in the root directory or configure directly in the Streamlit Sidebar:

```env
# AI Configuration
GROQ_API_KEY=your_groq_api_key_here

# SMTP Configuration (Example for Gmail)
SMTP_EMAIL=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587

# Branding Details
COMPANY_NAME="Your Company Name"
SENDER_NAME="Your Name"
SENDER_PHONE="+1 (555) 000-0000"
```

---

## 🖥️ Usage

Run the application using Streamlit:

```bash
streamlit run app.py
```

1.  **Upload**: Navigate to the chatbox and click the `+` icon or drop your invoice files.
2.  **Command**: Type *"Send this to client@example.com"* or *"Generate a draft"*.
3.  **Review**: Check the extracted details and the auto-generated email.
4.  **Send**: Click **🚀 Send Email** to notify your client!

---

## 🎨 Premium Aesthetics
Enjoy a sleek, modern interface with:
- **Inter Typography** for maximum readability.
- **Glassmorphic Components** and smooth micro-animations.
- **Responsive Dark/Light Modes** (optimized for clarity).
- **Gemini-style Chat Bubbles** for a natural conversational flow.

---

## 📄 License
Distributed under the MIT License. See `LICENSE` for more information.

---
*Developed with ❤️ by the bhavyasachula*
