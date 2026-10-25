import json

from odoo.tests import HttpCase, tagged
from odoo.tests.common import new_test_user


@tagged('post_install', '-at_install')
class TestClientPortal(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.login = 'client-portal-19@example.test'
        cls.password = 'client-portal-19-test'
        cls.user = new_test_user(
            cls.env, login=cls.login, password=cls.password,
            groups='base.group_portal', company_id=cls.env.company.id,
        )
        cls.user.partner_id.phone = False

    def test_home_renders_for_customer_without_phone(self):
        self.authenticate(self.login, self.password)
        response = self.url_open('/my/home')
        self.assertEqual(response.status_code, 200)
        self.assertIn('dc-home-profile', response.text)
        self.assertIn('Mi cuenta', response.text)

    def test_counters_contain_only_numeric_values(self):
        self.authenticate(self.login, self.password)
        response = self.url_open('/my/counters', data=json.dumps({
            'jsonrpc': '2.0', 'method': 'call', 'id': 1,
            'params': {'counters': ['quotation_count', 'order_count', 'invoice_count']},
        }), headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 200)
        result = response.json()['result']
        self.assertIsInstance(result, dict)
        self.assertNotIn('dreyes_client_partner', result)
        self.assertTrue(all(isinstance(value, (int, float)) for value in result.values()))
