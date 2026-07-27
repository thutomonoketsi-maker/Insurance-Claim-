# core/signals.py
from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.dispatch import receiver
from .models import UserProfile

# This is already handled in models.py with @receiver decorators
# Just keep this file for the ready() method in apps.py