=========
Cemes
=========

Welcome to the Cemes project. To learn more about Cemes please
read the :doc:`overview` which contains a feature list, installation
guide and other general information. To get an idea of the types of
sites possible with Cemes, have a look at the `gallery of sites
powered by Cemes <http://mezzanine.jupo.org/sites/>`_.

.. note::
    A working knowledge of `Django <https://www.djangoproject.com/>`_
    is required to work with Cemes and the documentation assumes as
    much. If you're new to Django, you'll need to work through the
    :doc:`Django tutorial <django:intro/tutorial01>`
    before being able to understand the concepts used throughout the
    Cemes documentation. *A mantra for working with Cemes:
    Cemes Is Just Django* - `Ken Bolton <http://bscientific.org/>`_,
    Cemes core team member.

**Front-end developers** might be interested in Cemes's ability for
content authors to edit content directly within a page while viewing it
on the website. You can read about this and how to implement this feature
within templates under :doc:`inline-editing`.

**Back-end developers** can get a better technical overview of how
content is managed and how to customize Cemes in general by
reading about Cemes's :doc:`content-architecture` which describes
the main components and how to extend them with your own custom
content types, or by reading about :doc:`model-customization` for
implementing more low-level customizations as required. There is also
a section on the :doc:`admin-customization` provided by Cemes, as
well as a :doc:`model-graph` depicting the relationships between all
the models.

**System administrators** can find out about some of the production
requirements and operations in the :doc:`deployment` and
:doc:`caching-strategy` sections.

**Further reading** includes :doc:`frequently-asked-questions`,
:doc:`utilities`, a section on :doc:`user-accounts`, support for
:doc:`multi-lingual-sites`, information about Cemes's
:doc:`search-engine`, and a section on Cemes's
:doc:`configuration` which outlines the various settings for
configuring Cemes. Lastly, you can learn about
:doc:`blog-importing` into Cemes, :doc:`twitter-integration`, or
just browse the auto-generated docs for each of Cemes's
:doc:`packages`.

Table Of Contents
=================

.. toctree::
    :maxdepth: 2

    overview
    content-architecture
    model-customization
    admin-customization
    multi-lingual-sites
    utilities
    model-graph
    inline-editing
    caching-strategy
    multi-tenancy
    deployment
    frequently-asked-questions
    user-accounts
    search-engine
    configuration
    blog-importing
    twitter-integration
    packages
    colophon
