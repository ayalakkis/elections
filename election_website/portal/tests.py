"""Tests for the new portal interface and its JSON API."""
import json
from unittest import mock

from django.core.cache import cache
from django.urls import reverse

from voting.models import LedgerReceipt, Votes
from voting.testing import BaseTestCase, PASSWORD, make_admin, make_candidate, make_position, make_voter

EMPTY_AUDIT = {'nodes': [{'name': 'interior', 'url': 'u', 'status': 'VALID', 'reason': 'ok', 'blocks': 1, 'ballots': 0, 'tip': 'abc'}],
               'majority': ['interior'], 'official': {}, 'blocks': []}


class PortalPageTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.audit = mock.patch('voting.ledger.audit', return_value=EMPTY_AUDIT)
        self.audit.start()
        self.addCleanup(self.audit.stop)

    def test_public_pages_open_without_login(self):
        for name in ('portal_home', 'portal_signin', 'portal_results', 'portal_explorer'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_private_pages_need_login(self):
        for name in ('portal_vote', 'portal_receipt', 'portal_control'):
            self.assertRedirects(self.client.get(reverse(name)), reverse('portal_signin'), fetch_redirect_response=False)

    def test_overview_api(self):
        make_candidate(make_position('President'), 'Ali')
        data = self.client.get(reverse('portal_api_overview')).json()
        self.assertTrue(data['confirmed'])
        self.assertEqual(data['positions'][0]['candidates'][0]['ledger'], 0)

    def test_signin_sends_each_role_home(self):
        voter = make_voter()
        response = self.client.post(reverse('portal_signin'), {'email': voter.email, 'password': PASSWORD})
        self.assertRedirects(response, reverse('portal_vote'), fetch_redirect_response=False)
        self.client.logout()
        admin = make_admin()
        response = self.client.post(reverse('portal_signin'), {'email': admin.email, 'password': PASSWORD})
        self.assertRedirects(response, reverse('portal_control'), fetch_redirect_response=False)

    def test_wrong_password_shows_error(self):
        make_voter()
        response = self.client.post(reverse('portal_signin'), {'email': 'voter@example.com', 'password': 'nope'})
        self.assertContains(response, 'do not match')

    def test_voter_cannot_open_control_room_or_tamper(self):
        voter = make_voter()
        self.client.login(username=voter.email, password=PASSWORD)
        self.assertEqual(self.client.get(reverse('portal_control')).status_code, 302)
        response = self.client.post(reverse('portal_api_tamper'), json.dumps({'node': 'interior'}), content_type='application/json')
        self.assertEqual(response.status_code, 403)


class PortalVoteTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        mock.patch.stopall()  # real record_ballot, network mocked per test
        self.voter = make_voter()
        self.president = make_position('President')
        self.council = make_position('Council', max_vote=2)
        self.a = make_candidate(self.president, 'Ali')
        self.b = make_candidate(self.council, 'Bea')
        self.c = make_candidate(self.council, 'Cal')
        self.client.login(username=self.voter.email, password=PASSWORD)

    def vote(self, ballot):
        return self.client.post(reverse('portal_api_vote'), json.dumps({'ballot': ballot}), content_type='application/json')

    def accept(self, name, url, vote):
        return name, 'accepted', 7

    def test_vote_is_recorded_with_receipt(self):
        with mock.patch('voting.ledger._post', side_effect=self.accept):
            response = self.vote({str(self.president.id): [str(self.a.id)], str(self.council.id): [str(self.b.id), str(self.c.id)]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['block'], 7)
        self.assertEqual(Votes.objects.count(), 3)
        self.assertEqual(LedgerReceipt.objects.get().block, 7)
        self.assertEqual(self.client.get(reverse('portal_vote')).status_code, 302)

    def test_too_many_choices_rejected(self):
        response = self.vote({str(self.president.id): [str(self.a.id), str(self.b.id)]})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Votes.objects.count(), 0)

    def test_candidate_from_another_position_rejected(self):
        response = self.vote({str(self.president.id): [str(self.b.id)]})
        self.assertEqual(response.status_code, 400)

    def test_empty_ballot_rejected(self):
        response = self.vote({})
        self.assertEqual(response.status_code, 409)

    def test_ledger_down_means_not_recorded(self):
        with mock.patch('voting.ledger._post', side_effect=lambda name, url, vote: (name, 'down', None)):
            response = self.vote({str(self.president.id): [str(self.a.id)]})
        self.assertEqual(response.status_code, 409)
        self.assertIn('not reachable', response.json()['message'])
        self.assertEqual(Votes.objects.count(), 0)
