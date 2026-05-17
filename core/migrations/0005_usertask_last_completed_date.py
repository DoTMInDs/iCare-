from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_referralcode_referralcommission_teammember_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='usertask',
            name='last_completed_date',
            field=models.DateField(
                blank=True,
                null=True,
                help_text='Date task was last completed. Used to enforce one completion per day.'
            ),
        ),
    ]
