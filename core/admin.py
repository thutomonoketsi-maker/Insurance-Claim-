from django.contrib import admin
from .models import UserProfile, Policy, Claim, Payment, Document, Notification, ActivityLog


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'status', 'phone']
    list_filter = ['role', 'status']
    search_fields = ['user__username', 'user__email']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Policy)
class PolicyAdmin(admin.ModelAdmin):
    list_display = ['policy_number', 'user', 'policy_type', 'status', 'created_at']
    list_filter = ['status', 'policy_type']
    search_fields = ['policy_number', 'user__username']


@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin):
    list_display = ['claim_number', 'user', 'status', 'fraud_score', 'fraud_flagged', 'submitted_at']
    list_filter = ['status', 'fraud_flagged']
    search_fields = ['claim_number', 'user__username']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['payment_number', 'user', 'amount', 'payment_type', 'status', 'created_at']
    list_filter = ['status', 'payment_type']
    search_fields = ['payment_number', 'user__username']


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ['document_number', 'user', 'document_type', 'status', 'uploaded_at']
    list_filter = ['status', 'document_type']
    search_fields = ['document_number', 'user__username']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'notification_type', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read']


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'action', 'created_at']
    list_filter = ['action']
