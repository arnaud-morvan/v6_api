from sqlalchemy.orm.exc import StaleDataError
from shapely.geometry import Point
from geoalchemy2.shape import from_shape

from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.models.document import (
    UpdateType, DocumentGeometry, set_available_cultures)
from c2corg_api.tests import BaseTestCase
from c2corg_api.models.query_builder import dict_to_query


class TestWaypoint(BaseTestCase):

    def test_to_archive(self):
        waypoint = Waypoint(
            document_id=1, waypoint_type='summit', elevation=2203,
            locales=[
                WaypointLocale(
                    id=2, culture='en', title='A', description='abc'),
                WaypointLocale(
                    id=3, culture='fr', title='B', description='bcd'),
            ],
            geometry=DocumentGeometry(
                document_id=1, geom=from_shape(Point(1, 1), srid=3857))
        )

        waypoint_archive = waypoint.to_archive()

        self.assertIsNone(waypoint_archive.id)
        self.assertEqual(waypoint_archive.document_id, waypoint.document_id)
        self.assertEqual(
            waypoint_archive.waypoint_type, waypoint.waypoint_type)
        self.assertEqual(waypoint_archive.elevation, waypoint.elevation)

        archive_locals = waypoint.get_archive_locales()

        self.assertEqual(len(archive_locals), 2)
        locale = waypoint.locales[0]
        locale_archive = archive_locals[0]
        self.assertIsNot(locale_archive, locale)
        self.assertIsNone(locale_archive.id)
        self.assertEqual(locale_archive.culture, locale.culture)
        self.assertEqual(locale_archive.title, locale.title)
        self.assertEqual(locale_archive.description, locale.description)

        archive_geometry = waypoint.get_archive_geometry()
        self.assertIsNone(archive_geometry.id)
        self.assertIsNotNone(archive_geometry.document_id)
        self.assertEqual(archive_geometry.document_id, waypoint.document_id)
        self.assertIsNotNone(archive_geometry.geom)

    def test_version_is_incremented(self):
        waypoint = Waypoint(
            document_id=1, waypoint_type='summit', elevation=2203,
            locales=[
                WaypointLocale(
                    id=2, culture='en', title='A', description='abc')
            ]
        )
        self.session.add(waypoint)
        self.session.flush()

        version1 = waypoint.version
        self.assertIsNotNone(version1)

        # make a change to the waypoint and check that the version changes
        # once the waypoint is persisted
        waypoint.elevation = 1234
        self.session.merge(waypoint)
        self.session.flush()
        version2 = waypoint.version
        self.assertNotEqual(version1, version2)

    def test_version_concurrent_edit(self):
        """Test that a `StaleDataError` is thrown when trying to update a
        waypoint with an old version number.
        """
        waypoint1 = Waypoint(
            document_id=1, waypoint_type='summit', elevation=2203,
            locales=[
                WaypointLocale(
                    id=2, culture='en', title='A', description='abc')
            ]
        )

        # add the initial waypoint
        self.session.add(waypoint1)
        self.session.flush()
        self.session.expunge(waypoint1)
        version1 = waypoint1.version
        self.assertIsNotNone(version1)

        # change the waypoint
        waypoint2 = self.session.query(Waypoint).get(waypoint1.document_id)
        waypoint2.elevation = 1234
        self.session.merge(waypoint2)
        self.session.flush()
        version2 = waypoint2.version
        self.assertNotEqual(version1, version2)

        self.assertNotEqual(waypoint1.version, waypoint2.version)
        self.assertNotEqual(waypoint1.elevation, waypoint2.elevation)

        # then try to update the waypoint again with the old version
        waypoint1.elevation = 2345
        self.assertRaises(StaleDataError, self.session.merge, waypoint1)

    def test_update(self):
        waypoint_db = Waypoint(
            document_id=1, waypoint_type='summit', elevation=2203,
            version=123,
            locales=[
                WaypointLocale(
                    id=2, culture='en', title='A', description='abc',
                    version=345),
                WaypointLocale(
                    id=3, culture='fr', title='B', description='bcd',
                    version=678),
            ],
            geometry=DocumentGeometry(
                document_id=1, geom='SRID=3857;POINT(1 2)'
            )
        )
        waypoint_in = Waypoint(
            document_id=1, waypoint_type='summit', elevation=1234,
            version=123,
            locales=[
                WaypointLocale(
                    id=2, culture='en', title='C', description='abc',
                    version=345),
                WaypointLocale(
                    culture='es', title='D', description='efg'),
            ],
            geometry=DocumentGeometry(geom='SRID=3857;POINT(3 4)')
        )
        waypoint_db.update(waypoint_in)
        self.assertEqual(waypoint_db.elevation, waypoint_in.elevation)
        self.assertEqual(len(waypoint_db.locales), 3)

        locale_en = waypoint_db.get_locale('en')
        locale_fr = waypoint_db.get_locale('fr')
        locale_es = waypoint_db.get_locale('es')

        self.assertEqual(locale_en.title, 'C')
        self.assertEqual(locale_fr.title, 'B')
        self.assertEqual(locale_es.title, 'D')

        self.assertEqual(waypoint_db.geometry.geom, 'SRID=3857;POINT(3 4)')

    def test_get_update_type_figures_only(self):
        waypoint = self._get_waypoint()
        self.session.add(waypoint)
        self.session.flush()

        versions = waypoint.get_versions()

        waypoint.elevation = 1234
        self.session.merge(waypoint)
        self.session.flush()

        (types, changed_langs) = waypoint.get_update_type(versions)
        self.assertIn(UpdateType.FIGURES, types)
        self.assertEqual(changed_langs, [])

    def test_get_update_type_geom_only(self):
        waypoint = self._get_waypoint()
        self.session.add(waypoint)
        self.session.flush()

        versions = waypoint.get_versions()

        waypoint.geometry.geom = 'SRID=3857;POINT(3 4)'
        self.session.merge(waypoint)
        self.session.flush()

        (types, changed_langs) = waypoint.get_update_type(versions)
        self.assertIn(UpdateType.GEOM, types)
        self.assertEqual(changed_langs, [])

    def test_get_update_type_lang_only(self):
        waypoint = self._get_waypoint()
        self.session.add(waypoint)
        self.session.flush()

        versions = waypoint.get_versions()

        waypoint.get_locale('en').description = 'abcd'
        self.session.merge(waypoint)
        self.session.flush()

        (types, changed_langs) = waypoint.get_update_type(versions)
        self.assertIn(UpdateType.LANG, types)
        self.assertEqual(changed_langs, ['en'])

    def test_get_update_type_lang_only_new_lang(self):
        waypoint = self._get_waypoint()
        self.session.add(waypoint)
        self.session.flush()

        versions = waypoint.get_versions()

        waypoint.locales.append(WaypointLocale(
            culture='es', title='A', description='abc'))
        self.session.merge(waypoint)
        self.session.flush()

        (types, changed_langs) = waypoint.get_update_type(versions)
        self.assertIn(UpdateType.LANG, types)
        self.assertEqual(changed_langs, ['es'])

    def test_get_update_type_all(self):
        waypoint = self._get_waypoint()
        self.session.add(waypoint)
        self.session.flush()

        versions = waypoint.get_versions()

        waypoint.elevation = 1234
        waypoint.get_locale('en').description = 'abcd'
        waypoint.locales.append(WaypointLocale(
            culture='es', title='A', description='abc'))

        self.session.merge(waypoint)
        self.session.flush()

        (types, changed_langs) = waypoint.get_update_type(versions)
        self.assertIn(UpdateType.LANG, types)
        self.assertIn(UpdateType.FIGURES, types)
        self.assertNotIn(UpdateType.GEOM, types)
        self.assertEqual(changed_langs, ['en', 'es'])

    def test_get_update_type_none(self):
        waypoint = self._get_waypoint()
        self.session.add(waypoint)
        self.session.flush()

        versions = waypoint.get_versions()
        self.session.merge(waypoint)
        self.session.flush()

        (types, changed_langs) = waypoint.get_update_type(versions)
        self.assertEqual(types, [])
        self.assertEqual(changed_langs, [])

    def test_save_geometry(self):
        waypoint = self._get_waypoint()
        waypoint.geometry = DocumentGeometry(
            geom='SRID=3857;POINT(635956.075332665 5723604.677994)')
        self.session.add(waypoint)
        self.session.flush()

    def test_set_available_cultures(self):
        waypoint = self._get_waypoint()
        waypoint.geometry = DocumentGeometry(
            geom='SRID=3857;POINT(635956.075332665 5723604.677994)')
        self.session.add(waypoint)
        self.session.flush()

        set_available_cultures([waypoint])
        self.assertEqual(waypoint.available_cultures, ['en', 'fr'])

    def test_dict_to_query(self):
        wp1 = self._get_waypoint(1)
        wp2 = self._get_waypoint(2)
        wp3 = self._get_waypoint(3)
        self.session.add_all([wp1, wp2, wp3])
        self.session.flush()

        d = {
                'outings': 'list',
                'summits': '{0}-{1}'.format(wp1.document_id, wp2.document_id),
                'orderby': 'document_id',
                'order': 'desc'
            }
        q = dict_to_query(d, Waypoint)
        results = q.all()
        self.assertEqual(
                map(lambda json: json.document_id, results),
                [wp2.document_id, wp1.document_id])

    def _get_waypoint(self, elevation=2203):
        return Waypoint(
            waypoint_type='summit', elevation=elevation,
            locales=[
                WaypointLocale(
                    culture='en', title='A', description='abc',
                    access='y'),
                WaypointLocale(
                    culture='fr', title='B', description='bcd',
                    access='y')
            ],
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956.075332665 5723604.677994)')
        )
