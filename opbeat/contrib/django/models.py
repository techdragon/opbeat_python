"""
opbeat.contrib.django.models
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Acts as an implicit hook for Django installs.

:copyright: (c) 2011-2012 Opbeat

Large portions are
:copyright: (c) 2010 by the Sentry Team, see AUTHORS for more details.
:license: BSD, see LICENSE for more details.
"""

from __future__ import absolute_import

import logging
import os
import sys
import warnings

from django.conf import settings as django_settings

import opbeat.instrumentation.control
from opbeat.utils import disabled_due_to_debug, six

logger = logging.getLogger('opbeat.errors.client')


def get_installed_apps():
    """
    Generate a list of modules in settings.INSTALLED_APPS.
    """
    out = set()
    for app in django_settings.INSTALLED_APPS:
        out.add(app)
    return out

default_client_class = 'opbeat.contrib.django.DjangoClient'


def get_client_class(client_path=default_client_class):
    module, class_name = client_path.rsplit('.', 1)
    return getattr(__import__(module, {}, {}, class_name), class_name)


def get_client_config():
    config = getattr(django_settings, 'OPBEAT', {})
    if 'ASYNC' in config:
        warnings.warn(
            'Usage of "ASYNC" configuration is deprecated. Use "ASYNC_MODE"',
            category=DeprecationWarning,
            stacklevel=2,
        )
        config['ASYNC_MODE'] = 'ASYNC'
    return dict(
        servers=config.get('SERVERS', None),
        include_paths=set(
            config.get('INCLUDE_PATHS', [])) | get_installed_apps(),
        exclude_paths=config.get('EXCLUDE_PATHS', None),
        timeout=config.get('TIMEOUT', None),
        hostname=config.get('HOSTNAME', None),
        auto_log_stacks=config.get('AUTO_LOG_STACKS', None),
        string_max_length=config.get('MAX_LENGTH_STRING', None),
        list_max_length=config.get('MAX_LENGTH_LIST', None),
        organization_id=config.get('ORGANIZATION_ID', None),
        app_id=config.get('APP_ID', None),
        secret_token=config.get('SECRET_TOKEN', None),
        transport_class=config.get('TRANSPORT_CLASS', None),
        processors=config.get('PROCESSORS', None),
        traces_send_freq_secs=config.get('TRACES_SEND_FREQ_SEC', None),
        async_mode=config.get('ASYNC_MODE', None),
        instrument_django_middleware=config.get('INSTRUMENT_DJANGO_MIDDLEWARE'),
    )


_client = (None, None)


def get_client(client=None):
    """
    Get an Opbeat client.

    :param client:
    :return:
    :rtype: opbeat.base.Client
    """
    global _client

    tmp_client = client is not None
    if not tmp_client:
        config = getattr(django_settings, 'OPBEAT', {})
        client = config.get('CLIENT', default_client_class)

    if _client[0] != client:
        client_class = get_client_class(client)
        instance = client_class(**get_client_config())
        if not tmp_client:
            _client = (client, instance)
        return instance
    return _client[1]


def opbeat_exception_handler(request=None, **kwargs):
    def actually_do_stuff(request=None, **kwargs):
        exc_info = sys.exc_info()
        try:
            if (
                disabled_due_to_debug(
                    getattr(django_settings, 'OPBEAT', {}),
                    django_settings.DEBUG
                )
                or getattr(exc_info[1], 'skip_opbeat', False)
            ):
                return

            get_client().capture('Exception', exc_info=exc_info,
                                 request=request)
        except Exception as exc:
            try:
                logger.exception(u'Unable to process log entry: %s' % (exc,))
            except Exception as exc:
                warnings.warn(u'Unable to process log entry: %s' % (exc,))
        finally:
            try:
                del exc_info
            except Exception as e:
                logger.exception(e)

    return actually_do_stuff(request, **kwargs)


def register_handlers():
    from django.core.signals import got_request_exception

    # Connect to Django's internal signal handler
    got_request_exception.connect(opbeat_exception_handler)

    # If Celery is installed, register a signal handler
    if 'djcelery' in django_settings.INSTALLED_APPS:
        from opbeat.contrib.celery import register_signal

        try:
            register_signal(get_client())
        except Exception as e:
            logger.exception('Failed installing django-celery hook: %s' % e)

    # Instrument to get traces
    skip_env_var = 'SKIP_INSTRUMENT'
    if skip_env_var in os.environ:
        logger.debug("Skipping instrumentation. %s is set.", skip_env_var)
    else:
        opbeat.instrumentation.control.instrument()


if 'opbeat.contrib.django' in django_settings.INSTALLED_APPS:
    register_handlers()
