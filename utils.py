import string
import random
from models import Affiliate

def generate_unique_slug(length=8):
    characters = string.ascii_letters + string.digits
    while True:
        slug = ''.join(random.choices(characters, k=length))
        if not Affiliate.query.filter_by(slug=slug).first():
            return slug

def format_phone_number(phone):
    # Remove any non-digit characters
    clean_phone = ''.join(filter(str.isdigit, phone))
    if not clean_phone.startswith('+'):
        clean_phone = '+' + clean_phone
    return clean_phone
