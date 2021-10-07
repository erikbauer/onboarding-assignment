import unittest
from onboarding_assignment.app import email_is_valid
from onboarding_assignment.app import phone_is_valid

class TestValidation(unittest.TestCase):
    def test_valid_email(self):
        test_data= "test@test.com"

        self.assertTrue(email_is_valid(test_data))

    def test_invalid_email(self):
        test_data = "test.org"

        self.assertFalse(email_is_valid(test_data))

    def test_valid_phone(self):
        test_data= "0721459613"

        self.assertTrue(phone_is_valid(test_data))

    def test_invalid_phone(self):
        test_data = "281934"

        self.assertFalse(phone_is_valid(test_data))