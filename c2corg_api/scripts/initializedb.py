import os
import sys
import transaction
from c2corg_api.models.es_sync import ESSyncStatus

from sqlalchemy import engine_from_config

from pyramid.paster import (
    get_appsettings,
    setup_logging,
    )

from pyramid.scripts.common import parse_vars

from c2corg_api.models import *  # noqa
from c2corg_common.attributes import default_langs


def usage(argv):
    cmd = os.path.basename(argv[0])
    print('usage: %s <config_uri> [var=value]\n'
          '(example: "%s development.ini")' % (cmd, cmd))
    sys.exit(1)


def main(argv=sys.argv):
    if len(argv) < 2:
        usage(argv)
    config_uri = argv[1]
    options = parse_vars(argv[2:])
    setup_logging(config_uri)
    settings = get_appsettings(config_uri, options=options)
    engine = engine_from_config(settings, 'sqlalchemy.')
    DBSession.configure(bind=engine)
    setup_db(engine, DBSession)


def setup_db(engine, session):
    Base.metadata.create_all(engine, checkfirst=True)

    with transaction.manager:
        # add default languages
        session.add_all([
            document.Lang(lang=lang) for lang in default_langs
        ])

        # add a default status for the ElasticSearch synchronization
        session.add(ESSyncStatus())
