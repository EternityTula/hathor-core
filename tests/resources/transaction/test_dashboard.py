from twisted.internet.defer import inlineCallbacks

from hathor.transaction.resources import DashboardTransactionResource
from tests.resources.base_resource import StubSite, _BaseResourceTest


class DashboardTest(_BaseResourceTest._ResourceTest):
    def setUp(self):
        super().setUp()
        self.web = StubSite(DashboardTransactionResource(self.manager))

    @inlineCallbacks
    def test_get(self):
        tx_count = block_count = 6
        response = yield self.web.get("dashboard_tx", {b'block': block_count, b'tx': tx_count})
        data = response.json_value()

        self.assertLessEqual(len(data['transactions']), tx_count)
        self.assertLessEqual(len(data['blocks']), block_count)

    @inlineCallbacks
    def test_invalid_parameters(self):
        # wrong type block
        response = yield self.web.get("dashboard_tx", {b'block': 'a', b'tx': 6})
        data = response.json_value()
        self.assertFalse(data['success'])
        # missing block param
        response = yield self.web.get("dashboard_tx", {b'tx': 6})
        data = response.json_value()
        self.assertFalse(data['success'])

        # wrong type tx
        response = yield self.web.get("dashboard_tx", {b'block': '6', b'tx': 'a'})
        data = response.json_value()
        self.assertFalse(data['success'])
        # missing tx param
        response = yield self.web.get("dashboard_tx", {b'block': '6'})
        data = response.json_value()
        self.assertFalse(data['success'])
