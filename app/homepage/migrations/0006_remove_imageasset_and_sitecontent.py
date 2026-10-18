# Generated with the removal of the GrapesJS homepage editor. The site content
# those two models held is replaced by the templates the page now always
# renders, so a troop's saved editor content is intentionally discarded.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('homepage', '0005_timelineactivity'),
    ]

    operations = [
        migrations.DeleteModel(
            name='ImageAsset',
        ),
        migrations.DeleteModel(
            name='SiteContent',
        ),
    ]
