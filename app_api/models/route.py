from sqlalchemy import (
    Column,
    Integer,
    SmallInteger,
    String,
    ForeignKey,
    Enum
    )

from colanderalchemy import SQLAlchemySchemaNode

from . import schema
from utils import copy_attributes
from document import (
    ArchiveDocument, Document, DocumentLocale, ArchiveDocumentLocale)

# TODO: move to a common place for outings etc.
activities = [
    'skitouring',
    'snow_ice_mixed',
    'mountain_climbing',
    'rock_climbing',
    'ice_climbing',
    'hiking',
    'snowshoeing',
    'paragliding',
    'mountain_biking',
    'via_ferrata'
    ]


class _RouteMixin(object):
    activities = Column(
        Enum(name='activities', inherit_schema=True, *activities),
        nullable=False)

    height = Column(SmallInteger)

    __mapper_args__ = {
        'polymorphic_identity': 'r'
    }


class Route(_RouteMixin, Document):
    """
    """
    __tablename__ = 'routes'

    document_id = Column(
        Integer,
        ForeignKey(schema + '.documents.document_id'), primary_key=True)

    _ATTRIBUTES = ['activities', 'height']

    def to_archive(self):
        route = ArchiveRoute()
        super(Route, self).to_archive(route)
        copy_attributes(self, route, Route._ATTRIBUTES)

        return route


class ArchiveRoute(_RouteMixin, ArchiveDocument):
    """
    """
    __tablename__ = 'routes_archives'

    id = Column(
        Integer,
        ForeignKey(schema + '.documents_archives.id'), primary_key=True)


class _RouteLocaleMixin(object):

    gear = Column(String)

    __mapper_args__ = {
        'polymorphic_identity': 'r'
    }


class RouteLocale(_RouteLocaleMixin, DocumentLocale):
    """
    """
    __tablename__ = 'routes_i18n'

    id = Column(
                Integer,
                ForeignKey(schema + '.documents_i18n.id'), primary_key=True)

    _ATTRIBUTES = ['gear']

    def to_archive(self):
        locale = ArchiveRouteLocale()
        super(RouteLocale, self).to_archive(locale)
        copy_attributes(self, locale, RouteLocale._ATTRIBUTES)

        return locale


class ArchiveRouteLocale(_RouteLocaleMixin, ArchiveDocumentLocale):
    """
    """
    __tablename__ = 'routes_i18n_archives'

    id = Column(
        Integer,
        ForeignKey(schema + '.documents_i18n_archives.id'), primary_key=True)


schema_route_locale = SQLAlchemySchemaNode(
    RouteLocale,
    # whitelisted attributes
    includes=['culture', 'title', 'description', 'gear'])

schema_route = SQLAlchemySchemaNode(
    Route,
    # whitelisted attributes
    includes=[
        'document_id', 'activities', 'height', 'locales'],
    overrides={
        'document_id': {
            'missing': None
        },
        'locales': {
            'children': [schema_route_locale]
        }
    })
