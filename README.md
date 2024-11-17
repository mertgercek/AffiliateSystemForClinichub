# ClinicHub - Affiliate Management System

## Overview
A clinic affiliate management system providing customized landing pages, referral tracking, and comprehensive administrative workflows. The system features user authentication, role-based access control, data-driven analytics dashboards, and API integration capabilities.

## Key Features
- User authentication with email verification
- Role-based access control (Admin/Affiliate)
- Customized landing pages per affiliate
- Treatment management system
- Referral tracking with data masking
- Commission calculation system
- Analytics dashboard with real-time metrics
- REST API with API key management
- Email notification system with templates
- Automated affiliate approval workflow
- Country-based analytics and tracking

## Requirements
- Python 3.11+
- PostgreSQL database
- Mandrill API key for email services
- Redis (optional, for caching)

## Installation
```bash
# Clone the repository
git clone [repository-url]
cd clinichub

# Install dependencies
pip install -r requirements.txt
```

## Environment Variables
Create a .env file with:
```
DATABASE_URL=postgresql://[user]:[password]@[host]:[port]/[dbname]
FLASK_SECRET_KEY=[your-secret-key]
MANDRILL_API_KEY=[your-mandrill-api-key]
```

## Database Setup
The system automatically creates necessary tables on first run. Default admin credentials:
- Email: admin@clinichub.com
- Password: admin123

## Running the Application
```bash
python app.py
```
Server will start on http://localhost:5000

## Server Requirements
### Minimum Specifications
- RAM: 2GB
- CPU: 1 vCPU/Core
- Storage: 20GB SSD
- OS: Ubuntu 20.04 LTS or newer

### Recommended Specifications
- RAM: 4GB
- CPU: 2 vCPU/Cores
- Storage: 40GB SSD
- OS: Ubuntu 22.04 LTS

## Production Deployment
### Domain Setup
1. Point your domain's A record to your server's IP address
2. Install and configure Nginx:
```bash
sudo apt update
sudo apt install nginx
```

3. Create Nginx configuration (/etc/nginx/sites-available/clinichub):
```nginx
server {
    server_name yourdomain.com;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

4. Enable the site and install SSL:
```bash
sudo ln -s /etc/nginx/sites-available/clinichub /etc/nginx/sites-enabled/
sudo certbot --nginx -d yourdomain.com
```

### Subdomain Setup
1. Configure DNS:
   - Add an A record for your subdomain (e.g., app.yourdomain.com) pointing to your server's IP address

2. Create Nginx configuration for subdomain (/etc/nginx/sites-available/clinichub):
```nginx
server {
    server_name app.yourdomain.com;     # Replace with your subdomain
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Enable SSL configuration
    listen 443 ssl;
    ssl_certificate /etc/letsencrypt/live/app.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/app.yourdomain.com/privkey.pem;
    
    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    
    # Enable HSTS
    add_header Strict-Transport-Security "max-age=31536000" always;
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name app.yourdomain.com;
    return 301 https://$server_name$request_uri;
}
```

3. Enable SSL for subdomain:
```bash
sudo certbot --nginx -d app.yourdomain.com
```

4. Test Nginx configuration:
```bash
sudo nginx -t
sudo systemctl reload nginx
```

Note: Replace 'app.yourdomain.com' with your actual subdomain throughout the configuration.

5. Update environment variables in /etc/environment:
```bash
FLASK_SECRET_KEY=your_secret_key
DATABASE_URL=postgresql://user:password@localhost:5432/clinichub
MANDRILL_API_KEY=your_mandrill_key
```

6. Setup systemd service (/etc/systemd/system/clinichub.service):
```ini
[Unit]
Description=ClinicHub
After=network.target

[Service]
User=clinichub
WorkingDirectory=/opt/clinichub
Environment="PATH=/opt/clinichub/venv/bin"
ExecStart=/opt/clinichub/venv/bin/gunicorn -w 4 -b 127.0.0.1:5000 app:app

[Install]
WantedBy=multi-user.target
```

7. Start and enable the service:
```bash
sudo systemctl start clinichub
sudo systemctl enable clinichub
```

## System Architecture
### Models
- User: Authentication and role management
- Affiliate: Manages affiliate profiles and earnings
- Treatment/TreatmentGroup: Organizes treatments and commission structures
- Referral: Tracks patient referrals and statuses
- APIKey: Manages API authentication

### Workflow
1. Affiliates register and get verified
2. Each affiliate receives a custom landing page
3. Patients submit referrals through landing pages
4. Admins manage treatments and approve referrals
5. System automatically calculates commissions on completion

## API Documentation
Detailed API documentation available at /admin/api-docs when logged in as admin.

### Authentication
All API requests require X-API-Key header:
```
X-API-Key: your-api-key
```

### Key Endpoints
- GET /api/v1/profile
- GET /api/v1/referrals
- POST /api/v1/referrals
- PUT /api/v1/referrals/{id}/status
- GET /api/v1/treatments
- GET /api/v1/stats

## Security Features
- Email verification required
- Data masking for sensitive information
- Role-based access control
- API key management
- Password hashing

## License
MIT License

## Support
For support and inquiries, please contact:
mert.gercek@clinichub.com
