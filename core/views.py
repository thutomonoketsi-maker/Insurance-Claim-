import re
import uuid
import json
from datetime import datetime, timedelta
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import (
    UserProfile, Policy, Claim, Payment, Document,
    Notification, ActivityLog,
)


# ============================================================
# HELPERS
# ============================================================

def role_required(role):
    """Decorator factory: restrict a view to a specific role."""
    def decorator(view_func):
        @login_required
        def wrapper(request, *args, **kwargs):
            if not hasattr(request.user, 'profile'):
                return redirect('login')
            if request.user.profile.role != role:
                return redirect('dashboard')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def log_activity(user, action, description):
    ActivityLog.objects.create(user=user, action=action, description=description)


def notify(user, title, message, category='system', **kwargs):
    Notification.objects.create(
        user=user, title=title, message=message,
        category=category, **kwargs,
    )


def notify_role(role, title, message, category='system', **kwargs):
    for u in User.objects.filter(profile__role=role, profile__status='active'):
        notify(u, title, message, category, **kwargs)


def calculate_fraud_score(amount_claimed, policy, user):
    """Simple rule-based fraud score (0-100)."""
    score = 0

    coverage = policy.coverage_amount or Decimal('100000')
    ratio = (Decimal(str(amount_claimed)) / coverage) * 100
    if ratio > 80:
        score += 25
    elif ratio > 50:
        score += 15

    recent = Claim.objects.filter(
        user=user, submitted_at__gte=timezone.now() - timedelta(days=30)
    ).count()
    if recent >= 3:
        score += 20
    elif recent >= 2:
        score += 10

    if policy.start_date:
        age = (timezone.now().date() - policy.start_date).days
        if age < 30:
            score += 15
        elif age < 90:
            score += 5

    if Decimal(str(amount_claimed)) > Decimal('50000'):
        score += 10
    if Decimal(str(amount_claimed)) > Decimal('100000'):
        score += 15

    return max(0, min(100, score))


# ============================================================
# LANDING PAGES
# ============================================================

def home(request):
    if request.user.is_authenticated:
        logout(request)
    return render(request, 'core/home.html')


def about(request):
    return render(request, 'core/about.html')


def contact(request):
    return render(request, 'core/contact.html')


def features(request):
    return render(request, 'core/features.html')


# ============================================================
# AUTH
# ============================================================

def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        id_number = request.POST.get('id_number', '').strip()
        password = request.POST.get('password')
        password2 = request.POST.get('password2')

        errors = []
        if not first_name:
            errors.append('First name is required.')
        if not last_name:
            errors.append('Last name is required.')
        if not email:
            errors.append('Email is required.')
        elif not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            errors.append('Please enter a valid email address.')
        if User.objects.filter(email=email).exists():
            errors.append('An account with this email already exists.')
        if not password:
            errors.append('Password is required.')
        elif len(password) < 8:
            errors.append('Password must be at least 8 characters.')
        if password != password2:
            errors.append('Passwords do not match.')
        if not id_number:
            errors.append('ID number is required.')
        if not request.POST.get('terms'):
            errors.append('You must accept the Terms & Conditions.')

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, 'core/register.html')

        username = email.split('@')[0]
        if User.objects.filter(username=username).exists():
            username = f"{username}_{User.objects.count() + 1}"

        user = User.objects.create_user(
            username=username, email=email, password=password,
            first_name=first_name, last_name=last_name,
        )
        profile = user.profile
        profile.role = 'policyholder'
        profile.phone = phone
        profile.id_number = id_number
        profile.status = 'active'
        profile.save()

        log_activity(user, 'create', 'Account registered')
        login(request, user)
        messages.success(request, f'Welcome {first_name}! Your account is ready.')
        return redirect('customer_dashboard')

    return render(request, 'core/register.html')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        email_or_username = request.POST.get('username', '').strip()
        password = request.POST.get('password')
        remember = request.POST.get('remember')

        if not email_or_username or not password:
            messages.error(request, 'Please enter your email and password.')
            return render(request, 'core/login.html')

        # Allow login by email or username
        user = None
        if '@' in email_or_username:
            try:
                user_obj = User.objects.get(email=email_or_username)
                user = authenticate(request, username=user_obj.username, password=password)
            except User.DoesNotExist:
                pass
        else:
            user = authenticate(request, username=email_or_username, password=password)

        if user is None:
            messages.error(request, 'Invalid credentials.')
            return render(request, 'core/login.html')

        profile = getattr(user, 'profile', None)
        if profile is None:
            UserProfile.objects.create(user=user, role='policyholder', status='active')
            profile = user.profile

        if profile.status in ('suspended', 'disabled'):
            messages.error(request, 'Your account has been suspended. Contact support.')
            return render(request, 'core/login.html')

        login(request, user)
        request.session.set_expiry(1209600 if remember else 0)
        log_activity(user, 'login', 'Logged in')

        role = profile.role
        if role == 'administrator':
            return redirect('admin_dashboard')
        elif role == 'staff':
            return redirect('staff_dashboard')
        elif role == 'investigator':
            return redirect('investigator_dashboard')
        else:
            return redirect('customer_dashboard')

    return render(request, 'core/login.html')


def logout_view(request):
    if request.user.is_authenticated:
        log_activity(request.user, 'logout', 'Logged out')
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('home')


@login_required
def dashboard(request):
    """Redirect to the correct dashboard based on role."""
    role = getattr(request.user, 'profile', None)
    if role is None:
        return redirect('login')
    role = role.role
    if role == 'administrator':
        return redirect('admin_dashboard')
    elif role == 'staff':
        return redirect('staff_dashboard')
    elif role == 'investigator':
        return redirect('investigator_dashboard')
    return redirect('customer_dashboard')


# ============================================================
# CUSTOMER (POLICYHOLDER) VIEWS
# ============================================================

@role_required('policyholder')
def customer_dashboard(request):
    user = request.user
    policies = Policy.objects.filter(user=user)
    claims = Claim.objects.filter(user=user)
    payments = Payment.objects.filter(user=user)
    unread = Notification.objects.filter(user=user, is_read=False).count()

    context = {
        'active_policies': policies.filter(status='active').count(),
        'total_policies': policies.count(),
        'pending_claims': claims.filter(status__in=['submitted', 'under_review', 'investigation']).count(),
        'total_claims': claims.count(),
        'total_paid': payments.filter(status='completed', payment_type='premium').aggregate(
            Sum('amount')
        )['amount__sum'] or 0,
        'recent_claims': claims.order_by('-submitted_at')[:5],
        'recent_policies': policies.order_by('-created_at')[:5],
        'unread_notifications': unread,
    }
    return render(request, 'core/customer_dashboard.html', context)


@role_required('policyholder')
def customer_policies(request):
    policies = Policy.objects.filter(user=request.user).order_by('-created_at')
    total_coverage = policies.aggregate(Sum('coverage_amount'))['coverage_amount__sum'] or 0
    total_premium = policies.aggregate(Sum('premium_amount'))['premium_amount__sum'] or 0

    context = {
        'policies': policies,
        'total_coverage': total_coverage,
        'total_premium': total_premium,
        'active_count': policies.filter(status='active').count(),
    }
    return render(request, 'core/customer_policies.html', context)


@role_required('policyholder')
def customer_policy_detail(request, policy_id):
    policy = get_object_or_404(Policy, id=policy_id, user=request.user)
    claims = Claim.objects.filter(policy=policy)
    payments = Payment.objects.filter(policy=policy)
    days_remaining = (policy.end_date - datetime.now().date()).days if policy.end_date else 0

    now = timezone.now()
    month_paid = payments.filter(
        status='completed',
        payment_type='premium',
        paid_at__year=now.year, paid_at__month=now.month,
    ).exists()

    context = {
        'policy': policy,
        'claims': claims,
        'payments': payments,
        'days_remaining': max(days_remaining, 0),
        'month_paid': month_paid,
    }
    return render(request, 'core/customer_policy_detail.html', context)


POLICY_LIMITS = {
    'vehicle': (10000, 500000),
    'home': (50000, 2000000),
    'life': (50000, 5000000),
    'health': (25000, 1000000),
    'business': (100000, 5000000),
    'travel': (5000, 200000),
}

PREMIUM_RATES = {
    'vehicle': Decimal('0.015'),
    'home': Decimal('0.008'),
    'life': Decimal('0.005'),
    'health': Decimal('0.012'),
    'business': Decimal('0.010'),
    'travel': Decimal('0.020'),
}


def calculate_premium(policy_type, coverage_amount):
    rate = PREMIUM_RATES.get(policy_type, Decimal('0.010'))
    return (Decimal(str(coverage_amount)) * rate / Decimal('12')).quantize(Decimal('0.01'))


@role_required('policyholder')
def customer_purchase_policy(request):
    if request.method == 'POST':
        policy_type = request.POST.get('policy_type')
        coverage_amount = request.POST.get('coverage_amount')
        start_date = request.POST.get('start_date')
        beneficiary_name = request.POST.get('beneficiary_name', '').strip()

        if not all([policy_type, coverage_amount, start_date]):
            messages.error(request, 'All required fields must be filled.')
            return redirect('customer_purchase_policy')

        min_cov, max_cov = POLICY_LIMITS.get(policy_type, (1000, 1000000))
        coverage = Decimal(coverage_amount)
        if coverage < min_cov or coverage > max_cov:
            messages.error(request, f'Coverage for this plan must be between R {min_cov:,.0f} and R {max_cov:,.0f}.')
            return redirect('customer_purchase_policy')

        premium_amount = calculate_premium(policy_type, coverage)

        policy_number = f"POL-{datetime.now().year}-{Policy.objects.count() + 1001}"
        start = datetime.strptime(start_date, '%Y-%m-%d').date()
        end = start + timedelta(days=365)

        policy = Policy.objects.create(
            policy_number=policy_number,
            user=request.user,
            policy_type=policy_type,
            coverage_amount=coverage,
            premium_amount=premium_amount,
            start_date=start,
            end_date=end,
            renewal_date=end,
            status='pending',
            beneficiary_name=beneficiary_name,
        )

        notify(request.user, 'Policy Submitted',
               f'Your {policy.get_policy_type_display()} policy {policy.policy_number} is pending review.',
               category='policy', related_policy=policy,
               action_url=f'/dashboard/customer/policy/{policy.id}/')
        notify_role('staff', 'New Policy Application',
                    f'{request.user.get_full_name()} applied for a {policy.get_policy_type_display()} policy.',
                    category='policy', action_url='/staff/applications/')

        messages.success(request, f'Policy {policy.policy_number} created. Your monthly premium is R {premium_amount:.2f}.')
        return redirect('customer_payshap_payment', policy_id=policy.id)

    context = {'policy_limits': POLICY_LIMITS}
    return render(request, 'core/customer_purchase_policy.html', context)


@role_required('policyholder')
def customer_renew_policy(request, policy_id):
    policy = get_object_or_404(Policy, id=policy_id, user=request.user)

    if request.method == 'POST':
        if policy.status not in ('active', 'expired'):
            messages.error(request, 'Only active or expired policies can be renewed.')
            return redirect('customer_policy_detail', policy_id=policy.id)

        policy.end_date = policy.end_date + timedelta(days=365)
        policy.renewal_date = policy.end_date
        policy.status = 'active'
        policy.save()

        notify(request.user, 'Policy Renewed',
               f'Your {policy.get_policy_type_display()} policy {policy.policy_number} has been renewed until {policy.end_date.strftime("%d %b %Y")}.',
               category='policy', related_policy=policy,
               action_url=f'/dashboard/customer/policy/{policy.id}/')
        notify_role('staff', 'Policy Renewed',
                    f'{request.user.get_full_name()} renewed policy {policy.policy_number}.',
                    category='policy')
        messages.success(request, f'Policy {policy.policy_number} renewed until {policy.end_date.strftime("%d %b %Y")}.')
        return redirect('customer_policy_detail', policy_id=policy.id)

    context = {'policy': policy}
    return render(request, 'core/customer_renew_policy.html', context)


@role_required('policyholder')
def customer_cancel_policy(request, policy_id):
    policy = get_object_or_404(Policy, id=policy_id, user=request.user)

    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        if not reason:
            messages.error(request, 'Please provide a reason for cancellation.')
            return redirect('customer_cancel_policy', policy_id=policy.id)

        policy.status = 'cancelled'
        policy.save()

        notify(request.user, 'Policy Cancelled',
               f'Your {policy.get_policy_type_display()} policy {policy.policy_number} has been cancelled.',
               category='policy', related_policy=policy)
        notify_role('staff', 'Policy Cancellation',
                    f'{request.user.get_full_name()} cancelled policy {policy.policy_number}. Reason: {reason}',
                    category='policy')
        log_activity(request.user, 'update', f'Cancelled policy {policy.policy_number}: {reason}')
        messages.success(request, f'Policy {policy.policy_number} has been cancelled.')
        return redirect('customer_policies')

    context = {'policy': policy}
    return render(request, 'core/customer_cancel_policy.html', context)


@role_required('policyholder')
def customer_payshap_payment(request, policy_id):
    policy = get_object_or_404(Policy, id=policy_id, user=request.user)

    if policy.status not in ('active', 'pending'):
        messages.error(request, 'This policy is not eligible for payment.')
        return redirect('customer_policy_detail', policy_id=policy.id)

    if request.method == 'POST':
        amount = request.POST.get('amount')
        payment_type = request.POST.get('payment_type', 'premium')

        if not amount:
            messages.error(request, 'Amount is required.')
            return redirect('customer_payshap_payment', policy_id=policy.id)

        amount = Decimal(amount)
        if amount <= 0:
            messages.error(request, 'Amount must be greater than zero.')
            return redirect('customer_payshap_payment', policy_id=policy.id)

        payment_number = f"PAY-{datetime.now().year}-{Payment.objects.count() + 1001}"
        payment = Payment.objects.create(
            payment_number=payment_number,
            user=request.user,
            policy=policy,
            amount=amount,
            payment_method='payshap',
            payment_type=payment_type,
            status='completed',
            due_date=timezone.now().date(),
            paid_at=timezone.now(),
            reference=f"PayShap-{payment_number}",
        )

        notify(request.user, 'Payment Successful',
               f'Your PayShap payment of R {amount:.2f} for policy {policy.policy_number} was successful.',
               category='payment', related_policy=policy, related_payment=payment)
        notify_role('staff', 'Payment Received',
                    f'{request.user.get_full_name()} paid R {amount:.2f} via PayShap for {policy.policy_number}.',
                    category='payment')
        log_activity(request.user, 'create', f'Paid R {amount:.2f} via PayShap for policy {policy.policy_number}')

        messages.success(request, f'PayShap payment of R {amount:.2f} completed successfully.')
        return redirect('customer_policy_detail', policy_id=policy.id)

    context = {'policy': policy}
    return render(request, 'core/customer_payshap_payment.html', context)


@role_required('policyholder')
def customer_claims(request):
    claims = Claim.objects.filter(user=request.user).order_by('-submitted_at')
    context = {
        'claims': claims,
        'total_claims': claims.count(),
        'approved': claims.filter(status='approved').count(),
        'pending': claims.filter(status__in=['submitted', 'under_review', 'investigation']).count(),
        'rejected': claims.filter(status='rejected').count(),
    }
    return render(request, 'core/customer_claims.html', context)


@role_required('policyholder')
def customer_submit_claim(request):
    policies = Policy.objects.filter(user=request.user, status='active')

    if request.method == 'POST':
        policy_id = request.POST.get('policy_id')
        incident_type = request.POST.get('incident_type')
        incident_date = request.POST.get('incident_date')
        incident_description = request.POST.get('incident_description', '').strip()
        incident_location = request.POST.get('incident_location', '').strip()
        amount_claimed = request.POST.get('amount_claimed')

        if not all([policy_id, incident_type, incident_date, incident_description, amount_claimed]):
            messages.error(request, 'All required fields must be filled.')
            return redirect('customer_submit_claim')

        policy = get_object_or_404(Policy, id=policy_id, user=request.user)

        claim_number = f"CLM-{datetime.now().year}-{Claim.objects.count() + 1001}"
        score = calculate_fraud_score(amount_claimed, policy, request.user)

        claim = Claim.objects.create(
            claim_number=claim_number,
            policy=policy,
            user=request.user,
            incident_type=incident_type,
            incident_date=incident_date,
            incident_description=incident_description,
            incident_location=incident_location,
            amount_claimed=Decimal(amount_claimed),
            status='submitted',
            fraud_score=score,
            fraud_flagged=score >= 60,
        )

        files = request.FILES.getlist('documents')
        for f in files:
            if f.size > 5 * 1024 * 1024:
                continue
            allowed = ['image/jpeg', 'image/png', 'application/pdf']
            if f.content_type not in allowed:
                continue
            doc_number = f"DOC-{datetime.now().year}-{Document.objects.count() + 1001}"
            Document.objects.create(
                document_number=doc_number,
                user=request.user,
                claim=claim,
                document_type='other',
                document_name=f.name,
                document_file=f,
            )

        notify(request.user, 'Claim Submitted',
               f'Your claim {claim_number} has been submitted and is being reviewed.',
               category='claim', related_claim=claim,
               action_url=f'/dashboard/customer/claim/{claim.id}/')
        notify_role('staff', 'New Claim Submitted',
                    f'{request.user.get_full_name()} submitted claim {claim_number}.',
                    category='claim', action_url='/staff/claims/')

        if claim.fraud_flagged:
            notify_role('investigator', 'High-Risk Claim Flagged',
                        f'Claim {claim_number} has a fraud score of {score}.',
                        category='fraud', action_url=f'/investigator/cases/')

        messages.success(request, f'Claim {claim_number} submitted successfully.')
        return redirect('customer_claims')

    context = {'policies': policies}
    return render(request, 'core/customer_submit_claim.html', context)


@role_required('policyholder')
def customer_claim_detail(request, claim_id):
    claim = get_object_or_404(Claim, id=claim_id, user=request.user)
    documents = Document.objects.filter(claim=claim)
    payments = Payment.objects.filter(claim=claim)

    context = {
        'claim': claim,
        'documents': documents,
        'payments': payments,
    }
    return render(request, 'core/customer_claim_detail.html', context)


@role_required('policyholder')
def customer_payments(request):
    payments = Payment.objects.filter(user=request.user).order_by('-created_at')
    money_out = payments.filter(status='completed', payment_type='premium').aggregate(Sum('amount'))['amount__sum'] or 0
    money_in = payments.filter(status='completed', payment_type='payout').aggregate(Sum('amount'))['amount__sum'] or 0
    context = {
        'payments': payments,
        'total_paid': money_out,
        'money_in': money_in,
        'pending_count': payments.filter(status='pending').count(),
    }
    return render(request, 'core/customer_payments.html', context)


@role_required('policyholder')
def customer_documents(request):
    if request.method == 'POST':
        document_type = request.POST.get('document_type')
        document_name = request.POST.get('document_name', '').strip()
        document_file = request.FILES.get('document_file')

        if not all([document_type, document_file]):
            messages.error(request, 'Document type and file are required.')
            return redirect('customer_documents')

        if document_file.size > 5 * 1024 * 1024:
            messages.error(request, 'File exceeds 5MB limit.')
            return redirect('customer_documents')

        allowed = ['image/jpeg', 'image/png', 'application/pdf']
        if document_file.content_type not in allowed:
            messages.error(request, 'Only JPG, PNG, and PDF files are accepted.')
            return redirect('customer_documents')

        doc_number = f"DOC-{datetime.now().year}-{Document.objects.count() + 1001}"
        Document.objects.create(
            document_number=doc_number,
            user=request.user,
            document_type=document_type,
            document_name=document_name or document_type.replace('_', ' ').title(),
            document_file=document_file,
        )
        messages.success(request, 'Document uploaded successfully.')
        return redirect('customer_documents')

    documents = Document.objects.filter(user=request.user).order_by('-uploaded_at')
    context = {
        'documents': documents,
        'verified_count': documents.filter(status='verified').count(),
        'pending_count': documents.filter(status='pending').count(),
    }
    return render(request, 'core/customer_documents.html', context)


@role_required('policyholder')
def customer_notifications(request):
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')

    if request.method == 'POST':
        notif_id = request.POST.get('notification_id')
        if notif_id:
            n = Notification.objects.filter(id=notif_id, user=request.user).first()
            if n:
                n.is_read = True
                n.read_at = timezone.now()
                n.save()
        return redirect('customer_notifications')

    context = {'notifications': notifications}
    return render(request, 'core/customer_notifications.html', context)


@role_required('policyholder')
def customer_profile(request):
    if request.method == 'POST':
        user = request.user
        user.first_name = request.POST.get('first_name', user.first_name).strip()
        user.last_name = request.POST.get('last_name', user.last_name).strip()
        user.email = request.POST.get('email', user.email).strip()
        user.save()

        profile = user.profile
        profile.phone = request.POST.get('phone', profile.phone).strip()
        profile.address = request.POST.get('address', profile.address).strip()
        profile.city = request.POST.get('city', profile.city).strip()
        profile.province = request.POST.get('province', profile.province).strip()
        profile.postal_code = request.POST.get('postal_code', profile.postal_code).strip()
        profile.save()

        messages.success(request, 'Profile updated successfully.')
        return redirect('customer_profile')

    return render(request, 'core/customer_profile.html')


@role_required('policyholder')
def customer_settings(request):
    if request.method == 'POST':
        current = request.POST.get('current_password')
        new = request.POST.get('new_password')
        confirm = request.POST.get('confirm_password')

        if not request.user.check_password(current):
            messages.error(request, 'Current password is incorrect.')
            return redirect('customer_settings')
        if not new or len(new) < 8:
            messages.error(request, 'New password must be at least 8 characters.')
            return redirect('customer_settings')
        if new != confirm:
            messages.error(request, 'New passwords do not match.')
            return redirect('customer_settings')

        request.user.set_password(new)
        request.user.save()
        messages.success(request, 'Password changed successfully.')
        return redirect('login')

    return render(request, 'core/customer_settings.html')


# ============================================================
# STAFF VIEWS
# ============================================================

@role_required('staff')
def staff_dashboard(request):
    pending_policies = Policy.objects.filter(status='pending').count()
    pending_claims = Claim.objects.filter(status='submitted').count()
    under_review = Claim.objects.filter(status='under_review').count()
    active_policies = Policy.objects.filter(status='active').count()

    context = {
        'pending_policies': pending_policies,
        'pending_claims': pending_claims,
        'under_review': under_review,
        'active_policies': active_policies,
        'recent_claims': Claim.objects.order_by('-submitted_at')[:5],
        'recent_policies': Policy.objects.order_by('-created_at')[:5],
    }
    return render(request, 'core/staff_dashboard.html', context)


@role_required('staff')
def staff_applications(request):
    policies = Policy.objects.filter(status='pending').order_by('-created_at')
    context = {'policies': policies}
    return render(request, 'core/staff_applications.html', context)


@role_required('staff')
def staff_process_application(request, policy_id):
    policy = get_object_or_404(Policy, id=policy_id)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'approve':
            policy.status = 'active'
            policy.save()
            notify(policy.user, 'Policy Approved',
                   f'Your {policy.get_policy_type_display()} policy {policy.policy_number} is now active.',
                   category='policy', related_policy=policy,
                   action_url=f'/dashboard/customer/policy/{policy.id}/')
            messages.success(request, f'Policy {policy.policy_number} approved.')
        elif action == 'reject':
            policy.status = 'cancelled'
            policy.save()
            notify(policy.user, 'Policy Rejected',
                   f'Your policy application {policy.policy_number} was not approved.',
                   category='policy')
            messages.info(request, f'Policy {policy.policy_number} rejected.')
        return redirect('staff_applications')

    context = {'policy': policy}
    return render(request, 'core/staff_process_application.html', context)


@role_required('staff')
def staff_claims(request):
    claims = Claim.objects.filter(status__in=['submitted', 'under_review']).order_by('-submitted_at')
    context = {'claims': claims}
    return render(request, 'core/staff_claims.html', context)


@role_required('staff')
def staff_claim_review(request, claim_id):
    claim = get_object_or_404(Claim, id=claim_id)

    if request.method == 'POST' and request.POST.get('action') == 'pay_out':
        claim.status = 'paid'
        claim.save()
        payment_number = f"PAY-{datetime.now().year}-{Payment.objects.count() + 1001}"
        Payment.objects.create(
            payment_number=payment_number,
            user=claim.user,
            claim=claim,
            policy=claim.policy,
            amount=claim.amount_approved or claim.amount_claimed,
            payment_method='payshap',
            payment_type='payout',
            status='completed',
            due_date=timezone.now().date(),
            paid_at=timezone.now(),
            reference=f"Payout-{claim.claim_number}",
        )
        notify(claim.user, 'Claim Payout Received',
               f'R {(claim.amount_approved or claim.amount_claimed):.2f} has been paid to you for claim {claim.claim_number}.',
               category='payment', related_claim=claim)
        log_activity(request.user, 'approve', f'Paid out R {(claim.amount_approved or claim.amount_claimed):.2f} for claim {claim.claim_number}')
        messages.success(request, f'Claim {claim.claim_number} paid out successfully.')
        return redirect('staff_claims')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'approve':
            claim.status = 'approved'
            claim.amount_approved = claim.amount_claimed
            claim.resolved_at = timezone.now()
            claim.save()
            notify(claim.user, 'Claim Approved',
                   f'Your claim {claim.claim_number} has been approved.',
                   category='claim', related_claim=claim,
                   action_url=f'/dashboard/customer/claim/{claim.id}/')
            messages.success(request, f'Claim {claim.claim_number} approved.')
        elif action == 'reject':
            claim.status = 'rejected'
            claim.rejection_reason = request.POST.get('reason', '').strip()
            claim.resolved_at = timezone.now()
            claim.save()
            notify(claim.user, 'Claim Rejected',
                   f'Your claim {claim.claim_number} has been rejected.',
                   category='claim', related_claim=claim,
                   action_url=f'/dashboard/customer/claim/{claim.id}/')
            messages.info(request, f'Claim {claim.claim_number} rejected.')
        elif action == 'investigate':
            investigator_id = request.POST.get('investigator_id')
            claim.status = 'investigation'
            if investigator_id:
                claim.investigator_id = investigator_id
            claim.save()
            if investigator_id:
                inv = User.objects.get(id=investigator_id)
                notify(inv, 'Case Assigned to You',
                       f'Claim {claim.claim_number} has been assigned to you for investigation.',
                       category='fraud', action_url=f'/investigator/cases/{claim.id}/')
            notify_role('investigator', 'Investigation Required',
                        f'Claim {claim.claim_number} needs investigation.',
                        category='fraud', action_url=f'/investigator/cases/{claim.id}/')
            messages.info(request, f'Claim {claim.claim_number} sent for investigation.')
        return redirect('staff_claims')

    investigators = User.objects.filter(profile__role='investigator', profile__status='active')
    context = {'claim': claim, 'investigators': investigators}
    return render(request, 'core/staff_claim_review.html', context)


@role_required('staff')
def staff_payments(request):
    payments = Payment.objects.all().order_by('-created_at')
    context = {
        'payments': payments,
        'total_completed': payments.filter(status='completed').aggregate(Sum('amount'))['amount__sum'] or 0,
        'pending_count': payments.filter(status='pending').count(),
    }
    return render(request, 'core/staff_payments.html', context)


@role_required('staff')
def staff_create_payment(request):
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        policy_id = request.POST.get('policy_id') or None
        claim_id = request.POST.get('claim_id') or None
        amount = request.POST.get('amount')
        payment_method = request.POST.get('payment_method', 'card')
        payment_type = request.POST.get('payment_type', 'premium')
        due_date = request.POST.get('due_date')
        status = request.POST.get('status', 'pending')

        if not all([user_id, amount, due_date]):
            messages.error(request, 'User, amount, and due date are required.')
            return redirect('staff_create_payment')

        target_user = get_object_or_404(User, id=user_id)
        policy = get_object_or_404(Policy, id=policy_id) if policy_id else None
        claim = get_object_or_404(Claim, id=claim_id) if claim_id else None

        payment_number = f"PAY-{datetime.now().year}-{Payment.objects.count() + 1001}"
        Payment.objects.create(
            payment_number=payment_number,
            user=target_user,
            policy=policy,
            claim=claim,
            amount=Decimal(amount),
            payment_method=payment_method,
            payment_type=payment_type,
            status=status,
            due_date=due_date,
            paid_at=timezone.now() if status == 'completed' else None,
        )

        notify(target_user, 'Payment Recorded',
               f'A payment of R {Decimal(amount):.2f} has been recorded on your account.',
               category='payment', related_policy=policy, related_payment=Payment.objects.get(payment_number=payment_number))
        log_activity(request.user, 'create', f'Created payment {payment_number} for {target_user.get_full_name()}')
        messages.success(request, f'Payment {payment_number} created successfully.')
        return redirect('staff_payments')

    users = User.objects.filter(profile__role='policyholder').order_by('first_name')
    policies = Policy.objects.filter(status='active').order_by('-created_at')
    claims = Claim.objects.filter(status='approved').order_by('-submitted_at')
    context = {'users': users, 'policies': policies, 'claims': claims}
    return render(request, 'core/staff_create_payment.html', context)


@role_required('staff')
def staff_documents(request):
    documents = Document.objects.filter(status='pending').order_by('-uploaded_at')
    context = {'documents': documents}
    return render(request, 'core/staff_documents.html', context)


@role_required('staff')
def staff_verify_document(request, document_id):
    document = get_object_or_404(Document, id=document_id)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'verify':
            document.status = 'verified'
            document.verified_by = request.user
            document.verified_at = timezone.now()
            document.save()
            notify(document.user, 'Document Verified',
                   f'Your document "{document.document_name}" has been verified.',
                   category='document')
            messages.success(request, 'Document verified.')
        elif action == 'reject':
            document.status = 'rejected'
            document.rejection_reason = request.POST.get('reason', '').strip()
            document.save()
            notify(document.user, 'Document Rejected',
                   f'Your document "{document.document_name}" was rejected.',
                   category='document')
            messages.info(request, 'Document rejected.')
        return redirect('staff_documents')

    context = {'document': document}
    return render(request, 'core/staff_verify_document.html', context)


@role_required('staff')
def staff_profile(request):
    return render(request, 'core/staff_profile.html')


# ============================================================
# INVESTIGATOR VIEWS
# ============================================================

@role_required('investigator')
def investigator_dashboard(request):
    assigned = Claim.objects.filter(investigator=request.user)
    flagged = Claim.objects.filter(fraud_flagged=True)

    context = {
        'assigned_count': assigned.count(),
        'flagged_count': flagged.count(),
        'open_cases': assigned.exclude(status__in=['approved', 'rejected', 'paid']).count(),
        'recent_cases': assigned.order_by('-updated_at')[:5],
    }
    return render(request, 'core/investigator_dashboard.html', context)


@role_required('investigator')
def investigator_cases(request):
    cases = Claim.objects.filter(
        Q(investigator=request.user) | Q(fraud_flagged=True)
    ).order_by('-submitted_at')
    context = {'cases': cases}
    return render(request, 'core/investigator_cases.html', context)


@role_required('investigator')
def investigator_case_detail(request, claim_id):
    claim = get_object_or_404(Claim, id=claim_id)

    if request.method == 'POST':
        claim.investigator = request.user
        claim.investigation_notes = request.POST.get('notes', '').strip()
        claim.status = 'under_review'
        claim.save()
        notify_role('staff', 'Investigation Complete',
                    f'Investigator submitted notes on claim {claim.claim_number}.',
                    category='claim', action_url=f'/staff/claims/{claim.id}/review/')
        messages.success(request, 'Investigation notes saved.')
        return redirect('investigator_cases')

    context = {'claim': claim}
    return render(request, 'core/investigator_case_detail.html', context)


@role_required('investigator')
def investigator_profile(request):
    return render(request, 'core/investigator_profile.html')


# ============================================================
# ADMIN VIEWS
# ============================================================

@role_required('administrator')
def admin_dashboard(request):
    context = {
        'total_users': User.objects.count(),
        'total_policies': Policy.objects.count(),
        'active_policies': Policy.objects.filter(status='active').count(),
        'total_claims': Claim.objects.count(),
        'pending_claims': Claim.objects.filter(status='submitted').count(),
        'flagged_claims': Claim.objects.filter(fraud_flagged=True).count(),
        'total_payments': Payment.objects.filter(status='completed').aggregate(
            Sum('amount')
        )['amount__sum'] or 0,
        'recent_activity': ActivityLog.objects.order_by('-created_at')[:10],
    }
    return render(request, 'core/admin_dashboard.html', context)


@role_required('administrator')
def admin_users(request):
    users = User.objects.select_related('profile').all().order_by('-date_joined')
    context = {'users': users}
    return render(request, 'core/admin_users.html', context)


@role_required('administrator')
def admin_user_detail(request, user_id):
    target_user = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        action = request.POST.get('action')
        profile = target_user.profile
        if action == 'suspend':
            profile.status = 'suspended'
            profile.save()
            messages.info(request, f'{target_user.username} suspended.')
        elif action == 'activate':
            profile.status = 'active'
            profile.save()
            messages.success(request, f'{target_user.username} activated.')
        return redirect('admin_user_detail', user_id=user_id)

    context = {
        'target_user': target_user,
        'policies': Policy.objects.filter(user=target_user),
        'claims': Claim.objects.filter(user=target_user),
    }
    return render(request, 'core/admin_user_detail.html', context)


@role_required('administrator')
def admin_policies(request):
    policies = Policy.objects.all().order_by('-created_at')
    context = {'policies': policies}
    return render(request, 'core/admin_policies.html', context)


@role_required('administrator')
def admin_claims(request):
    claims = Claim.objects.all().order_by('-submitted_at')
    context = {'claims': claims}
    return render(request, 'core/admin_claims.html', context)


@role_required('administrator')
def admin_payments(request):
    payments = Payment.objects.all().order_by('-created_at')
    context = {'payments': payments}
    return render(request, 'core/admin_payments.html', context)


@role_required('administrator')
def admin_staff(request):
    staff = User.objects.filter(profile__role='staff').order_by('-date_joined')
    investigators = User.objects.filter(profile__role='investigator').order_by('-date_joined')
    context = {'staff': staff, 'investigators': investigators}
    return render(request, 'core/admin_staff.html', context)


@role_required('administrator')
def admin_add_staff(request):
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        role = request.POST.get('role', 'staff')
        password = request.POST.get('password')

        if not all([first_name, last_name, email, password]):
            messages.error(request, 'All fields are required.')
            return redirect('admin_add_staff')

        if User.objects.filter(email=email).exists():
            messages.error(request, 'A user with this email already exists.')
            return redirect('admin_add_staff')

        username = email.split('@')[0]
        if User.objects.filter(username=username).exists():
            username = f"{username}_{User.objects.count() + 1}"

        user = User.objects.create_user(
            username=username, email=email, password=password,
            first_name=first_name, last_name=last_name,
        )
        profile = user.profile
        profile.role = role
        profile.status = 'active'
        profile.save()

        messages.success(request, f'{role.title()} account created for {first_name} {last_name}.')
        return redirect('admin_staff')

    return render(request, 'core/admin_add_staff.html')


@role_required('administrator')
def admin_logs(request):
    logs = ActivityLog.objects.all().order_by('-created_at')[:200]
    context = {'logs': logs}
    return render(request, 'core/admin_logs.html', context)


@role_required('administrator')
def admin_profile(request):
    return render(request, 'core/admin_profile.html')


@role_required('policyholder')
@require_POST
@csrf_exempt
def copilot_chat(request):
    try:
        data = json.loads(request.body)
        question = (data.get('message') or '').strip().lower()
    except Exception:
        return JsonResponse({'reply': 'Sorry, I could not understand that. Could you rephrase?'})

    if not question:
        return JsonResponse({'reply': 'Hi! I am your SIFDS insurance assistant. Ask me about your policies, claims, payments, or coverage limits.'})

    user = request.user
    policies = Policy.objects.filter(user=user)
    claims = Claim.objects.filter(user=user)
    payments = Payment.objects.filter(user=user, status='completed')

    if any(w in question for w in ['policy', 'policies', 'cover', 'coverage', 'plan']):
        if policies.exists():
            lines = []
            for p in policies[:5]:
                lines.append(f"{p.policy_number} ({p.get_policy_type_display()}): R {p.coverage_amount:,.0f} cover, R {p.premium_amount:.2f}/month, status: {p.get_status_display()}.")
            return JsonResponse({'reply': f'You have {policies.count()} polic{"y" if policies.count()==1 else "ies"}:\n' + '\n'.join(lines)})
        return JsonResponse({'reply': 'You do not have any policies yet. You can apply for one from the Policies page.'})

    if any(w in question for w in ['claim', 'claims']):
        if claims.exists():
            lines = []
            for c in claims[:5]:
                lines.append(f"{c.claim_number}: {c.get_incident_type_display()}, R {c.amount_claimed:,.0f}, status: {c.get_status_display()}.")
            return JsonResponse({'reply': f'You have {claims.count()} claim{"s" if claims.count()!=1 else ""}:\n' + '\n'.join(lines)})
        return JsonResponse({'reply': 'You have not submitted any claims. You can submit one from the Claims page.'})

    if any(w in question for w in ['pay', 'payment', 'premium', 'payshap', 'paid']):
        total_out = payments.filter(payment_type='premium').aggregate(Sum('amount'))['amount__sum'] or 0
        total_in = payments.filter(payment_type='payout').aggregate(Sum('amount'))['amount__sum'] or 0
        return JsonResponse({'reply': f'You have paid R {total_out:,.2f} in premiums and received R {total_in:,.2f} in claim payouts. You can pay your premium using PayShap from any policy detail page.'})

    if any(w in question for w in ['limit', 'max', 'minimum', 'range']):
        return JsonResponse({'reply': 'Coverage limits by plan:\nVehicle: R 10,000 - R 500,000\nHome: R 50,000 - R 2,000,000\nLife: R 50,000 - R 5,000,000\nHealth: R 25,000 - R 1,000,000\nBusiness: R 100,000 - R 5,000,000\nTravel: R 5,000 - R 200,000'})

    if any(w in question for w in ['premium', 'calculate', 'cost', 'price', 'how much']):
        return JsonResponse({'reply': 'Your monthly premium is auto-calculated based on your coverage amount and plan type. For example, R 100,000 vehicle cover = about R 125/month. You will see the exact amount before you confirm your policy.'})

    if any(w in question for w in ['hello', 'hi', 'hey', 'help']):
        return JsonResponse({'reply': 'Hi! I am your SIFDS insurance assistant. I can help you with:\n- Your policies and coverage\n- Your claims and their status\n- Your payments and premiums\n- Coverage limits for each plan\n- How premiums are calculated\nWhat would you like to know?'})

    if any(w in question for w in ['document', 'upload', 'file']):
        return JsonResponse({'reply': 'You can upload supporting documents (ID, proof of address, police reports, photos) from the Documents page. Files must be JPG, PNG, or PDF, max 5MB each.'})

    return JsonResponse({'reply': 'I can help with your policies, claims, payments, coverage limits, and premiums. Try asking "What are my policies?" or "How is my premium calculated?"'})
