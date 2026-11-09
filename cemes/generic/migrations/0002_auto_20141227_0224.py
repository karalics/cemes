from django.db import migrations, models

import cemes.core.fields


class Migration(migrations.Migration):

    dependencies = [
        ("generic", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="assignedkeyword",
            name="_order",
            field=cemes.core.fields.OrderField(null=True, verbose_name="Order"),
            preserve_default=True,
        ),
    ]
