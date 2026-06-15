import smtplib
import base64
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import List, Dict, Optional

from app.core.config import settings

class EmailService:
    def send_inquiry_email(
        self,
        inquiry_type: str,
        full_name: str,
        email: str,
        phone: str,
        message: str,
        subject: str,
        additional_data: dict,
        file_links: List[str],
        files: List[Dict[str, str]],
        recipient_emails: List[str]
    ) -> bool:
        """
        Builds and sends an HTML email for an inquiry.
        Attaches the raw files directly to the email.
        """
        # Always email to info@getmeds.ph in addition to custom recipients
        all_recipients = list(set(["info@getmeds.ph"] + [r.strip() for r in recipient_emails if r.strip()]))
        
        # Build HTML Body
        html_content = self._build_email_html(
            inquiry_type, full_name, email, phone, message, subject, additional_data, file_links
        )
        
        email_subject = f"[GetMEDS Website Inquiry] {inquiry_type} - {full_name}"
        
        # Check if SMTP is configured
        if not settings.SMTP_HOST:
            print("======================================================================")
            print("[SIMULATED EMAIL DISPATCH]")
            print(f"To: {', '.join(all_recipients)}")
            print(f"From: {settings.SMTP_FROM}")
            print(f"Subject: {email_subject}")
            print(f"Attachments: {[f.get('name') for f in files if f.get('name')]}")
            print("----------------------------------------------------------------------")
            print(f"Body preview: {html_content[:500]}...")
            print("======================================================================")
            return True

        try:
            # Construct message
            msg = MIMEMultipart("mixed")
            msg["From"] = settings.SMTP_FROM
            msg["To"] = ", ".join(all_recipients)
            msg["Subject"] = email_subject

            # Attach HTML body
            msg_alternative = MIMEMultipart("alternative")
            msg.attach(msg_alternative)
            msg_alternative.attach(MIMEText(html_content, "html", "utf-8"))

            # Attach files if any
            if files:
                for file_info in files:
                    file_name = file_info.get("name")
                    file_base64 = file_info.get("base64")
                    if not file_name or not file_base64:
                        continue
                    try:
                        file_data = base64.b64decode(file_base64)
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(file_data)
                        encoders.encode_base64(part)
                        part.add_header(
                            "Content-Disposition",
                            f'attachment; filename="{file_name}"'
                        )
                        msg.attach(part)
                        print(f"INFO: Attached file '{file_name}' to email.")
                    except Exception as attach_err:
                        print(f"ERROR: Failed to attach file '{file_name}': {attach_err}")

            # Connect and send
            port = int(settings.SMTP_PORT)
            if port == 465:
                server = smtplib.SMTP_SSL(settings.SMTP_HOST, port, timeout=15)
            else:
                server = smtplib.SMTP(settings.SMTP_HOST, port, timeout=15)
                server.starttls()
            
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            
            server.sendmail(settings.SMTP_FROM, all_recipients, msg.as_string())
            server.quit()
            print(f"INFO: Inquiry email sent successfully to {all_recipients}")
            return True

        except Exception as smtp_err:
            print(f"ERROR: SMTP email dispatch failed: {smtp_err}")
            return False

    def _build_email_html(
        self,
        inquiry_type: str,
        full_name: str,
        email: str,
        phone: str,
        message: str,
        subject: str,
        additional_data: dict,
        file_links: List[str]
    ) -> str:
        additional_rows = ""
        
        # Add special fields based on type
        if inquiry_type == "Career Inquiry":
            position = additional_data.get("position") or subject
            if position:
                additional_rows += f"<tr><td><b>Target Position:</b></td><td>{position}</td></tr>"
        elif inquiry_type == "Contact Us":
            if phone:
                additional_rows += f"<tr><td><b>Phone Number:</b></td><td>{phone}</td></tr>"
            if subject:
                additional_rows += f"<tr><td><b>Subject:</b></td><td>{subject}</td></tr>"
        elif inquiry_type == "Product Inquiry":
            prod_name = additional_data.get("productName")
            if prod_name:
                additional_rows += f"<tr><td><b>Product of Interest:</b></td><td>{prod_name}</td></tr>"
            if phone:
                additional_rows += f"<tr><td><b>Phone Number:</b></td><td>{phone}</td></tr>"
        elif inquiry_type == "Order Medicine":
            dob = additional_data.get("dob")
            address = additional_data.get("address")
            if phone:
                additional_rows += f"<tr><td><b>Phone Number:</b></td><td>{phone}</td></tr>"
            if dob:
                additional_rows += f"<tr><td><b>Date of Birth:</b></td><td>{dob}</td></tr>"
            if address:
                additional_rows += f"<tr><td><b>Delivery Address:</b></td><td>{address}</td></tr>"
        elif inquiry_type == "Partnership":
            if phone:
                additional_rows += f"<tr><td><b>Phone Number:</b></td><td>{phone}</td></tr>"
            if subject:
                additional_rows += f"<tr><td><b>Subject:</b></td><td>{subject}</td></tr>"

        attachments_row = ""
        if file_links:
            links_html = ", ".join([f"<a href='{link}' target='_blank'>{link.split('/')[-1]}</a>" for link in file_links])
            attachments_row = f"<tr><td><b>Uploaded Assets (Sanity):</b></td><td>{links_html}</td></tr>"

        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #2D3748; background-color: #F7FAFC; padding: 20px; }}
                .container {{ width: 100%; max-width: 600px; margin: 0 auto; border: 1px solid #E2E8F0; border-radius: 12px; overflow: hidden; background-color: #FFFFFF; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }}
                .header {{ background: linear-gradient(135deg, #61A644 0%, #1D9FDA 100%); padding: 30px 20px; text-align: center; color: white; }}
                .header h2 {{ margin: 0; font-size: 24px; font-weight: 800; letter-spacing: -0.5px; }}
                .header p {{ margin: 5px 0 0 0; font-size: 14px; font-weight: 600; opacity: 0.9; text-transform: uppercase; letter-spacing: 1px; }}
                .content {{ padding: 30px; line-height: 1.6; }}
                .table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                .table td {{ padding: 12px; border-bottom: 1px solid #EDF2F7; font-size: 14px; vertical-align: top; }}
                .table td:first-child {{ width: 160px; color: #4A5568; font-weight: bold; }}
                .message-title {{ margin-top: 25px; margin-bottom: 10px; color: #1D9FDA; font-size: 16px; font-weight: bold; border-left: 3px solid #61A644; padding-left: 10px; }}
                .message-box {{ background-color: #F7FAFC; border: 1px solid #EDF2F7; border-radius: 8px; padding: 20px; font-size: 14px; color: #4A5568; white-space: pre-wrap; }}
                .footer {{ background-color: #EDF2F7; padding: 20px; text-align: center; font-size: 11px; color: #718096; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>New Inquiry Received</h2>
                    <p>{inquiry_type}</p>
                </div>
                <div class="content">
                    <p style="margin-top: 0; font-size: 15px;">Hello team,</p>
                    <p style="font-size: 14px; color: #4A5568;">A new inquiry has been submitted from the GetMEDS website. Please review the details below:</p>
                    <table class="table">
                        <tr>
                            <td><b>Sender Name:</b></td>
                            <td>{full_name}</td>
                        </tr>
                        <tr>
                            <td><b>Email Address:</b></td>
                            <td><a href="mailto:{email}">{email}</a></td>
                        </tr>
                        {additional_rows}
                        {attachments_row}
                    </table>
                    
                    <div class="message-title">Inquiry Message</div>
                    <div class="message-box">{message or "<i>No text message provided.</i>"}</div>
                </div>
                <div class="footer">
                    <p>This is an automated notification from the GetMEDS website inquiry gateway.</p>
                </div>
            </div>
        </body>
        </html>
        """
        return html

email_service = EmailService()
