from c2corg_api.models import es_sync, document_types, document_locale_types
from c2corg_api.models.area import Area
from c2corg_api.models.document import Document, DocumentGeometry
from c2corg_api.models.document_history import DocumentVersion, HistoryMetaData
from c2corg_api.models.route import Route, ROUTE_TYPE
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.utils import windowed_query
from c2corg_api.models.waypoint import WAYPOINT_TYPE
from c2corg_api.scripts.es.es_batch import ElasticBatch
from c2corg_api.search import elasticsearch_config, batch_size, \
    search_documents
from c2corg_api.views.document import add_load_for_profiles
from sqlalchemy.orm import joinedload
import logging

from sqlalchemy.sql.elements import literal

log = logging.getLogger(__name__)


def sync_es(session):
    last_update, date_now = es_sync.get_status(session)

    if not last_update:
        raise Exception('No last update time, run `fill_index` to do an '
                        'initial import into ElasticSearch')

    # get all documents that have changed since the last update
    # TODO also check changes to associations
    changed_documents = get_changed_documents(session, last_update) + \
        get_changed_users(session, last_update)

    if changed_documents:
        sync_documents(session, changed_documents)

    es_sync.mark_as_updated(session, date_now)


def get_changed_documents(session, last_update):
    """Get the documents that have changed since the last update.
    Returns a list of (document_id, document_type) tuples ordered by
    document_type.
    """
    # TODO if there are many changed documents getting all ids is not very
    # efficient. stop in that case and prompt to run `fill_index` manually?
    return session.query(Document.document_id, Document.type). \
        join(DocumentVersion,
             Document.document_id == DocumentVersion.document_id). \
        join(HistoryMetaData,
             HistoryMetaData.id ==
             DocumentVersion.history_metadata_id). \
        filter(HistoryMetaData.written_at >= last_update). \
        group_by(Document.document_id, Document.type). \
        order_by(Document.type). \
        all()


def get_changed_users(session, last_update):
    """Get the users that have changed. Needed to update the profile when
    the user name has changed.
    """
    return session.query(User.id, literal(USERPROFILE_TYPE)). \
        filter(User.last_modified >= last_update). \
        all()


def sync_documents(session, changed_documents):
    client = elasticsearch_config['client']
    batch = ElasticBatch(client, batch_size)
    with batch:
        docs_per_type = get_documents_per_type(changed_documents)
        add_dependent_documents(session, docs_per_type)
        for doc_type, document_ids in docs_per_type.items():
            if document_ids:
                docs = get_documents(session, doc_type, document_ids)
                create_search_documents(doc_type, docs, batch)


def add_dependent_documents(session, docs_per_type):
    add_routes_for_waypoints(session, docs_per_type)


def add_routes_for_waypoints(session, docs_per_type):
    """Add the routes that have one of the waypoints as main waypoints.
    """
    changed_waypoint_ids = docs_per_type.get(WAYPOINT_TYPE, [])
    if not changed_waypoint_ids:
        return

    linked_route_ids = session.query(Route.document_id). \
        filter(Route.main_waypoint_id.in_(changed_waypoint_ids)).all()

    route_ids = docs_per_type.setdefault(ROUTE_TYPE, set())
    route_ids.update(linked_route_ids)


def get_documents_per_type(changed_documents):
    docs_per_type = {}
    for document_id, doc_type in changed_documents:
        docs = docs_per_type.setdefault(doc_type, set())
        docs.add(document_id)
    return docs_per_type


def get_documents(session, doc_type, document_ids=None):
    clazz = document_types[doc_type]
    locales_clazz = document_locale_types[doc_type]

    base_query = session.query(clazz)
    if document_ids:
        base_query = base_query.filter(clazz.document_id.in_(document_ids))

    base_query = base_query. \
        options(joinedload(clazz.locales.of_type(locales_clazz))). \
        options(joinedload(clazz.geometry).load_only(DocumentGeometry.lon_lat))

    if clazz != Area:
        base_query = base_query. \
            options(joinedload(clazz._areas).load_only('document_id'))

    base_query = add_load_for_profiles(base_query, clazz)

    return windowed_query(base_query, Document.document_id, batch_size)


def create_search_documents(doc_type, documents, batch):
    to_search_document = search_documents[doc_type].to_search_document
    index = elasticsearch_config['index']
    n = 0
    for doc in documents:
        batch.add(to_search_document(doc, index))
        n += 1
    log.info('Sent {} document(s) of type {}'.format(n, doc_type))
