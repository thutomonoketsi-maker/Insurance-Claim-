from django.urls import path
from . import views

urlpatterns = [
    # LANDING PAGES
    path('', views.home, name='home'),
    path('features/', views.features, name='features'),
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),

    # AUTH
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),

    # CUSTOMER (POLICYHOLDER)
    path('dashboard/customer/', views.customer_dashboard, name='customer_dashboard'),
    path('dashboard/customer/policies/', views.customer_policies, name='customer_policies'),
    path('dashboard/customer/policies/<int:policy_id>/', views.customer_policy_detail, name='customer_policy_detail'),
    path('dashboard/customer/purchase/', views.customer_purchase_policy, name='customer_purchase_policy'),
    path('dashboard/customer/policies/<int:policy_id>/pay/', views.customer_payshap_payment, name='customer_payshap_payment'),
    path('dashboard/customer/policies/<int:policy_id>/renew/', views.customer_renew_policy, name='customer_renew_policy'),
    path('dashboard/customer/policies/<int:policy_id>/cancel/', views.customer_cancel_policy, name='customer_cancel_policy'),
    path('dashboard/customer/claims/', views.customer_claims, name='customer_claims'),
    path('dashboard/customer/claims/submit/', views.customer_submit_claim, name='customer_submit_claim'),
    path('dashboard/customer/claims/<int:claim_id>/', views.customer_claim_detail, name='customer_claim_detail'),
    path('dashboard/customer/payments/', views.customer_payments, name='customer_payments'),
    path('dashboard/customer/documents/', views.customer_documents, name='customer_documents'),
    path('dashboard/customer/notifications/', views.customer_notifications, name='customer_notifications'),
    path('dashboard/customer/profile/', views.customer_profile, name='customer_profile'),
    path('dashboard/customer/settings/', views.customer_settings, name='customer_settings'),
    path('dashboard/customer/copilot/', views.copilot_chat, name='copilot_chat'),

    # STAFF
    path('dashboard/staff/', views.staff_dashboard, name='staff_dashboard'),
    path('staff/applications/', views.staff_applications, name='staff_applications'),
    path('staff/applications/<int:policy_id>/', views.staff_process_application, name='staff_process_application'),
    path('staff/claims/', views.staff_claims, name='staff_claims'),
    path('staff/claims/<int:claim_id>/review/', views.staff_claim_review, name='staff_claim_review'),
    path('staff/payments/', views.staff_payments, name='staff_payments'),
    path('staff/payments/create/', views.staff_create_payment, name='staff_create_payment'),
    path('staff/documents/', views.staff_documents, name='staff_documents'),
    path('staff/documents/<int:document_id>/', views.staff_verify_document, name='staff_verify_document'),
    path('staff/profile/', views.staff_profile, name='staff_profile'),

    # INVESTIGATOR
    path('dashboard/investigator/', views.investigator_dashboard, name='investigator_dashboard'),
    path('investigator/cases/', views.investigator_cases, name='investigator_cases'),
    path('investigator/cases/<int:claim_id>/', views.investigator_case_detail, name='investigator_case_detail'),
    path('investigator/profile/', views.investigator_profile, name='investigator_profile'),

    # ADMIN
    path('admin/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin/users/', views.admin_users, name='admin_users'),
    path('admin/users/<int:user_id>/', views.admin_user_detail, name='admin_user_detail'),
    path('admin/policies/', views.admin_policies, name='admin_policies'),
    path('admin/claims/', views.admin_claims, name='admin_claims'),
    path('admin/payments/', views.admin_payments, name='admin_payments'),
    path('admin/staff/', views.admin_staff, name='admin_staff'),
    path('admin/staff/add/', views.admin_add_staff, name='admin_add_staff'),
    path('admin/logs/', views.admin_logs, name='admin_logs'),
    path('admin/profile/', views.admin_profile, name='admin_profile'),
]
