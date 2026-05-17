import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = 'Creates a superuser from environment variables. Safe to run on every deploy.'

    def handle(self, *args, **options):
        User = get_user_model()

        phone_number = os.environ.get('SUPERUSER_PHONE')
        password = os.environ.get('SUPERUSER_PASSWORD')
        email = os.environ.get('SUPERUSER_EMAIL', '')

        if not phone_number or not password:
            self.stdout.write(self.style.WARNING(
                'Skipping superuser creation: SUPERUSER_PHONE and SUPERUSER_PASSWORD '
                'environment variables are not set.'
            ))
            return

        if User.objects.filter(phone_number=phone_number).exists():
            self.stdout.write(self.style.SUCCESS(
                f'Superuser with phone {phone_number} already exists. Skipping.'
            ))
            return

        User.objects.create_superuser(
            phone_number=phone_number,
            password=password,
            email=email,
        )
        self.stdout.write(self.style.SUCCESS(
            f'Superuser created successfully with phone {phone_number}.'
        ))
