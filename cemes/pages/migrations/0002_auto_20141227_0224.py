from django.db import migrations, models

import cemes.core.fields
import cemes.pages.fields


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="page",
            name="_order",
            field=cemes.core.fields.OrderField(null=True, verbose_name="Order"),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name="page",
            name="in_menus",
            field=cemes.pages.fields.MenusField(
                max_length=100, null=True, verbose_name="Show in menus", blank=True
            ),
            preserve_default=True,
        ),
    ]
