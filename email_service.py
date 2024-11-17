import mandrill
from flask import current_app, url_for

def get_mandrill_client():
    api_key = current_app.config['MANDRILL_API_KEY']
    return mandrill.Mandrill(api_key)

def send_verification_email(email, token):
    client = get_mandrill_client()
    
    verification_url = url_for('auth.verify_email', token=token, _external=True)
    
    template_content = [
        {
            'name': 'verification_url',
            'content': verification_url
        }
    ]
    
    message = {
        'from_email': 'noreply@clinichub.com',
        'from_name': 'ClinicHub',
        'subject': 'Verify your email',
        'to': [{'email': email}],
        'html': f'''
            <p>Please click the following link to verify your email:</p>
            <p><a href="{verification_url}">{verification_url}</a></p>
            <p>If you did not register for ClinicHub, please ignore this email.</p>
        '''
    }
    
    try:
        client.messages.send(message=message)
    except mandrill.Error as e:
        print(f'A mandrill error occurred: {e.__class__} - {e}')
        raise

def send_approval_notification(email):
    client = get_mandrill_client()
    
    message = {
        'from_email': 'noreply@clinichub.com',
        'from_name': 'ClinicHub',
        'subject': 'Account Approved',
        'to': [{'email': email}],
        'html': '''
            <p>Your affiliate account has been approved!</p>
            <p>You can now log in and start referring patients.</p>
        '''
    }
    
    try:
        client.messages.send(message=message)
    except mandrill.Error as e:
        print(f'A mandrill error occurred: {e.__class__} - {e}')
        raise
