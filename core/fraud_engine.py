"""AI-powered fraud detection engine.

Analyzes insurance claims using multiple risk signals and returns a structured
risk assessment with a score (0-100), a risk level (low/medium/high/critical),
and human-readable reasons explaining each flag.

The engine uses a weighted multi-factor model:
  1. Amount-to-coverage ratio      — claims close to the coverage limit are riskier
  2. Claim frequency               — multiple claims in a short window is suspicious
  3. Policy age                    — claims on very new policies are a red flag
  4. Amount anomaly detection      — unusually round or very large amounts
  5. Incident-description analysis — vague or copy-paste descriptions score higher
  6. Duplicate description check   — same wording across claims signals fabrication
  7. Time-to-claim gap             — long delays between incident and claim filing
  8. User claim history pattern    — users with prior rejected claims score higher
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone


def _amount_ratio_score(amount_claimed, policy):
    """Score based on how close the claim is to the coverage limit."""
    coverage = policy.coverage_amount or Decimal('100000')
    ratio = (Decimal(str(amount_claimed)) / coverage) * 100
    if ratio > 80:
        return 25, f'Claim amount is {ratio:.0f}% of your coverage limit — unusually high.'
    elif ratio > 50:
        return 15, f'Claim amount is {ratio:.0f}% of coverage — on the higher side.'
    elif ratio > 30:
        return 5, f'Claim amount is {ratio:.0f}% of coverage — within normal range.'
    return 0, ''


def _frequency_score(user, claim_id=None):
    """Score based on how many claims the user filed recently."""
    recent = __import__('core.models', fromlist=['Claim']).Claim.objects.filter(
        user=user, submitted_at__gte=timezone.now() - timedelta(days=30)
    )
    if claim_id:
        recent = recent.exclude(id=claim_id)
    count = recent.count()
    if count >= 3:
        return 20, f'{count} claims filed in the past 30 days — high frequency.'
    elif count >= 2:
        return 10, f'{count} claims filed in the past 30 days — slightly elevated.'
    return 0, ''


def _policy_age_score(policy):
    """Score based on how new the policy is when the claim is filed."""
    if policy.start_date:
        age = (timezone.now().date() - policy.start_date).days
        if age < 7:
            return 20, f'Policy is only {age} days old — claim filed very early.'
        elif age < 30:
            return 15, f'Policy is {age} days old — claim filed within first month.'
        elif age < 90:
            return 5, f'Policy is {age} days old — relatively new.'
    return 0, ''


def _amount_anomaly_score(amount_claimed):
    """Score based on whether the amount is a suspicious round number or very large."""
    score = 0
    reasons = []
    amount = Decimal(str(amount_claimed))

    if amount > Decimal('100000'):
        score += 15
        reasons.append('Claim exceeds R 100,000 — high-value claim requires scrutiny.')
    elif amount > Decimal('50000'):
        score += 10
        reasons.append('Claim exceeds R 50,000 — elevated value.')

    if amount == amount.quantize(Decimal('1')):
        score += 8
        reasons.append('Amount is an exact round number — can indicate estimation rather than real loss.')

    return score, ' '.join(reasons) if reasons else ''


def _description_analysis(description):
    """Score the incident description for vagueness, length, and patterns."""
    if not description:
        return 15, 'No incident description provided — missing critical detail.'

    score = 0
    reasons = []
    text = description.strip()
    word_count = len(text.split())

    if word_count < 10:
        score += 15
        reasons.append(f'Description is very short ({word_count} words) — lacks sufficient detail.')
    elif word_count < 20:
        score += 8
        reasons.append(f'Description is brief ({word_count} words) — could use more detail.')

    vague_phrases = [
        'i don\'t know', 'not sure', 'something happened', 'stuff happened',
        'can\'t remember', 'dont remember', 'no idea', 'it just broke',
        'it just stopped', 'i lost it', 'stolen somehow', 'disappeared',
    ]
    lower = text.lower()
    for phrase in vague_phrases:
        if phrase in lower:
            score += 12
            reasons.append('Description contains vague language — specific details expected.')
            break

    if text == text.upper() and len(text) > 20:
        score += 5
        reasons.append('Description is in all caps — unusual formatting.')

    return score, ' '.join(reasons) if reasons else ''


def _duplicate_description_check(description, user, claim_id=None):
    """Check if the user has submitted another claim with the same description."""
    if not description or len(description.strip()) < 15:
        return 0, ''

    Claim = __import__('core.models', fromlist=['Claim']).Claim
    normalized = description.strip().lower()
    qs = Claim.objects.filter(user=user)
    if claim_id:
        qs = qs.exclude(id=claim_id)

    for other in qs:
        if other.incident_description and other.incident_description.strip().lower() == normalized:
            return 25, 'Description matches a previously submitted claim — possible duplicate.'

    return 0, ''


def _time_gap_score(incident_date):
    """Score based on the gap between incident date and claim filing date."""
    if not incident_date:
        return 0, ''
    today = timezone.now().date()
    gap = (today - incident_date).days
    if gap > 90:
        return 15, f'{gap} days between incident and claim — long delay before reporting.'
    elif gap > 30:
        return 8, f'{gap} days between incident and claim — delayed reporting.'
    return 0, ''


def _prior_rejection_score(user):
    """Score higher if the user has had claims rejected before."""
    Claim = __import__('core.models', fromlist=['Claim']).Claim
    rejected = Claim.objects.filter(user=user, status='rejected').count()
    if rejected >= 2:
        return 15, f'{rejected} previously rejected claims on record.'
    elif rejected >= 1:
        return 8, f'{rejected} previously rejected claim on record.'
    return 0, ''


def analyze_claim(amount_claimed, policy, user, incident_description='',
                  incident_date=None, claim_id=None):
    """Run the full fraud analysis and return a structured result.

    Returns:
        {
            'score': int 0-100,
            'risk_level': 'low' | 'medium' | 'high' | 'critical',
            'reasons': [str, ...],
            'factors': [{'name': str, 'score': int, 'reason': str}, ...],
        }
    """
    factors = []

    s, r = _amount_ratio_score(amount_claimed, policy)
    factors.append({'name': 'Amount-to-coverage ratio', 'score': s, 'reason': r})

    s, r = _frequency_score(user, claim_id)
    factors.append({'name': 'Claim frequency', 'score': s, 'reason': r})

    s, r = _policy_age_score(policy)
    factors.append({'name': 'Policy age', 'score': s, 'reason': r})

    s, r = _amount_anomaly_score(amount_claimed)
    factors.append({'name': 'Amount anomaly', 'score': s, 'reason': r})

    s, r = _description_analysis(incident_description)
    factors.append({'name': 'Description analysis', 'score': s, 'reason': r})

    s, r = _duplicate_description_check(incident_description, user, claim_id)
    factors.append({'name': 'Duplicate description', 'score': s, 'reason': r})

    s, r = _time_gap_score(incident_date)
    factors.append({'name': 'Reporting delay', 'score': s, 'reason': r})

    s, r = _prior_rejection_score(user)
    factors.append({'name': 'Prior claim history', 'score': s, 'reason': r})

    total = sum(f['score'] for f in factors)
    score = max(0, min(100, total))
    reasons = [f['reason'] for f in factors if f['reason']]

    if score >= 60:
        risk_level = 'critical'
    elif score >= 40:
        risk_level = 'high'
    elif score >= 20:
        risk_level = 'medium'
    else:
        risk_level = 'low'

    return {
        'score': score,
        'risk_level': risk_level,
        'reasons': reasons,
        'factors': factors,
    }


def get_risk_label(risk_level):
    """Human-readable label for the risk level."""
    labels = {
        'low': 'Low Risk',
        'medium': 'Medium Risk',
        'high': 'High Risk',
        'critical': 'Critical Risk',
    }
    return labels.get(risk_level, 'Unknown')
