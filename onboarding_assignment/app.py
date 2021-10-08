from base64 import b64encode
import csv
import httpx
import os
import re
from dotenv import load_dotenv
from typing import Dict

load_dotenv()

api_user: bytes = bytes(os.getenv("API_USER"), "utf-8")
api_password: bytes = bytes(os.getenv("API_PASSWORD"), "utf-8")
base_url: str = "https://sandbox.billogram.com/api/v2"

headers: Dict = {"Authorization": b"Basic " + b64encode(api_user + b":" + api_password)}

vat = 25

class InvoicingError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)

class ServiceMalfunctioningError(InvoicingError):
    "The Billogram API service seems to be malfunctioning"
    pass

class NotAuthorizedError(InvoicingError):
    "The user does not have authorization to perform the requested operation"
    pass

class InvalidAuthenticationError(InvoicingError):
    "The user/key combination could not be authenticated"
    pass

class RequestFormError(InvoicingError):
    "Errors caused by malformed requests"
    pass

class PermissionDeniedError(InvoicingError):
    "No permission to perform the requested operation"
    pass

class ObjectNotFoundError(InvoicingError):
    "No object by the requested ID exists"
    pass

def email_is_valid(email: str) -> bool:
    regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    return re.fullmatch(regex, email) is not None

def phone_is_valid(phone_number: str) -> bool:
    regex = r'\b^0\d{8,10}\b'
    return re.fullmatch(regex, phone_number) is not None
    

def check_response(response: httpx.Response) -> Dict:
    if not response.status_code == 200:
        expect_content_type = 'application/json'
        data = response.json()
        status = data["status"]

        if response.status_code in range(500, 600):
            if response.headers["content-type"] == expect_content_type:
                raise ServiceMalfunctioningError(
                    'Billogram API reported a server error: {} - {}'.format(
                        data.get('status'),
                        data.get('data').get('message')
                    )
                )

            raise ServiceMalfunctioningError(
                'Billogram API reported a server error'
            )
        
        if not status:
            raise ServiceMalfunctioningError(
                "Response data missing status field"
            )
        
        if not "data" in data:
            raise ServiceMalfunctioningError(
                "Response data missing data field"
            )
        
        if response.status_code == 403:
            # bad auth
            if status == 'PERMISSION_DENIED':
                raise NotAuthorizedError(
                    'Not allowed to perform the requested operation'
                )
            elif status == 'INVALID_AUTH':
                raise InvalidAuthenticationError(
                    'The user/key combination is wrong, check the credentials \
                     used and possibly generate a new set'
                )
            elif status == 'MISSING_AUTH':
                raise RequestFormError('No authentication data was given')
            else:
                raise PermissionDeniedError(
                    'Permission denied, status={}'.format(
                        status
                    )
                )
            
        if response.status_code == 404:
            #  not found
            if data.get('status') == 'NOT_AVAILABLE_YET':
                raise ObjectNotFoundError('Object not available yet')
            raise ObjectNotFoundError('Object not found')
    
    return response.json()["data"]

def create_customer(client: httpx.Client, invoice: Dict) -> Dict:
    # Check if customer already exists
    response = client.get(base_url + "/customer" + "/" + invoice["customer_number"], headers=headers)

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
            "contact": {"email": invoice["email"], "phone": invoice["phone_number"]},
            "address": {
                "street_address": invoice["street_address"],
                "zipcode": invoice["postal_code"],
                "city": invoice["city"],
            },
        }

        response = httpx.post(base_url + "/customer", headers=headers, json=customer_body)

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
    price: float = float(invoice["article_price"]) / (1 + vat / 100)

    billogram_body = {
        "invoice_no": invoice["invoice_number"],
        "customer": {"customer_no": invoice["customer_number"]},
        "items": [{"title": invoice["article_name"], "price": price, "vat": vat, "count": 1}],
        "on_success": {
            "command": "send",
            "method": send_method,
        },
    }

    response = httpx.post(base_url + "/billogram", headers=headers, json=billogram_body)

    if response.status_code == 200:
        response_body = response.json()
        billogram = response_body["data"]
        print("Billogram created and sent with id: " + billogram["id"])
        return billogram
    else:
        print(response.text)
        exit()


def read_file() -> Dict:
    with open("invoices.csv", newline="") as csvfile:
        invoices = csv.DictReader(csvfile)
    return invoices


def main():
    invoices = read_file()
    for invoice in invoices:
        customer = create_customer(invoice)
        billogram = create_billogram(invoice)
    return


if __name__ == "__main__":
    main()
