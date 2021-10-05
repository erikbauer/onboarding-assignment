from base64 import b64encode
import csv
import httpx
import os
from dotenv import load_dotenv
from typing import Dict

load_dotenv()

api_user: str = os.getenv("API_USER")
api_password: str = os.getenv("API_PASSWORD")
base_url = "https://sandbox.billogram.com/api/v2"

headers = {"Authorization": b"Basic " + b64encode(api_user + b":" + api_password)}

vat = 25


class BillogramAPI:
    def __init__(self, api_user: str, api_password: str) -> None:
        self.basic_auth = (api_user, api_password)
        self.customers = None
        self.billograms = None


class RemoteObject(object):
    def __init__(self, api: BillogramAPI, url: str, id_field: str) -> None:
        self._api = api
        self._url = url
        self._id_field = id_field


class Address(object):
    def __init__(self, street_address: str, zipcode: str, city: str) -> None:
        self.street_address = street_address
        self.zipcode = zipcode
        self.city = city

    def get(self):
        return {
            "street_address": self.street_address,
            "zipcode": self.zipcode,
            "city": self.city,
        }


class Contact(object):
    def __init__(self, email: str = None, phone: str = None):
        self.email = email
        self.phone = phone

    def get(self):
        return {"email": self.email, "phone": self.phone}


class Item(object):
    def __init__(self, title: str, price: float, vat: int, count: int) -> None:
        super().__init__()
        self.title = title
        self.vat = vat
        self.price = price
        self.count = count

    def price_excluding_vat(self):
        return self.price / (1 + self.vat / 100)

    def get(self):
        return {"title": self.title, "price": self.price, "vat": self.vat, "count": self.count}


class Customer(RemoteObject):
    def __init__(self, name: str, contact: Contact, address: Address) -> None:
        super().__init__()
        self.name = name
        self.contact = contact
        self.address = address
        self.send_method = None

        # Determine send method
        if self.address.email:
            self.send_method = "Email"
        elif self.address.phone:
            self.send_method = "SMS"
        else:
            self.send_method = "Letter"

    def get_body(self):
        return {
            "customer_no": self.id_field,
            "name": self.name,
            "contact": self.contact.get(),
            "address": self.address.get(),
        }


class Billogram(RemoteObject):
    def __init__(self, customer: Customer) -> None:
        super().__init__()
        self.customer = customer


def create_customer(invoice: Dict) -> Dict:
    # Check if customer already exists
    response = httpx.get(base_url + "/customer" + "/" + invoice["customer_number"], headers=headers)

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
