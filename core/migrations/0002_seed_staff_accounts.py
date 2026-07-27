from django.db import migrations


def seed_staff_accounts(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    UserProfile = apps.get_model('core', 'UserProfile')

    accounts = [
        {
            'username': 'admin',
            'email': 'admin@sifds.co.za',
            'password': 'Admin@12345',
            'first_name': 'System',
            'last_name': 'Administrator',
            'role': 'administrator',
        },
        {
            'username': 'staff',
            'email': 'staff@sifds.co.za',
            'password': 'Staff@12345',
            'first_name': 'Staff',
            'last_name': 'Member',
            'role': 'staff',
        },
        {
            'username': 'investigator',
            'email': 'investigator@sifds.co.za',
            'password': 'Invest@12345',
            'first_name': 'Lead',
            'last_name': 'Investigator',
            'role': 'investigator',
        },
    ]

    for acc in accounts:
        user = User.objects.create_user(
            username=acc['username'],
            email=acc['email'],
            password=acc['password'],
            first_name=acc['first_name'],
            last_name=acc['last_name'],
        )
        UserProfile.objects.create(
            user=user,
            role=acc['role'],
            status='active',
        )


def remove_staff_accounts(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    User.objects.filter(username__in=['admin', 'staff', 'investigator']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_staff_accounts, remove_staff_accounts),
    ]
