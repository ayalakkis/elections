"""Admin pages for the blockchain ledger: audit, explorer and the tampering demo."""
import datetime

import requests
from django.conf import settings
from django.contrib import messages
from django.db.models import Count
from django.shortcuts import redirect, render, reverse
from django.views.decorators.http import require_POST

from account.decorators import admin_required
from voting import ledger
from voting.models import Candidate, Position, Voter


@admin_required
def ledger_audit(request):
    report = ledger.audit()
    website_counts = dict(Candidate.objects.annotate(n=Count('votes')).values_list('id', 'n'))
    official = report["official"]

    rows = []
    for position in Position.objects.order_by('priority', 'id').prefetch_related('candidate_set'):
        for candidate in position.candidate_set.all():
            on_ledger = official.get(str(candidate.id), 0) if official is not None else None
            on_website = website_counts.get(candidate.id, 0)
            rows.append({
                'position': position.name, 'candidate': candidate.fullname,
                'ledger': on_ledger, 'website': on_website,
                'match': on_ledger == on_website,
            })

    names = {str(c.id): c.fullname for c in Candidate.objects.all()}
    blocks = []
    for block in reversed(report["blocks"][-15:]):
        choices = []
        for vote in block["votes"]:
            for chosen in vote["body"].get("ballot", {}).values():
                choices += [names.get(c, "candidate " + c) for c in chosen]
            if "candidate" in vote["body"]:
                choices.append(vote["body"]["candidate"])
        blocks.append({
            'index': block["index"],
            'time': datetime.datetime.fromtimestamp(block["timestamp"]).strftime('%H:%M:%S') if block["timestamp"] else 'genesis',
            'hash': block["hash"], 'prev_hash': block["prev_hash"],
            'voters': [v["body"]["voter"][:12] for v in block["votes"]],
            'choices': choices,
        })

    context = {
        'page_title': 'Blockchain Audit',
        'nodes': report["nodes"],
        'majority': report["majority"],
        'rows': rows,
        'all_match': official is not None and all(r['match'] for r in rows),
        'blocks': blocks,
        'block_count': len(report["blocks"]),
        'voted_on_website': Voter.objects.filter(voted=True).count(),
        'ballots_on_ledger': sum(len(b["votes"]) for b in report["blocks"]),
    }
    return render(request, "admin/ledger.html", context)


@admin_required
@require_POST
def ledger_tamper(request):
    """Demonstration only: ask one node to change a stored ballot in its own copy."""
    node = request.POST.get('node')
    url = settings.LEDGER_NODES.get(node)
    if url is None:
        messages.error(request, "Unknown node")
        return redirect(reverse('ledgerAudit'))
    params = {'rehash': '1'} if request.POST.get('rehash') else {}
    try:
        requests.post(url + "/tamper", params=params, timeout=(0.5, 3))
        kind = "changed a ballot and recomputed every hash" if params else "changed a ballot"
        messages.warning(request, "Demonstration: the %s node %s in its own copy." % (node, kind))
    except requests.RequestException:
        messages.error(request, "The %s node is not reachable" % node)
    return redirect(reverse('ledgerAudit'))
