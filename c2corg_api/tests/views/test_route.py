import datetime
import json

from c2corg_api.models.area import Area
from c2corg_api.models.area_association import AreaAssociation
from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.models.topo_map import TopoMap
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.tests.search import reset_search_index
from c2corg_api.views.route import check_title_prefix
from c2corg_common.attributes import quality_types
from shapely.geometry import shape, LineString

from c2corg_api.models.route import (
    Route, RouteLocale, ArchiveRoute, ArchiveRouteLocale, ROUTE_TYPE)
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.views.document import DocumentRest

from c2corg_api.tests.views import BaseDocumentTestRest
from shapely.geometry.point import Point


class TestRouteRest(BaseDocumentTestRest):

    def setUp(self):  # noqa
        self.set_prefix_and_model(
            "/routes", ROUTE_TYPE, Route, ArchiveRoute, ArchiveRouteLocale)
        BaseDocumentTestRest.setUp(self)
        self._add_test_data()

    def test_get_collection(self):
        body = self.get_collection()
        doc = body['documents'][0]
        self.assertNotIn('climbing_outdoor_type', doc)
        self.assertNotIn('elevation_min', doc)

    def test_get_collection_paginated(self):
        self.app.get("/routes?offset=invalid", status=400)

        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 0}), [], 4)

        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 1}),
            [self.route4.document_id], 4)
        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 2}),
            [self.route4.document_id, self.route3.document_id], 4)
        self.assertResultsEqual(
            self.get_collection({'offset': 1, 'limit': 2}),
            [self.route3.document_id, self.route2.document_id], 4)

    def test_get_collection_lang(self):
        self.get_collection_lang()

    def test_get_collection_search(self):
        reset_search_index(self.session)

        body = self.get_collection_search({'act': 'skitouring'})
        self.assertEqual(body.get('total'), 4)
        self.assertEqual(len(body.get('documents')), 4)

        body = self.get_collection_search({'act': 'skitouring', 'limit': 2})
        self.assertEqual(body.get('total'), 4)
        self.assertEqual(len(body.get('documents')), 2)

        body = self.get_collection_search({'hdif': '700,900'})
        self.assertEqual(body.get('total'), 2)

    def test_get(self):
        body = self.get(self.route)
        self.assertEqual(
            body.get('activities'), self.route.activities)
        self._assert_geometry(body)
        self.assertNotIn('climbing_outdoor_type', body)
        self.assertIn('elevation_min', body)

        locale_en = self.get_locale('en', body.get('locales'))
        self.assertEqual(
            'Main waypoint title',
            locale_en.get('title_prefix'))

        self.assertIn('main_waypoint_id', body)
        self.assertIn('associations', body)
        associations = body.get('associations')

        linked_waypoints = associations.get('waypoints')
        self.assertEqual(1, len(linked_waypoints))
        self.assertEqual(
            self.waypoint.document_id, linked_waypoints[0].get('document_id'))

        linked_routes = associations.get('routes')
        self.assertEqual(1, len(linked_routes))
        self.assertEqual(
            self.route4.document_id, linked_routes[0].get('document_id'))

        recent_outings = associations.get('recent_outings')
        self.assertEqual(1, recent_outings['total'])
        self.assertEqual(1, len(recent_outings['outings']))
        self.assertEqual(
            self.outing1.document_id,
            recent_outings['outings'][0].get('document_id'))
        self.assertIn('type', recent_outings['outings'][0])

        self.assertIn('maps', body)
        topo_map = body.get('maps')[0]
        self.assertEqual(topo_map.get('code'), '3232ET')
        self.assertEqual(topo_map.get('locales')[0].get('title'), 'Belley')

    def test_get_version(self):
        self.get_version(self.route, self.route_version)

    def test_get_lang(self):
        body = self.get_lang(self.route)

        self.assertEqual(
            'Mont Blanc from the air',
            body.get('locales')[0].get('title'))
        self.assertEqual(
            'Main waypoint title',
            body.get('locales')[0].get('title_prefix'))

    def test_get_new_lang(self):
        self.get_new_lang(self.route)

    def test_get_404(self):
        self.get_404()

    def test_get_edit(self):
        response = self.app.get(self._prefix + '/' +
                                str(self.route.document_id) + '?e=1',
                                status=200)
        body = response.json

        self.assertIn('maps', body)
        self.assertNotIn('areas', body)
        self.assertIn('associations', body)
        associations = body['associations']
        self.assertIn('waypoints', associations)
        self.assertIn('routes', associations)
        self.assertNotIn('images', associations)
        self.assertNotIn('users', associations)

    def test_post_error(self):
        body = self.post_error({})
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertCorniceMissing(errors[0], 'activities')

    def test_post_empty_activities_error(self):
        body = self.post_error({
            'activities': []
        })
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertEqual(
            errors[0].get('description'), 'Shorter than minimum length 1')
        self.assertEqual(errors[0].get('name'), 'activities')

    def test_post_invalid_activity(self):
        body_post = {
            'activities': ['cooking'],
            'elevation_min': 700,
            'elevation_max': 1500,
            'height_diff_up': 800,
            'height_diff_down': 800,
            'durations': ['1'],
            'geometry': {
                'id': 5678, 'version': 6789,
                'geom_detail':
                    '{"type": "LineString", "coordinates": ' +
                    '[[635956, 5723604], [635966, 5723644]]}'
            },
            'locales': [
                {'lang': 'en', 'title': 'Some nice loop'}
            ]
        }
        body = self.post_error(body_post)
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertEqual(
            errors[0].get('description'), 'invalid value: cooking')
        self.assertEqual(errors[0].get('name'), 'activities')

    def test_post_missing_title(self):
        body_post = {
            'activities': ['skitouring'],
            'elevation_min': 700,
            'elevation_max': 1500,
            'height_diff_up': 800,
            'height_diff_down': 800,
            'durations': ['1'],
            'geometry': {
                'id': 5678, 'version': 6789,
                'geom_detail':
                    '{"type": "LineString", "coordinates": ' +
                    '[[635956, 5723604], [635966, 5723644]]}'
            },
            'locales': [
                {'lang': 'en'}
            ]
        }
        body = self.post_missing_title(body_post)
        errors = body.get('errors')
        self.assertEqual(len(errors), 2)
        self.assertCorniceRequired(errors[1], 'locales')

    def test_post_non_whitelisted_attribute(self):
        body = {
            'activities': ['hiking'],
            'protected': True,
            'elevation_min': 700,
            'elevation_max': 1500,
            'height_diff_up': 800,
            'height_diff_down': 800,
            'durations': ['1'],
            'geometry': {
                'id': 5678, 'version': 6789,
                'geom_detail':
                    '{"type": "LineString", "coordinates": ' +
                    '[[635956, 5723604], [635966, 5723644]]}'
            },
            'locales': [
                {'lang': 'en', 'title': 'Some nice loop',
                 'gear': 'shoes'}
            ]
        }
        self.post_non_whitelisted_attribute(body)

    def test_post_missing_content_type(self):
        self.post_missing_content_type({})

    def test_post_success(self):
        body = {
            'main_waypoint_id': self.waypoint.document_id,
            'activities': ['hiking', 'skitouring'],
            'elevation_min': 700,
            'elevation_max': 1500,
            'height_diff_up': 800,
            'height_diff_down': 800,
            'durations': ['1'],
            'geometry': {
                'id': 5678, 'version': 6789,
                'geom_detail':
                    '{"type": "LineString", "coordinates": ' +
                    '[[635956, 5723604], [635966, 5723644]]}'
            },
            'locales': [
                {'lang': 'en', 'title': 'Some nice loop',
                 'gear': 'shoes'}
            ],
            'associations': {
                'waypoints': [{'document_id': self.waypoint.document_id}]
            }
        }
        body, doc = self.post_success(body)
        self._assert_geometry(body)
        self._assert_default_geometry(body)

        version = doc.versions[0]

        archive_route = version.document_archive
        self.assertEqual(archive_route.activities, ['hiking', 'skitouring'])
        self.assertEqual(archive_route.elevation_max, 1500)

        archive_locale = version.document_locales_archive
        self.assertEqual(archive_locale.lang, 'en')
        self.assertEqual(archive_locale.title, 'Some nice loop')

        archive_geometry = version.document_geometry_archive
        self.assertEqual(archive_geometry.version, doc.geometry.version)
        self.assertIsNotNone(archive_geometry.geom_detail)
        self.assertIsNotNone(archive_geometry.geom)

        self.assertEqual(doc.main_waypoint_id, self.waypoint.document_id)
        self.assertEqual(
            body.get('main_waypoint_id'), self.waypoint.document_id)
        self.assertEqual(
            archive_route.main_waypoint_id, self.waypoint.document_id)

        self.assertEqual(
            self.waypoint.locales[0].title, doc.locales[0].title_prefix)

        # check that a link for intersecting areas is created
        links = self.session.query(AreaAssociation). \
            filter(
                AreaAssociation.document_id == doc.document_id). \
            all()
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].area_id, self.area1.document_id)

        # check that a link to the main waypoint is created
        association_main_wp = self.session.query(Association).get(
            (self.waypoint.document_id, doc.document_id))
        self.assertIsNotNone(association_main_wp)

        association_main_wp_log = self.session.query(AssociationLog). \
            filter(AssociationLog.parent_document_id ==
                   self.waypoint.document_id). \
            filter(AssociationLog.child_document_id ==
                   doc.document_id). \
            first()
        self.assertIsNotNone(association_main_wp_log)

    def test_post_default_geom_multi_line(self):
        body = {
            'main_waypoint_id': self.waypoint.document_id,
            'activities': ['hiking', 'skitouring'],
            'elevation_min': 700,
            'elevation_max': 1500,
            'height_diff_up': 800,
            'height_diff_down': 800,
            'durations': ['1'],
            'geometry': {
                'id': 5678, 'version': 6789,
                'geom_detail':
                    '{"type": "MultiLineString", "coordinates": ' +
                    '[[[635956, 5723604], [635966, 5723644]], '
                    '[[635966, 5723614], [635976, 5723654]]]}'
            },
            'locales': [
                {'lang': 'en', 'title': 'Some nice loop',
                 'gear': 'shoes'}
            ],
            'associations': {
                'waypoints': [{'document_id': self.waypoint.document_id}]
            }
        }
        body, doc = self.post_success(body)
        self.assertIsNotNone(doc.geometry.geom)
        self.assertIsNotNone(doc.geometry.geom_detail)
        self._assert_default_geometry(body)

    def test_post_default_geom_from_main_wp(self):
        body = {
            'main_waypoint_id': self.waypoint.document_id,
            'activities': ['hiking', 'skitouring'],
            'elevation_min': 700,
            'elevation_max': 1500,
            'height_diff_up': 800,
            'height_diff_down': 800,
            'durations': ['1'],
            'locales': [
                {'lang': 'en', 'title': 'Some nice loop',
                 'gear': 'shoes'}
            ],
            'associations': {
                'waypoints': [{'document_id': self.waypoint.document_id}]
            }
        }
        body, doc = self.post_success(body)
        self.assertIsNotNone(doc.geometry.geom)
        self.assertIsNone(doc.geometry.geom_detail)
        self._assert_default_geometry(body, x=635956, y=5723604)

    def test_post_main_wp_without_association(self):
        body_post = {
            'main_waypoint_id': self.waypoint.document_id,
            'activities': ['hiking', 'skitouring'],
            'elevation_min': 700,
            'elevation_max': 1500,
            'height_diff_up': 800,
            'height_diff_down': 800,
            'durations': ['1'],
            'locales': [
                {'lang': 'en', 'title': 'Some nice loop',
                 'gear': 'shoes'}
            ]
            # no association for the main waypoint
        }
        body = self.post_error(body_post)
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertError(
            errors, 'main_waypoint_id', 'no association for the main waypoint')

    def test_put_wrong_document_id(self):
        body = {
            'document': {
                'document_id': '-9999',
                'version': self.route.version,
                'activities': ['hiking'],
                'elevation_min': 700,
                'elevation_max': 1500,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'durations': ['1'],
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'gear': 'none',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_document_id(body)

    def test_put_wrong_document_version(self):
        body = {
            'document': {
                'document_id': self.route.document_id,
                'version': -9999,
                'activities': ['skitouring'],
                'elevation_min': 700,
                'elevation_max': 1600,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'durations': ['1'],
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'gear': 'none',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_version(body, self.route.document_id)

    def test_put_wrong_locale_version(self):
        body = {
            'document': {
                'document_id': self.route.document_id,
                'version': self.route.version,
                'activities': ['skitouring'],
                'elevation_min': 700,
                'elevation_max': 1600,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'durations': ['1'],
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'gear': 'none',
                     'version': -9999}
                ]
            }
        }
        self.put_wrong_version(body, self.route.document_id)

    def test_put_wrong_ids(self):
        body = {
            'document': {
                'document_id': self.route.document_id,
                'version': self.route.version,
                'activities': ['skitouring'],
                'elevation_min': 700,
                'elevation_max': 1600,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'durations': ['1'],
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'gear': 'none',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_ids(body, self.route.document_id)

    def test_put_no_document(self):
        self.put_put_no_document(self.route.document_id)

    def test_put_success_all(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.route.document_id,
                'version': self.route.version,
                'quality': quality_types[1],
                'activities': ['skitouring'],
                'elevation_min': 700,
                'elevation_max': 1600,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'durations': ['1'],
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'gear': 'none',
                     'version': self.locale_en.version}
                ],
                'geometry': {
                    'version': self.route.geometry.version,
                    'geom_detail':
                        '{"type": "LineString", "coordinates": ' +
                        '[[635956, 5723604], [635976, 5723654]]}'
                }
            }
        }
        (body, route) = self.put_success_all(body, self.route)
        self._assert_default_geometry(body, x=635966, y=5723629)

        self.assertEquals(route.elevation_max, 1600)
        locale_en = route.get_locale('en')
        self.assertEquals(locale_en.description, '...')
        self.assertEquals(locale_en.gear, 'none')

        # version with lang 'en'
        versions = route.versions
        version_en = self.get_latest_version('en', versions)
        archive_locale = version_en.document_locales_archive
        self.assertEqual(archive_locale.title, 'Mont Blanc from the air')
        self.assertEqual(archive_locale.gear, 'none')

        archive_document_en = version_en.document_archive
        self.assertEqual(archive_document_en.activities, ['skitouring'])
        self.assertEqual(archive_document_en.elevation_max, 1600)

        archive_geometry_en = version_en.document_geometry_archive
        self.assertEqual(archive_geometry_en.version, 2)

        # version with lang 'fr'
        version_fr = self.get_latest_version('fr', versions)
        archive_locale = version_fr.document_locales_archive
        self.assertEqual(archive_locale.title, 'Mont Blanc du ciel')
        self.assertEqual(archive_locale.gear, 'paraglider')

    def test_put_success_figures_only(self):
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.route.document_id,
                'version': self.route.version,
                'quality': quality_types[1],
                'activities': ['skitouring'],
                'elevation_min': 700,
                'elevation_max': 1600,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'durations': ['1'],
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'gear': 'paraglider',
                     'version': self.locale_en.version,
                     'title_prefix': 'Should be ignored'}
                ]
            }
        }
        (body, route) = self.put_success_figures_only(body, self.route)

        self.assertEquals(route.elevation_max, 1600)

    def test_put_success_new_track_with_default_geom(self):
        """Test that a provided default geometry (`geom`) is used instead of
        obtaining the geom from a track (`geom_detail`).
        """
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.route.document_id,
                'version': self.route.version,
                'quality': quality_types[1],
                'activities': ['skitouring'],
                'elevation_min': 700,
                'elevation_max': 1600,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'durations': ['1'],
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'gear': 'paraglider',
                     'version': self.locale_en.version,
                     'title_prefix': 'Should be ignored'}
                ],
                'geometry': {
                    'version': self.route.geometry.version,
                    'geom_detail':
                        '{"type": "LineString", "coordinates": ' +
                        '[[635956, 5723604], [635976, 5723654]]}',
                    'geom':
                        '{"type": "Point", "coordinates": [635000, 5723000]}'
                }
            }
        }
        (body, route) = self.put_success_figures_only(body, self.route)
        self._assert_default_geometry(body, x=635000, y=5723000)

    def test_put_success_update_default_geom_main_wp_changed(self):
        """Test that the default geom is updated when the main waypoint changes
        and no track exists.
        """
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.route2.document_id,
                'version': self.route2.version,
                'quality': quality_types[1],
                'main_waypoint_id': self.waypoint.document_id,
                'activities': ['skitouring'],
                'elevation_min': 700,
                'elevation_max': 1600,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'durations': ['1'],
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'gear': 'paraglider',
                     'version': self.route2.locales[0].version}
                ],
                'associations': {
                    'waypoints': [
                        {'document_id': self.waypoint.document_id}
                    ]
                }
            }
        }
        (body, route) = self.put_success_figures_only(body, self.route2)
        self._assert_default_geometry(body, x=635956, y=5723604)

    def test_put_success_main_wp_changed(self):
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.route.document_id,
                'main_waypoint_id': self.waypoint2.document_id,
                'version': self.route.version,
                'quality': quality_types[1],
                'activities': ['skitouring'],
                'elevation_min': 700,
                'elevation_max': 1500,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'durations': ['1'],
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'gear': 'paraglider',
                     'version': self.locale_en.version}
                ],
                'associations': {
                    'waypoints': [
                        {'document_id': self.waypoint2.document_id}
                    ]
                }
            }
        }
        (body, route) = self.put_success_figures_only(body, self.route)
        # tests that the default geometry has not changed (main wp has changed
        # but the route has a track)
        self._assert_default_geometry(body)

        self.assertEqual(route.main_waypoint_id, self.waypoint2.document_id)
        locale_en = route.get_locale('en')
        self.assertEqual(
            locale_en.title_prefix, self.waypoint2.get_locale('en').title)

        # check that a link to the new main waypoint is created
        association_main_wp = self.session.query(Association).get(
            (self.waypoint2.document_id, route.document_id))
        self.assertIsNotNone(association_main_wp)

        association_main_wp_log = self.session.query(AssociationLog). \
            filter(AssociationLog.parent_document_id ==
                   self.waypoint2.document_id). \
            filter(AssociationLog.child_document_id ==
                   route.document_id). \
            first()
        self.assertIsNotNone(association_main_wp_log)

    def test_put_success_lang_only(self):
        body = {
            'message': 'Changing lang',
            'document': {
                'document_id': self.route.document_id,
                'version': self.route.version,
                'quality': quality_types[1],
                'activities': ['skitouring'],
                'elevation_min': 700,
                'elevation_max': 1500,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'durations': ['1'],
                'locales': [
                    {'lang': 'en', 'title': 'Mont Blanc from the air',
                     'description': '...', 'gear': 'none',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, route) = self.put_success_lang_only(body, self.route)

        self.assertEquals(route.get_locale('en').gear, 'none')

    def test_put_success_new_lang(self):
        """Test updating a document by adding a new locale.
        """
        body = {
            'message': 'Adding lang',
            'document': {
                'document_id': self.route.document_id,
                'version': self.route.version,
                'quality': quality_types[1],
                'activities': ['skitouring'],
                'elevation_min': 700,
                'elevation_max': 1500,
                'height_diff_up': 800,
                'height_diff_down': 800,
                'durations': ['1'],
                'locales': [
                    {'lang': 'es', 'title': 'Mont Blanc del cielo',
                     'description': '...', 'gear': 'si'}
                ]
            }
        }
        (body, route) = self.put_success_new_lang(body, self.route)

        self.assertEquals(route.get_locale('es').gear, 'si')

    def test_history(self):
        id = self.route.document_id
        langs = ['fr', 'en']
        for lang in langs:
            body = self.app.get('/document/%d/history/%s' % (id, lang))
            username = 'contributor'
            user_id = self.global_userids[username]

            title = body.json['title']
            versions = body.json['versions']
            self.assertEqual(len(versions), 1)
            self.assertEqual(getattr(self, 'locale_' + lang).title, title)
            for r in versions:
                self.assertEqual(r['username'], username)
                self.assertEqual(r['user_id'], user_id)
                self.assertIn('written_at', r)
                self.assertIn('version_id', r)

    def test_history_no_lang(self):
        id = self.route.document_id
        self.app.get('/document/%d/history/es' % id, status=404)

    def test_history_no_doc(self):
        self.app.get('/document/99999/history/es', status=404)

    def _assert_geometry(self, body):
        self.assertIsNotNone(body.get('geometry'))
        geometry = body.get('geometry')
        self.assertIsNotNone(geometry.get('version'))
        self.assertIsNotNone(geometry.get('geom_detail'))

        geom = geometry.get('geom_detail')
        line = shape(json.loads(geom))
        self.assertIsInstance(line, LineString)
        self.assertAlmostEqual(line.coords[0][0], 635956)
        self.assertAlmostEqual(line.coords[0][1], 5723604)
        self.assertAlmostEqual(line.coords[1][0], 635966)
        self.assertAlmostEqual(line.coords[1][1], 5723644)

    def _assert_default_geometry(self, body, x=635961, y=5723624):
        self.assertIsNotNone(body.get('geometry'))
        geometry = body.get('geometry')
        self.assertIsNotNone(geometry.get('version'))
        self.assertIsNotNone(geometry.get('geom'))

        geom = geometry.get('geom')
        point = shape(json.loads(geom))
        self.assertIsInstance(point, Point)
        self.assertAlmostEqual(point.x, x)
        self.assertAlmostEqual(point.y, y)

    def test_update_prefix_title(self):
        self.route.locales.append(RouteLocale(
            lang='es', title='Mont Blanc del cielo', description='...',
            gear='paraglider'))
        self.route.main_waypoint_id = self.waypoint.document_id
        self.session.flush()
        self.session.refresh(self.route)
        check_title_prefix(self.route, create=False)
        self.session.expire_all()

        route = self.session.query(Route).get(self.route.document_id)
        locale_en = route.get_locale('en')
        self.assertEqual(locale_en.version, 1)
        self.assertEqual(
            locale_en.title_prefix, self.waypoint.get_locale('en').title)
        locale_fr = route.get_locale('fr')
        self.assertEqual(locale_fr.version, 1)
        self.assertEqual(
            locale_fr.title_prefix, self.waypoint.get_locale('fr').title)
        locale_es = route.get_locale('es')
        self.assertEqual(locale_es.version, 1)
        self.assertEqual(
            locale_es.title_prefix, self.waypoint.get_locale('fr').title)

    def _add_test_data(self):
        self.route = Route(
            activities=['skitouring'], elevation_max=1500, elevation_min=700,
            height_diff_up=800, height_diff_down=800, durations='1')

        self.locale_en = RouteLocale(
            lang='en', title='Mont Blanc from the air', description='...',
            gear='paraglider', title_prefix='Main waypoint title')

        self.locale_fr = RouteLocale(
            lang='fr', title='Mont Blanc du ciel', description='...',
            gear='paraglider')

        self.route.locales.append(self.locale_en)
        self.route.locales.append(self.locale_fr)

        self.route.geometry = DocumentGeometry(
            geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)',
            geom='SRID=3857;POINT(635961 5723624)'
        )

        self.session.add(self.route)
        self.session.flush()

        user_id = self.global_userids['contributor']
        DocumentRest.create_new_version(self.route, user_id)
        self.route_version = self.session.query(DocumentVersion). \
            filter(DocumentVersion.document_id == self.route.document_id). \
            filter(DocumentVersion.lang == 'en').first()

        self.route2 = Route(
            activities=['skitouring'], elevation_max=1500, elevation_min=700,
            height_diff_up=800, height_diff_down=800, durations='1',
            locales=[
                RouteLocale(
                    lang='en', title='Mont Blanc from the air',
                    description='...', gear='paraglider'),
                RouteLocale(
                    lang='fr', title='Mont Blanc du ciel', description='...',
                    gear='paraglider')]
        )
        self.session.add(self.route2)
        self.session.flush()
        DocumentRest.create_new_version(self.route2, user_id)

        self.route3 = Route(
            activities=['skitouring'], elevation_max=1500, elevation_min=700,
            height_diff_up=500, height_diff_down=500, durations='1')
        self.session.add(self.route3)
        self.route4 = Route(
            activities=['skitouring'], elevation_max=1500, elevation_min=700,
            height_diff_up=500, height_diff_down=500, durations='1')
        self.route4.locales.append(RouteLocale(
            lang='en', title='Mont Blanc from the air', description='...',
            gear='paraglider'))
        self.route4.locales.append(RouteLocale(
            lang='fr', title='Mont Blanc du ciel', description='...',
            gear='paraglider'))
        self.session.add(self.route4)

        # add a map
        self.session.add(TopoMap(
            code='3232ET', editor='IGN', scale='25000',
            locales=[
                DocumentLocale(lang='fr', title='Belley')
            ],
            geometry=DocumentGeometry(geom_detail='SRID=3857;POLYGON((635900 5723600, 635900 5723700, 636000 5723700, 636000 5723600, 635900 5723600))')  # noqa
        ))

        # add some associations
        self.waypoint = Waypoint(
            waypoint_type='summit', elevation=4,
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)'))
        self.waypoint.locales.append(WaypointLocale(
            lang='en', title='Mont Granier (en)', description='...',
            access='yep'))
        self.waypoint.locales.append(WaypointLocale(
            lang='fr', title='Mont Granier (fr)', description='...',
            access='ouai'))
        self.session.add(self.waypoint)
        self.waypoint2 = Waypoint(
            waypoint_type='summit', elevation=4,
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)'))
        self.waypoint2.locales.append(WaypointLocale(
            lang='en', title='Mont Granier (en)', description='...',
            access='yep'))
        self.session.add(self.waypoint2)
        self.session.flush()
        self.session.add(Association(
            parent_document_id=self.route.document_id,
            child_document_id=self.route4.document_id))
        self.session.add(Association(
            parent_document_id=self.route4.document_id,
            child_document_id=self.route.document_id))
        self.session.add(Association(
            parent_document_id=self.waypoint.document_id,
            child_document_id=self.route.document_id))

        self.outing1 = Outing(
            activities=['skitouring'], date_start=datetime.date(2016, 1, 1),
            date_end=datetime.date(2016, 1, 1),
            locales=[
                OutingLocale(
                    lang='en', title='...', description='...',
                    weather='sunny')
            ]
        )
        self.session.add(self.outing1)
        self.session.flush()
        self.session.add(Association(
            parent_document_id=self.route.document_id,
            child_document_id=self.outing1.document_id))

        self.outing2 = Outing(
            redirects_to=self.outing1.document_id,
            activities=['skitouring'], date_start=datetime.date(2016, 1, 1),
            date_end=datetime.date(2016, 1, 1),
            locales=[
                OutingLocale(
                    lang='en', title='...', description='...',
                    weather='sunny')
            ]
        )
        self.session.add(self.outing2)
        self.session.flush()
        self.session.add(Association(
            parent_document_id=self.route.document_id,
            child_document_id=self.outing2.document_id))
        self.session.flush()

        # add areas
        self.area1 = Area(
            area_type='range',
            geometry=DocumentGeometry(
                geom_detail='SRID=3857;POLYGON((635900 5723600, 635900 5723700, 636000 5723700, 636000 5723600, 635900 5723600))'  # noqa
            )
        )
        self.area2 = Area(
            area_type='range',
            locales=[
                DocumentLocale(lang='fr', title='France')
            ]
        )

        self.session.add_all([self.area1, self.area2])
        self.session.flush()
