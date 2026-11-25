"""The new election portal: pages plus a small JSON API on top of the existing backend.

It reuses the website's models, accounts and rate limiting, and the blockchain
bridge in voting/ledger.py. The classic AdminLTE pages keep working next to it.
"""
import datetime
import json
from concurrent.futures import ThreadPoolExecutor

import requests
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.core.cache import cache
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from account import throttle
from voting import ledger, services
from voting.models import Candidate, LedgerReceipt, Position, Voter

ADMIN, VOTER = '1', '2'
NODE_LABELS = {
    'interior': 'Ministry of Interior',
    'commission': 'Supervisory Commission',
    'delegates': "Candidates' Delegates",
}
PALETTE = ['#2563EB', '#DB2777', '#059669', '#D97706', '#7C3AED', '#0891B2', '#DC2626', '#4F46E5', '#65A30D']


# Helpers

def election_title():
    try:
        with open(settings.ELECTION_TITLE_PATH) as f:
            return f.read().strip() or "Election"
    except OSError:
        return "Election"


def role(user):
    if not user.is_authenticated:
        return None
    return user.user_type


def initials(name):
    parts = [p for p in name.split() if p]
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else '')).upper() if parts else '?'


def candidate_dict(c, with_bio=False):
    d = {'id': c.id, 'name': c.fullname, 'initials': initials(c.fullname),
         'color': PALETTE[c.id % len(PALETTE)], 'photo': c.photo.url if c.photo else ''}
    if with_bio:
        d['bio'] = c.bio
    return d


def ballot_definition():
    return [{
        'id': p.id, 'name': p.name, 'max_vote': p.max_vote,
        'candidates': [candidate_dict(c, with_bio=True) for c in p.candidate_set.all()],
    } for p in Position.objects.order_by('priority', 'id').prefetch_related('candidate_set')]


def cached_audit():
    """The audit downloads three chains; share one result between quick refreshes."""
    report = cache.get('portal-audit')
    if report is None:
        report = ledger.audit()
        cache.set('portal-audit', report, 1)
    return report


def page_context(request, page, **extra):
    ctx = {'page': page, 'title': election_title(), 'role': role(request.user), 'user': request.user}
    ctx.update(extra)
    return ctx


def json_error(message, status=400):
    return JsonResponse({'ok': False, 'message': message}, status=status)


def voter_home(user):
    return reverse('portal_receipt') if user.voter.voted else reverse('portal_vote')


# Pages

def home(request):
    return render(request, 'portal/home.html', page_context(request, 'home'))


def signin(request):
    if request.user.is_authenticated:
        return redirect(reverse('portal_control') if role(request.user) == ADMIN else voter_home(request.user))
    error = None
    email = ''
    if request.method == 'POST':
        email = (request.POST.get('email') or '').strip().lower()
        password = request.POST.get('password') or ''
        key = "login-fail:%s:%s" % (throttle.client_ip(request), email)
        if throttle.is_limited(key, settings.LOGIN_MAX_ATTEMPTS):
            error = "Too many failed attempts. Please wait a few minutes and try again."
        else:
            user = authenticate(request, username=email, password=password)
            if user is not None and user.user_type in (ADMIN, VOTER):
                throttle.reset(key)
                login(request, user)
                if user.user_type == ADMIN:
                    return redirect('portal_control')
                return redirect(voter_home(user))
            throttle.hit(key, settings.LOGIN_LOCKOUT_SECONDS)
            error = "That email and password do not match an account."
    return render(request, 'portal/signin.html', page_context(request, 'signin', error=error, email=email))


@require_POST
def signout(request):
    logout(request)
    return redirect('portal_home')


def vote(request):
    if role(request.user) != VOTER:
        return redirect('portal_signin') if role(request.user) is None else redirect('portal_control')
    voter = request.user.voter
    if voter.voted:
        return redirect('portal_receipt')
    if not (voter.verified and voter.otp is not None):
        if settings.SEND_OTP:
            return redirect('voterVerify')  # classic SMS verification page
        from voting.views import bypass_otp
        bypass_otp(voter)
    return render(request, 'portal/vote.html', page_context(
        request, 'vote', ballot=ballot_definition(), voter_name=request.user.first_name or str(request.user)))


def receipt(request):
    if role(request.user) != VOTER:
        return redirect('portal_signin') if role(request.user) is None else redirect('portal_control')
    voter = request.user.voter
    if not voter.voted:
        return redirect('portal_vote')
    rec = LedgerReceipt.objects.filter(voter=voter).first()
    key = getattr(voter, 'ledgerkey', None)
    choices = [{'position': v.position.name, 'candidate': candidate_dict(v.candidate)}
               for v in voter.votes_set.select_related('position', 'candidate').order_by('position__priority', 'candidate_id')]
    data = {
        'block': rec.block if rec else None,
        'answers': json.loads(rec.answers) if rec else [],
        'time': rec.created_at.isoformat() if rec else None,
        'public_key': key.public_key if key else '',
        'choices': choices,
        'labels': NODE_LABELS,
    }
    return render(request, 'portal/receipt.html', page_context(request, 'receipt', receipt=data,
                                                               voter_name=request.user.first_name or str(request.user)))


def results(request):
    return render(request, 'portal/results.html', page_context(request, 'results'))


def explorer(request):
    return render(request, 'portal/explorer.html', page_context(request, 'explorer'))


def control(request):
    if role(request.user) != ADMIN:
        return redirect('portal_signin') if role(request.user) is None else redirect(voter_home(request.user))
    return render(request, 'portal/control.html', page_context(request, 'control', labels=NODE_LABELS))


# API

@require_GET
def api_overview(request):
    report = cached_audit()
    official = report['official']
    website = dict(Candidate.objects.annotate(n=Count('votes')).values_list('id', 'n'))
    positions = []
    all_match = official is not None
    for p in Position.objects.order_by('priority', 'id').prefetch_related('candidate_set'):
        cands = []
        for c in p.candidate_set.all():
            d = candidate_dict(c)
            d['ledger'] = official.get(str(c.id), 0) if official is not None else None
            d['website'] = website.get(c.id, 0)
            all_match = all_match and d['ledger'] == d['website']
            cands.append(d)
        positions.append({'id': p.id, 'name': p.name, 'max_vote': p.max_vote, 'candidates': cands})

    nodes = [dict(n, label=NODE_LABELS.get(n['name'], n['name'])) for n in report['nodes']]
    ballots = sum(len(b['votes']) for b in report['blocks'])
    data = {
        'title': election_title(),
        'time': datetime.datetime.now().strftime('%H:%M:%S'),
        'nodes': nodes,
        'majority': report['majority'],
        'confirmed': report['majority'] is not None,
        'db_matches': all_match,
        'stats': {
            'voters': Voter.objects.count(),
            'voted_website': Voter.objects.filter(voted=True).count(),
            'ballots_ledger': ballots,
            'blocks': len(report['blocks']),
            'valid_nodes': sum(1 for n in nodes if n['status'] == 'VALID'),
        },
        'positions': positions,
    }
    return JsonResponse(data)


@require_GET
def api_chain(request):
    report = cached_audit()
    names = {str(c.id): c.fullname for c in Candidate.objects.all()}
    positions = {str(p.id): p.name for p in Position.objects.all()}
    blocks = []
    for b in report['blocks']:
        votes = []
        for v in b['votes']:
            body = v['body']
            choices = [{'position': positions.get(pid, 'Position ' + pid), 'candidates': [names.get(c, 'Candidate ' + c) for c in cids]}
                       for pid, cids in body.get('ballot', {}).items()]
            if 'candidate' in body:
                choices.append({'position': 'Vote', 'candidates': [body['candidate']]})
            votes.append({'voter': body['voter'], 'signature': v['signature'], 'choices': choices})
        blocks.append({'index': b['index'], 'timestamp': b['timestamp'], 'hash': b['hash'],
                       'prev_hash': b['prev_hash'], 'votes': votes})
    return JsonResponse({'blocks': blocks, 'majority': report['majority']})


@require_POST
def api_vote(request):
    if role(request.user) != VOTER:
        return json_error("Please sign in as a voter.", 403)
    try:
        payload = json.loads(request.body or b'{}')
        choice = payload.get('ballot') or {}
        assert isinstance(choice, dict)
    except (ValueError, AssertionError):
        return json_error("The ballot could not be read.")

    selections = []
    for p in Position.objects.order_by('priority', 'id').prefetch_related('candidate_set'):
        picked = choice.get(str(p.id)) or []
        if not isinstance(picked, list):
            return json_error("The ballot could not be read.")
        if not picked:
            continue
        by_id = {str(c.id): c for c in p.candidate_set.all()}
        picked = [str(x) for x in picked]
        if len(set(picked)) != len(picked) or len(picked) > p.max_vote:
            return json_error("You can choose up to %d for %s." % (p.max_vote, p.name))
        if any(x not in by_id for x in picked):
            return json_error("One of the choices is not a candidate for %s." % p.name)
        selections.append((p, [by_id[x] for x in picked]))

    result = services.cast_ballot(request.user.voter, selections)
    cache.delete('portal-audit')
    status = 200 if result.ok else 409
    return JsonResponse({'ok': result.ok, 'message': result.message, 'block': result.block,
                         'answers': result.answers, 'labels': NODE_LABELS}, status=status)


@require_GET
def api_verify(request):
    """Look for this voter's signed ballot in every node's copy of the chain."""
    if role(request.user) != VOTER:
        return json_error("Please sign in as a voter.", 403)
    key = getattr(request.user.voter, 'ledgerkey', None)
    if key is None:
        return json_error("No ballot has been signed yet.", 404)
    registered = set(ledger.LedgerKey.objects.values_list('public_key', flat=True))

    def check(item):
        name, url = item
        try:
            chain = requests.get(url + '/chain', timeout=ledger.READ_TIMEOUT).json()
        except (requests.RequestException, ValueError):
            return {'name': name, 'label': NODE_LABELS.get(name, name), 'status': 'down'}
        problem = ledger.chain_problem(chain, registered, {})
        for block in chain:
            for v in block['votes']:
                if v['body'].get('voter') == key.public_key:
                    return {'name': name, 'label': NODE_LABELS.get(name, name), 'block': block['index'],
                            'status': 'verified' if problem is None and ledger.signature_ok(v) else 'tampered',
                            'reason': problem}
        return {'name': name, 'label': NODE_LABELS.get(name, name), 'status': 'missing'}

    with ThreadPoolExecutor(len(settings.LEDGER_NODES)) as pool:
        nodes = list(pool.map(check, settings.LEDGER_NODES.items()))
    return JsonResponse({'ok': True, 'nodes': nodes})


@require_POST
def api_tamper(request):
    """Demonstration only: ask one node to change a stored ballot in its own copy."""
    if role(request.user) != ADMIN:
        return json_error("Administrators only.", 403)
    try:
        payload = json.loads(request.body or b'{}')
    except ValueError:
        return json_error("Bad request.")
    node = payload.get('node')
    url = settings.LEDGER_NODES.get(node)
    if url is None:
        return json_error("Unknown node.")
    params = {'rehash': '1'} if payload.get('rehash') else {}
    try:
        requests.post(url + '/tamper', params=params, timeout=(0.5, 3))
    except requests.RequestException:
        return json_error("The %s node is not reachable." % NODE_LABELS.get(node, node), 503)
    cache.delete('portal-audit')
    return JsonResponse({'ok': True})
