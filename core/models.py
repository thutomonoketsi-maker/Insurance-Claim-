from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('policyholder', 'Policyholder'),
        ('staff', 'Staff'),
        ('investigator', 'Investigator'),
        ('administrator', 'Administrator'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('disabled', 'Disabled'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='policyholder')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')

    phone = models.CharField(max_length=20, blank=True)
    id_number = models.CharField(max_length=20, blank=True)

    address = models.TextField(blank=True)
    city = models.CharField(max_length=50, blank=True)
    province = models.CharField(max_length=50, blank=True)
    postal_code = models.CharField(max_length=10, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.get_role_display()})"


class Policy(models.Model):
    POLICY_TYPES = [
        ('vehicle', 'Vehicle Insurance'),
        ('home', 'Home Insurance'),
        ('life', 'Life Insurance'),
        ('health', 'Health Insurance'),
        ('business', 'Business Insurance'),
        ('travel', 'Travel Insurance'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]

    policy_number = models.CharField(max_length=50, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='policies')
    policy_type = models.CharField(max_length=20, choices=POLICY_TYPES)
    coverage_amount = models.DecimalField(max_digits=15, decimal_places=2)
    premium_amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_frequency = models.CharField(max_length=20, default='monthly')

    start_date = models.DateField()
    end_date = models.DateField()
    renewal_date = models.DateField()

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    beneficiary_name = models.CharField(max_length=200, blank=True)
    beneficiary_id = models.CharField(max_length=20, blank=True)
    beneficiary_relationship = models.CharField(max_length=50, blank=True)
    beneficiary_phone = models.CharField(max_length=20, blank=True)
    beneficiary_email = models.EmailField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.policy_number} - {self.get_policy_type_display()}"

    def type_display(self):
        return self.get_policy_type_display()


class Claim(models.Model):
    INCIDENT_TYPES = [
        ('accident', 'Accident'),
        ('theft', 'Theft'),
        ('damage', 'Damage'),
        ('fire', 'Fire'),
        ('natural_disaster', 'Natural Disaster'),
        ('medical', 'Medical Emergency'),
        ('death', 'Death Claim'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('submitted', 'Submitted'),
        ('under_review', 'Under Review'),
        ('investigation', 'Under Investigation'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('paid', 'Paid Out'),
    ]

    claim_number = models.CharField(max_length=50, unique=True)
    policy = models.ForeignKey(Policy, on_delete=models.CASCADE, related_name='claims')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='claims')

    incident_type = models.CharField(max_length=20, choices=INCIDENT_TYPES)
    incident_date = models.DateField()
    incident_description = models.TextField()
    incident_location = models.CharField(max_length=255, blank=True)

    amount_claimed = models.DecimalField(max_digits=15, decimal_places=2)
    amount_approved = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='submitted')

    fraud_score = models.IntegerField(default=0)
    fraud_flagged = models.BooleanField(default=False)

    investigator = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='investigated_claims'
    )
    investigation_notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)

    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.claim_number} - {self.get_status_display()}"

    def incident_type_display(self):
        return self.get_incident_type_display()


class Payment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]

    PAYMENT_METHODS = [
        ('payshap', 'PayShap'),
        ('card', 'Card'),
        ('bank_transfer', 'Bank Transfer'),
        ('debit_order', 'Debit Order'),
    ]

    PAYMENT_TYPES = [
        ('premium', 'Premium'),
        ('payout', 'Claim Payout'),
    ]

    payment_number = models.CharField(max_length=50, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    policy = models.ForeignKey(
        Policy, on_delete=models.CASCADE, related_name='payments',
        null=True, blank=True
    )
    claim = models.ForeignKey(
        Claim, on_delete=models.CASCADE, related_name='payments',
        null=True, blank=True
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPES, default='premium')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    due_date = models.DateField()
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.payment_number} - {self.get_status_display()}"


class Document(models.Model):
    DOCUMENT_TYPES = [
        ('id_document', 'ID Document'),
        ('proof_of_address', 'Proof of Address'),
        ('police_report', 'Police Report'),
        ('accident_photos', 'Accident Photos'),
        ('medical_report', 'Medical Report'),
        ('death_certificate', 'Death Certificate'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    ]

    document_number = models.CharField(max_length=50, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='documents')
    policy = models.ForeignKey(
        Policy, on_delete=models.CASCADE, related_name='documents',
        null=True, blank=True
    )
    claim = models.ForeignKey(
        Claim, on_delete=models.CASCADE, related_name='documents',
        null=True, blank=True
    )

    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPES)
    document_name = models.CharField(max_length=255)
    document_file = models.FileField(upload_to='documents/%Y/%m/%d/')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    verified_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='verified_documents'
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.document_number} - {self.document_name}"


class Notification(models.Model):
    TYPES = [
        ('info', 'Info'),
        ('success', 'Success'),
        ('warning', 'Warning'),
        ('danger', 'Danger'),
    ]

    CATEGORIES = [
        ('policy', 'Policy'),
        ('claim', 'Claim'),
        ('payment', 'Payment'),
        ('document', 'Document'),
        ('fraud', 'Fraud'),
        ('system', 'System'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(max_length=20, choices=TYPES, default='info')
    category = models.CharField(max_length=20, choices=CATEGORIES, default='system')

    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    related_claim = models.ForeignKey(
        Claim, on_delete=models.SET_NULL, null=True, blank=True
    )
    related_policy = models.ForeignKey(
        Policy, on_delete=models.SET_NULL, null=True, blank=True
    )
    related_payment = models.ForeignKey(
        Payment, on_delete=models.SET_NULL, null=True, blank=True
    )

    action_url = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} - {self.user.username}"


class ActivityLog(models.Model):
    ACTIONS = [
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('approve', 'Approve'),
        ('reject', 'Reject'),
    ]

    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='activity_logs'
    )
    action = models.CharField(max_length=20, choices=ACTIONS)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.get_action_display()} - {self.created_at:%Y-%m-%d %H:%M}"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()
