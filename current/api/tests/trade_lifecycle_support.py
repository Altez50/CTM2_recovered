"""Controlled concurrency and faults, available only to the test executor."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import goods_services
from api.main import app
from api.trade_access import TradeConnection


class InjectedPostingFailure(RuntimeError):
    pass


class FailAfterInventoryInsert:
    def __init__(self, connection):
        self.connection = connection

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, sql, params=()):
        result = self.connection.execute(sql, params)
        if sql.lstrip().startswith('INSERT INTO inventory_register'):
            raise InjectedPostingFailure('test failure after inventory insert')
        return result


def competing_issue_requests(first_id, second_id, headers):
    """Two HTTP clients/DB connections; first pauses while holding stock lock."""
    # Separate sessions prevent the sessions.last_activity UPDATE from becoming
    # an accidental shared row lock that would mask an inventory-lock defect.
    login_client = TestClient(app)
    try:
        response = login_client.post('/api/auth/login', json={'username': 'admin', 'password': 'admin'})
        assert response.status_code == 200, response.text
        second_headers = {'Authorization': 'Bearer '+response.json()['access_token']}
        assert second_headers['Authorization'] != headers['Authorization']
    finally:
        login_client.close()
    checked, release, second_attempted, second_finished = Event(), Event(), Event(), Event()
    authenticated = Barrier(2)
    connections = {}
    original = goods_services._inventory_balance
    original_admin = goods_services._require_admin

    def authenticated_start(user):
        original_admin(user)
        # Both *real* authentication dependencies (including their SQLite
        # writes/commits) finish before either business transaction starts.
        authenticated.wait(timeout=10)

    def execute(self, sql, params=()):
        if sql == 'UPDATE goods_issues SET id = id WHERE id = ?':
            ident = params[0]
            connections[ident] = self.connection
            if ident == second_id:
                assert checked.wait(10), 'first request did not reach stock check'
                second_attempted.set()
        return self.connection.execute(sql, params)

    def pause_after_balance(*args, **kwargs):
        result = original(*args, **kwargs)
        if not checked.is_set():
            checked.set()
            assert release.wait(10), 'concurrent posting did not resume'
        return result

    def post(ident, second=False):
        client = TestClient(app)
        try:
            return client.post(f'/api/goods/issues/{ident}/post?auto_schedule=false', headers=second_headers if second else headers).status_code
        finally:
            client.close()
            if second:
                second_finished.set()

    with patch.object(goods_services, '_inventory_balance', pause_after_balance), \
         patch.object(goods_services, '_require_admin', authenticated_start), \
         patch.object(TradeConnection, 'execute', execute, create=True):
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(post, first_id)
            second = pool.submit(post, second_id, True)
            try:
                assert checked.wait(10), 'first request did not reach stock check'
                assert second_attempted.wait(10), 'second authenticated request never attempted the business lock'
                assert connections[first_id] is not connections[second_id]
                assert not second_finished.wait(.1), 'second request bypassed the held transaction'
            finally:
                release.set()
            return first.result(timeout=10), second.result(timeout=10)
