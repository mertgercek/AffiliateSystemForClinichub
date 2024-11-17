import os
from flask import current_app, render_template_string, url_for, request
import mandrill
from jinja2 import Template
from datetime import datetime
import hashlib

def get_mandrill_client():
    api_key = current_app.config['MANDRILL_API_KEY']
    return mandrill.Mandrill(api_key)

def get_unsubscribe_link(email):
    """Generate a unique unsubscribe link for the email"""
    secret_key = current_app.config['SECRET_KEY']
    token = hashlib.sha256(f"{email}:{secret_key}".encode()).hexdigest()
    return url_for('auth.unsubscribe', token=token, _external=True)

def get_email_template(template_content):
    """Wrap email content in base template with required elements"""
    base_url = url_for('index', _external=True)
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta name="x-apple-disable-message-reformatting">
        <title>ClinicHub</title>
    </head>
    <body style="margin: 0; padding: 0; font-family: Arial, sans-serif; line-height: 1.6; background-color: #f4f4f4;">
        <!-- Preview Text -->
        <div style="display: none; max-height: 0px; overflow: hidden;">
            ClinicHub - Your Medical Tourism Partner
            &nbsp;‌&nbsp;‌&nbsp;‌&nbsp;‌&nbsp;‌&nbsp;‌&nbsp;‌&nbsp;‌&nbsp;‌&nbsp;‌&nbsp;‌
        </div>
        
        <!-- Main Content -->
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="text-align: center; margin-bottom: 30px;">
                <img src="{base_url}static/images/logo.png" alt="ClinicHub Logo" style="max-width: 200px;">
            </div>
            
            <!-- Email Content -->
            <div style="background-color: #ffffff; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                {template_content}
            </div>
            
            <!-- Footer -->
            <div style="text-align: center; margin-top: 20px; color: #666; font-size: 12px;">
                <p>© {{ CURRENT_YEAR }} ClinicHub. All rights reserved.</p>
                <p>
                    You're receiving this email because you're registered with ClinicHub.<br>
                    Our mailing address is:<br>
                    ClinicHub, 123 Medical Plaza, Istanbul, Turkey
                </p>
                <p>
                    <a href="{{{{ unsubscribe_link }}}}" style="color: #666; text-decoration: underline;">
                        Unsubscribe from these emails
                    </a>
                    &nbsp;|&nbsp;
                    <a href="{base_url}privacy" style="color: #666; text-decoration: underline;">
                        Privacy Policy
                    </a>
                    &nbsp;|&nbsp;
                    <a href="{base_url}terms" style="color: #666; text-decoration: underline;">
                        Terms of Service
                    </a>
                </p>
            </div>
        </div>
    </body>
    </html>
    """

def send_email(to_email, subject, html_content):
    """Send email with proper configuration and formatting"""
    try:
        client = get_mandrill_client()
        
        # Generate unsubscribe link
        unsubscribe_link = get_unsubscribe_link(to_email)
        
        # Wrap content in base template
        full_html = get_email_template(html_content).replace(
            '{{{{ unsubscribe_link }}}}', 
            unsubscribe_link
        )
        
        message = {
            'from_email': 'no-reply@clinichub.com',
            'from_name': 'Clinichub Partners',
            'subject': subject,
            'html': full_html,
            'to': [{'email': to_email, 'type': 'to'}],
            'track_opens': True,
            'track_clicks': True,
            'important': True,
            'headers': {
                'Reply-To': 'no-reply@clinichub.com',
                'List-Unsubscribe': f'<mailto:unsubscribe@clinichub.com?subject=unsubscribe>, <{unsubscribe_link}>',
                'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click',
                'Feedback-ID': 'clinichub:mandrill',
                'X-MC-Tags': 'clinichub,transactional',
                'X-MC-BulkSender': 'yes'
            },
            'metadata': {
                'website': url_for('index', _external=True)
            },
            'merge': True,
            'merge_language': 'handlebars',
            'merge_vars': [{
                'rcpt': to_email,
                'vars': [
                    {'name': 'CURRENT_YEAR', 'content': str(datetime.now().year)},
                    {'name': 'UNSUBSCRIBE_LINK', 'content': unsubscribe_link}
                ]
            }],
            'tags': ['transactional']
        }
        
        result = client.messages.send(message=message)
        return True
    except Exception as e:
        current_app.logger.error(f"Error sending email: {str(e)}")
        return False

def send_verification_email(email, token):
    """Send email verification with professional template"""
    verification_link = url_for('auth.verify_email', token=token, _external=True)
    base_url = url_for('index', _external=True)
    template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Verify Your Email - ClinicHub</title>
    </head>
    <body style="margin: 0; padding: 0; font-family: Arial, sans-serif; line-height: 1.6;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="text-align: center; margin-bottom: 30px;">
                <img src="{base_url}static/images/logo.png" alt="ClinicHub Logo" style="max-width: 200px;">
            </div>
            <div style="background-color: #ffffff; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <h2 style="color: #333; margin-bottom: 20px;">Verify Your Email Address</h2>
                <p>Welcome to ClinicHub! Please verify your email address to get started.</p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{verification_link}" 
                       style="background-color: #0891b2; color: white; padding: 12px 30px; 
                              text-decoration: none; border-radius: 5px; font-weight: bold;">
                        Verify Email
                    </a>
                </div>
                <p style="color: #666; font-size: 14px;">
                    If you didn't create an account with ClinicHub, please ignore this email.
                </p>
            </div>
        </div>
    </body>
    </html>
    """.format(verification_link=verification_link, base_url=base_url)
    
    return send_email(email, "Verify Your ClinicHub Account", template)

def send_welcome_email(email, username):
    """Send welcome email with professional template"""
    template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Welcome to ClinicHub</title>
    </head>
    <body style="margin: 0; padding: 0; font-family: Arial, sans-serif; line-height: 1.6;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="text-align: center; margin-bottom: 30px;">
                <img src="https://clinichub.com/assets/custom/images/logo.png" alt="ClinicHub Logo" style="max-width: 200px;">
            </div>
            <div style="background-color: #ffffff; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <h2 style="color: #333; margin-bottom: 20px;">Welcome to ClinicHub!</h2>
                <p>Hello {{ username }},</p>
                <p>Thank you for joining ClinicHub! We're excited to have you as part of our community.</p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="https://clinichub.com/login" 
                       style="background-color: #0891b2; color: white; padding: 12px 30px; 
                              text-decoration: none; border-radius: 5px; font-weight: bold;">
                        Login to Your Account
                    </a>
                </div>
                <p>If you have any questions, feel free to contact our support team.</p>
            </div>
            <div style="text-align: center; margin-top: 20px; color: #666; font-size: 12px;">
                <p>© {{ CURRENT_YEAR }} ClinicHub. All rights reserved.</p>
                <p>
                    <a href="https://clinichub.com/privacy" style="color: #666; text-decoration: none;">Privacy Policy</a> | 
                    <a href="https://clinichub.com/terms" style="color: #666; text-decoration: none;">Terms of Service</a>
                </p>
            </div>
        </div>
    </body>
    </html>
    """
    html = Template(template).render(username=username)
    return send_email(email, "Welcome to ClinicHub!", html)

def send_referral_notification(email, referral_data):
    """Send referral notification with professional template"""
    template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>New Referral Created</title>
    </head>
    <body style="margin: 0; padding: 0; font-family: Arial, sans-serif; line-height: 1.6;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="text-align: center; margin-bottom: 30px;">
                <img src="https://clinichub.com/assets/custom/images/logo.png" alt="ClinicHub Logo" style="max-width: 200px;">
            </div>
            <div style="background-color: #ffffff; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <h2 style="color: #333; margin-bottom: 20px;">New Referral Created</h2>
                <p>Hello {{ referral_data.affiliate_name }},</p>
                <p>A new referral has been created for {{ referral_data.name }} for {{ referral_data.treatment_name }}.</p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="https://clinichub.com/referrals" 
                       style="background-color: #0891b2; color: white; padding: 12px 30px; 
                              text-decoration: none; border-radius: 5px; font-weight: bold;">
                        View Referral Details
                    </a>
                </div>
            </div>
            <div style="text-align: center; margin-top: 20px; color: #666; font-size: 12px;">
                <p>© {{ CURRENT_YEAR }} ClinicHub. All rights reserved.</p>
                <p>
                    <a href="https://clinichub.com/privacy" style="color: #666; text-decoration: none;">Privacy Policy</a> | 
                    <a href="https://clinichub.com/terms" style="color: #666; text-decoration: none;">Terms of Service</a>
                </p>
            </div>
        </div>
    </body>
    </html>
    """
    html = Template(template).render(referral_data=referral_data)
    return send_email(email, "New Referral Created - ClinicHub", html)

def send_approval_notification(email, username):
    """Send approval notification with professional template"""
    template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Account Approved - ClinicHub</title>
    </head>
    <body style="margin: 0; padding: 0; font-family: Arial, sans-serif; line-height: 1.6;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="text-align: center; margin-bottom: 30px;">
                <img src="https://clinichub.com/assets/custom/images/logo.png" alt="ClinicHub Logo" style="max-width: 200px;">
            </div>
            <div style="background-color: #ffffff; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <h2 style="color: #333; margin-bottom: 20px;">Account Approved!</h2>
                <p>Hello {{ username }},</p>
                <p>Great news! Your ClinicHub account has been approved. You can now start referring patients.</p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="https://clinichub.com/login" 
                       style="background-color: #0891b2; color: white; padding: 12px 30px; 
                              text-decoration: none; border-radius: 5px; font-weight: bold;">
                        Login to Your Account
                    </a>
                </div>
            </div>
            <div style="text-align: center; margin-top: 20px; color: #666; font-size: 12px;">
                <p>© {{ CURRENT_YEAR }} ClinicHub. All rights reserved.</p>
                <p>
                    <a href="https://clinichub.com/privacy" style="color: #666; text-decoration: none;">Privacy Policy</a> | 
                    <a href="https://clinichub.com/terms" style="color: #666; text-decoration: none;">Terms of Service</a>
                </p>
            </div>
        </div>
    </body>
    </html>
    """
    html = Template(template).render(username=username)
    return send_email(email, "Your ClinicHub Account is Approved!", html)
