# Generated by Django 4.1.7 on 2023-03-05 08:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('members', '0011_alter_customuser_address_alter_customuser_note'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='customgroup',
            options={'verbose_name': 'groupe', 'verbose_name_plural': 'groupes'},
        ),
        migrations.AlterModelOptions(
            name='customuser',
            options={'verbose_name': 'utilisateur', 'verbose_name_plural': 'utilisateurs'},
        ),
        migrations.AlterField(
            model_name='customuser',
            name='note',
            field=models.TextField(blank=True, max_length=500, null=True),
        ),
    ]
