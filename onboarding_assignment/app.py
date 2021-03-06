import csv
import logging
import os
import re
from base64 import b64encode
from pathlib import Path
from typing import Dict, Optional, TypedDict

import httpx
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
api_user_env: Optional[str] = os.getenv("API_USER")
if api_user_env is not None:
    API_USER: bytes = bytes(api_user_env, "utf-8")

api_password_env: Optional[str] = os.getenv("API_PASSWORD")
if api_password_env is not None:
    API_PASSWORD: bytes = bytes(api_password_env, "utf-8")

BASE_URL: str = "https://sandbox.billogram.com/api/v2"

HEADERS: Dict = {"Authorization": b"Basic " + b64encode(API_USER + b":" + API_PASSWORD)}


class ItemDict(TypedDict, total=False):
    vat: int
    count: int
    price: float
    title: str
    description: str


class InvoiceDict(TypedDict, total=False):
    customer_number: int
    invoice_number: int
    name: str
    street_address: str
    postal_code: str
    city: str
    email: str
    phone_number: str
    article_name: str
    article_price: float


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


class InvalidParameterError(InvoicingError):
    "Error caused by invalid parameter in field"
    pass


class InvalidContact(InvoicingError):
    "Contact field is not in a valid format"
    pass


def email_is_valid(email: str) -> bool:
    regex = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    return re.fullmatch(regex, email) is not None


def phone_is_valid(phone_number: str) -> bool:
    regex = r"\b0\d{8,10}\b"
    return re.fullmatch(regex, phone_number) is not None


def check_response(response: httpx.Response) -> None:
    if not response.status_code == 200:
        expect_content_type = "application/json"
        data = response.json()
        status = data["status"]

        if response.status_code in range(500, 600):
            if response.headers["content-type"] == expect_content_type:
                raise ServiceMalfunctioningError(
                    "Billogram API reported a server error: {} - {}".format(
                        data.get("status"), data.get("data").get("message")
                    )
                )

            raise ServiceMalfunctioningError("Billogram API reported a server error")

        if not status:
            raise ServiceMalfunctioningError("Response data missing status field")

        if not "data" in data:
            raise ServiceMalfunctioningError("Response data missing data field")

        if response.status_code == 400:
            if status == "INVALID_PARAMETER":
                raise InvalidParameterError(
                    "A field in the request has an invalid value, type or is out of range: {}".format(
                        data.get("data").get("message")
                    )
                )

        if response.status_code == 403:
            # bad auth
            if status == "PERMISSION_DENIED":
                raise NotAuthorizedError("Not allowed to perform the requested operation")
            elif status == "INVALID_AUTH":
                raise InvalidAuthenticationError(
                    "The user/key combination is wrong, check the credentials \
                     used and possibly generate a new set"
                )
            elif status == "MISSING_AUTH":
                raise RequestFormError("No authentication data was given")
            else:
                raise PermissionDeniedError("Permission denied, status={}".format(status))

        if response.status_code == 404:
            #  not found
            if data.get("status") == "NOT_AVAILABLE_YET":
                raise ObjectNotFoundError("Object not available yet")
            raise ObjectNotFoundError("Object not found")


def create_contact_field(invoice: InvoiceDict) -> Dict:
    email = ""
    if invoice["email"]:
        if email_is_valid(invoice["email"]):
            email = invoice["email"]
        else:
            raise InvalidContact("Invalid format of email: {}".format(invoice["email"]))
    phone = ""
    if invoice["phone_number"]:
        if phone_is_valid(invoice["phone_number"]):
            phone = invoice["phone_number"]
        else:
            raise InvalidContact("invalid format of phone number: {}".format(invoice["phone_number"]))
    return {"email": email, "phone": phone}


def create_address_field(invoice: InvoiceDict) -> Dict:
    return {
        "street_address": invoice["street_address"],
        "zipcode": invoice["postal_code"],
        "city": invoice["city"],
    }


def create_item_field(invoice: InvoiceDict) -> ItemDict:
    vat = 25
    count = 1
    item: ItemDict = {"vat": vat, "count": count}

    # Exclude VAT from article price
    price: float = float(invoice["article_price"]) / (1 + vat / 100)
    item["price"] = price

    title = invoice["article_name"]
    # The Billogram API only allows for titles with a max lenght of 40 characters
    # Make sure title is not too long. If it is, shorten it and put the whole name in the description
    if len(title) > 40:
        item["description"] = title
        item["title"] = title[:37] + "..."
    else:
        item["title"] = title

    return item


def send_method(invoice: InvoiceDict) -> str:
    # Determine send method
    if invoice["email"]:
        send_method = "Email"
    elif invoice["phone_number"]:
        send_method = "SMS"
    else:
        send_method = "Letter"

    return send_method


def create_customer(client: httpx.Client, invoice: InvoiceDict) -> None:
    """Creates a customer from an invoice, if it does not already exist"""
    # Check if customer already exists
    response = client.get(BASE_URL + "/customer" + "/" + str(invoice["customer_number"]), headers=HEADERS)

    try:
        check_response(response)
    except ObjectNotFoundError:
        # Customer not found. Create an object for a customer
        customer_body = {
            "customer_no": invoice["customer_number"],
            "name": invoice["name"],
            "contact": create_contact_field(invoice),
            "address": create_address_field(invoice),
        }

        response = client.post(BASE_URL + "/customer", headers=HEADERS, json=customer_body)

        check_response(response)

        response_body = response.json()
        customer = response_body["data"]
        logging.info("Created customer: " + str(customer["customer_no"]))


def create_billogram(client: httpx.Client, invoice: InvoiceDict) -> None:
    """Creates a billogram from an invoice"""
    billogram_body = {
        "invoice_no": invoice["invoice_number"],
        "customer": {"customer_no": invoice["customer_number"]},
        "items": [create_item_field(invoice)],
        "on_success": {
            "command": "send",
            "method": send_method(invoice),
        },
    }

    response = client.post(BASE_URL + "/billogram", headers=HEADERS, json=billogram_body)

    check_response(response)

    response_body = response.json()
    billogram = response_body["data"]
    logging.info("Billogram created and sent with id: " + billogram["id"])


def main():
    logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)

    invoices_path = Path("./data/invoices.csv")

    with open(invoices_path, newline="") as csvfile:
        invoices = csv.DictReader(csvfile)

        with httpx.Client() as client:
            for invoice in invoices:
                create_customer(client, invoice)
                create_billogram(client, invoice)
            return


if __name__ == "__main__":
    main()
