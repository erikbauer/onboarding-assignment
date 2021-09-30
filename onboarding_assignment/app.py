import csv
import os
import httpx
from dotenv import load_dotenv
from base64 import b64encode, encode

from typing import Dict

load_dotenv()

api_user: bytes = bytes(os.getenv("API_USER"), encoding="utf8") 
api_password: bytes = bytes(os.getenv("API_PASSWORD"), encoding="utf8")
base_url = "https://sandbox.billogram.com/api/v2"

headers = {
    "Authorization": b"Basic " + b64encode(api_user + b":" + api_password)
}

vat: int = 25

def create_customer(invoice: Dict) -> Dict:
    # Check if customer already exists
    response = httpx.get(
        base_url + "/customer" + "/" + invoice["customer_number"],
        headers=headers
    )

    if response.status_code == 200:
        response_body = response.json()
        customer = response_body["data"]
        print("Found customer: " + str(customer["customer_no"]))
        return customer
    else: 
        # Customer not found. Create an object for a customer
        customer_body = {
            "customer_no": invoice["customer_number"],
            "name": invoice["name"],
            "contact": {
                "email": invoice["email"],
                "phone": invoice["phone_number"]
            },
            "address": {
                "street_address": invoice["street_address"],
                "zipcode": invoice["postal_code"],
                "city": invoice["city"]
            }
        }

        response = httpx.post(
            base_url + "/customer",
            headers=headers,
            json=customer_body
        )       

        if response.status_code == 200:
            response_body = response.json()
            customer = response_body["data"]
            print("Created customer: " + str(customer["customer_no"]))
            return customer
        else:
            print(response.text)
            exit

def create_billogram(invoice: Dict) -> Dict:
    # Determine send method
    if invoice["email"]:
        send_method = "Email"
    elif invoice["phone_number"]:
        send_method = "SMS"
    else:
        send_method = "Letter"

    # Exclude VAT from article price
    price: float = float(invoice["article_price"]) / (1 + vat/100)

    billogram_body = {
        "invoice_no": invoice["invoice_number"],
        "customer": {
            "customer_no": invoice["customer_number"]
        },
        "items": [{
            "title": invoice["article_name"],
            "price": price,
            "vat": vat,
            "count": 1
        }],
        "on_success": {
            "command": "send",
            "method": send_method,
        }
    }

    response = httpx.post(
        base_url + "/billogram",
        headers=headers,
        json=billogram_body
    )

    if response.status_code == 200:
        response_body = response.json()
        billogram = response_body["data"]
        print("Billogram created and sent with id: " + billogram["id"])
        return billogram
    else:
        print(response.text)
        exit()

def read_file() -> Dict:
    with open('invoices.csv', newline='') as csvfile:
        invoices = csv.DictReader(csvfile)
    
    return invoices
            
def main():
    invoices = read_file()
    for invoice in invoices:
        customer = create_customer(invoice)
        billogram = create_billogram(invoice)
    return