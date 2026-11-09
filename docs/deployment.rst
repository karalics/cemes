==========
Deployment
==========

Deployment of a Cemes site to production is mostly identical to
deploying a regular Django site. For serving static content, Cemes
makes full use of Django's ``staticfiles`` app. For more information,
see the Django docs for
`deployment <https://docs.djangoproject.com/en/dev/howto/deployment/>`_ and
`staticfiles <https://docs.djangoproject.com/en/dev/howto/static-files/>`_.

Cemes's only customization to the deployment process is adding built-in
support for a ``local_settings.py`` file. This file is not kept under version
control and you can use it to include production-only configuration.

.. versionchanged:: 5.0
   Previously Cemes used to ship a fabfile for automatic deployments. It
   has been removed in favor of regular Django deployment methods.
