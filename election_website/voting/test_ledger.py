"""Tests for the bridge between the website and the blockchain ledger."""
import json
import tempfile
from unittest import mock

from django.test import override_settings
from django.urls import reverse

from . import ledger
from .models import LedgerReceipt, Votes
from .testing import BaseTestCase, PASSWORD, make_candidate, make_position, make_voter


class LedgerSigningTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.user = make_voter()
        self.position = make_position('President')
        self.c1 = make_candidate(self.position, 'Ali')

    def test_ballot_is_signed_and_verifiable(self):
        vote = ledger.signed_ballot(self.user.voter, [(self.position, [self.c1])])
        self.assertEqual(vote['body']['ballot'], {str(self.position.id): [str(self.c1.id)]})
        self.assertTrue(ledger.signature_ok(vote))

    def test_changed_ballot_fails_signature(self):
        vote = ledger.signed_ballot(self.user.voter, [(self.position, [self.c1])])
        vote['body']['ballot'][str(self.position.id)] = ['999']
        self.assertFalse(ledger.signature_ok(vote))

    def test_key_is_created_once(self):
        first = ledger.key_for(self.user.voter)
        self.assertEqual(first.pk, ledger.key_for(self.user.voter).pk)

    def test_export_writes_public_keys_only(self):
        folder = tempfile.mkdtemp()
        with override_settings(LEDGER_DIR=folder):
            ledger.key_for(self.user.voter)
            self.assertTrue(ledger.export_register())
        with open(folder + '/voters.json') as f:
            voters = json.load(f)
        with open(folder + '/election.json') as f:
            election = json.load(f)
        self.assertEqual(set(voters[0]), {'name', 'public'})
        self.assertIn(str(self.position.id), election['positions'])


class LedgerAuditTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.user = make_voter()
        self.position = make_position('President')
        self.c1 = make_candidate(self.position, 'Ali')
        vote = ledger.signed_ballot(self.user.voter, [(self.position, [self.c1])])
        genesis = {"index": 0, "prev_hash": "0" * 64, "timestamp": 0, "votes": []}
        genesis["hash"] = ledger.hash_block(genesis)
        block = {"index": 1, "prev_hash": genesis["hash"], "timestamp": 1.0, "votes": [vote]}
        block["hash"] = ledger.hash_block(block)
        self.chain = [genesis, block]
        self.registered = {ledger.key_for(self.user.voter).public_key}

    def test_valid_chain(self):
        self.assertIsNone(ledger.chain_problem(self.chain, self.registered, {}))
        self.assertEqual(ledger.tally(self.chain), {str(self.c1.id): 1})

    def test_tampered_vote_is_detected(self):
        self.chain[1]['votes'][0]['body']['ballot'][str(self.position.id)] = ['999']
        self.assertIn('hash does not match', ledger.chain_problem(self.chain, self.registered, {}))

    def test_rehashed_tampering_is_detected_by_signature(self):
        self.chain[1]['votes'][0]['body']['ballot'][str(self.position.id)] = ['999']
        copy = {k: v for k, v in self.chain[1].items() if k != 'hash'}
        self.chain[1]['hash'] = ledger.hash_block(copy)
        self.assertIn('bad signature', ledger.chain_problem(self.chain, self.registered, {}))

    def test_unregistered_voter_is_detected(self):
        self.assertIn('unregistered', ledger.chain_problem(self.chain, set(), {}))


class SubmitWithLedgerTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        mock.patch.stopall()  # use the real record_ballot, with the network mocked below
        self.user = make_voter()
        self.position = make_position('President')
        self.c1 = make_candidate(self.position, 'Ali')
        self.client.login(username=self.user.email, password=PASSWORD)

    def submit(self):
        return self.client.post(reverse('submit_ballot'), {'president': str(self.c1.id)})

    def test_vote_saved_with_receipt_when_a_node_accepts(self):
        answers = [('interior', 'accepted', 4), ('commission', 'rejected', 'already voted'), ('delegates', 'down', None)]
        with mock.patch('voting.ledger._post', side_effect=answers):
            self.submit()
        self.assertEqual(Votes.objects.count(), 1)
        self.assertEqual(LedgerReceipt.objects.get().block, 4)

    def test_nothing_saved_when_every_node_is_down(self):
        with mock.patch('voting.ledger._post', side_effect=lambda name, url, vote: (name, 'down', None)):
            response = self.submit()
        self.assertEqual(Votes.objects.count(), 0)
        self.assertRedirects(response, reverse('show_ballot'), fetch_redirect_response=False)

    def test_ledger_already_holds_ballot(self):
        with mock.patch('voting.ledger._post', side_effect=lambda name, url, vote: (name, 'rejected', 'already voted')):
            self.submit()
        self.assertEqual(Votes.objects.count(), 0)
