# coding=utf-8
from c2corg_api.models.waypoint import WAYPOINT_TYPE
from c2corg_api.scripts.migration.documents.document import DEFAULT_QUALITY
from c2corg_api.scripts.migration.documents.waypoints.waypoint import \
    MigrateWaypoints


class MigrateSites(MigrateWaypoints):

    def get_name(self):
        return 'sites'

    def get_count_query(self):
        return (
            'select count(*) '
            'from app_sites_archives sa join sites s on sa.id = s.id '
            'where s.redirects_to is null;'
        )

    def get_query(self):
        return (
            'select '
            '   sa.id, sa.document_archive_id, sa.is_latest_version, '
            '   sa.elevation, sa.is_protected, sa.redirects_to, '
            '   ST_Force2D(ST_SetSRID(sa.geom, 3857)) geom,'
            '   sa.routes_quantity, sa.max_rating, sa.min_rating, '
            '   sa.mean_rating, sa.max_height, sa.min_height, sa.mean_height, '
            '   sa.equipment_rating, sa.climbing_styles, sa.rock_types, '
            '   sa.site_types, sa.children_proof, sa.rain_proof, sa.facings, '
            '   sa.best_periods '
            'from app_sites_archives sa join sites s on sa.id = s.id '
            'where s.redirects_to is null '
            'order by sa.id, sa.document_archive_id;'
        )

    def get_count_query_locales(self):
        return (
            'select count(*) '
            'from app_sites_i18n_archives sa join sites s on sa.id = s.id '
            'where s.redirects_to is null;'
        )

    def get_query_locales(self):
        return (
            'select '
            '   sa.id, sa.document_i18n_archive_id, sa.is_latest_version, '
            '   sa.culture, sa.name, sa.description, sa.remarks, '
            '   sa.pedestrian_access, sa.way_back, sa.site_history, '
            '   sa.external_resources '
            'from app_sites_i18n_archives sa join sites s on sa.id = s.id '
            'where s.redirects_to is null '
            'order by sa.id, sa.document_i18n_archive_id;'
        )

    def get_document(self, document_in, version):
        indoor_types, outdoor_types = self.get_climbing_types(document_in)
        return dict(
            document_id=document_in.id,
            type=WAYPOINT_TYPE,
            version=version,
            waypoint_type='climbing_indoor' if indoor_types
                          else 'climbing_outdoor',
            protected=document_in.is_protected,
            redirects_to=document_in.redirects_to,
            elevation=document_in.elevation,
            routes_quantity=document_in.routes_quantity,
            climbing_rating_max=self.convert_type(
                document_in.max_rating, MigrateSites.climbing_ratings),
            climbing_rating_min=self.convert_type(
                document_in.min_rating, MigrateSites.climbing_ratings),
            climbing_rating_median=self.convert_type(
                document_in.mean_rating, MigrateSites.climbing_ratings),
            height_max=document_in.max_height,
            height_min=document_in.min_height,
            height_median=document_in.mean_height,
            equipment_rating=self.convert_type(
                document_in.equipment_rating,
                MigrateSites.equipment_ratings, [0]),
            climbing_styles=self.convert_types(
                document_in.climbing_styles,
                MigrateSites.climbing_styles, [0]),
            rock_types=self.convert_types(
                document_in.rock_types, MigrateSites.rock_types, [0, 20]),
            climbing_outdoor_types=outdoor_types,
            climbing_indoor_types=indoor_types,
            children_proof=self.convert_type(
                document_in.children_proof, MigrateSites.children_proof_types),
            rain_proof=self.convert_type(
                document_in.rain_proof, MigrateSites.rain_proof_types),
            orientations=self.convert_types(
                document_in.facings, MigrateSites.orientation_types, [0]),
            best_periods=self.convert_types(
                document_in.best_periods, MigrateSites.best_periods),
            quality=DEFAULT_QUALITY
        )

    def get_document_locale(self, document_in, version):
        description, summary = self.extract_summary(document_in.description)
        return dict(
            document_id=document_in.id,
            id=document_in.document_i18n_archive_id,
            type=WAYPOINT_TYPE,
            version=version,
            lang=document_in.culture,
            title=document_in.name,
            description=self.get_description(description, document_in),
            summary=summary,
            access=document_in.pedestrian_access,
        )

    def get_climbing_types(self, document_in):
        """ v6 did not differentiate between indoor and outdoor types, so this
        function tries to make a guess if the site is indoor or outdoor.
        """
        site_types_in = document_in.site_types \
            if document_in.site_types is not None else []
        rock_types_in = document_in.rock_types \
            if document_in.rock_types is not None else []

        indoor_types = []
        outdoor_types = []
        if 12 in site_types_in:  # climbing_gym
            indoor_types.append('pitch')
            if 4 in site_types_in:  # boulder
                # assuming indoor bloc
                indoor_types.append('bloc')
        else:
            if 2 in site_types_in:  # single-pitch
                if 30 in rock_types_in:  # rocktype: artificial
                    indoor_types.append('pitch')
                else:
                    outdoor_types.append('single')
            if 4 in site_types_in:  # boulder
                if 30 in rock_types_in:  # rocktype: artificial
                    indoor_types.append('bloc')
                else:
                    outdoor_types.append('bloc')

        indoor_types = indoor_types if indoor_types else None
        outdoor_types = outdoor_types if outdoor_types else None

        return indoor_types, outdoor_types

    def get_description(self, description, document_in):
        sections = []

        if description is not None:
            sections.append(description.strip())

        self.add_section(sections, 'way_back', document_in)
        self.add_section(sections, 'remarks', document_in)
        self.add_section(sections, 'external_resources', document_in)
        self.add_section(sections, 'site_history', document_in)

        return '\n'.join(sections)

    def add_section(self, sections, field, document_in):
        text = document_in[field]
        if text is None:
            return
        text = text.strip()

        if text:
            section = ''
            header = self.translate(field, document_in.culture)
            section += '## ' + header + '\n'
            section += text
            sections.append(section)

    def translate(self, field, lang):
        return MigrateSites.translations[field][lang]

    translations = {
        'way_back': {
            'ca': 'Baixada de las vies',
            'de': 'Abstieg der Route',
            'en': 'Means of descent',
            'es': 'Bajada de las vías',
            'eu': 'Luzeeren jeitsiera',
            'fr': 'Descente des voies',
            'it': 'Discesa delle vie'
        },
        'remarks': {
            'ca': 'Remarques',
            'de': 'Bemerkungen',
            'en': 'Remarks',
            'es': 'Observaciones',
            'eu': 'Azalpenak',
            'fr': 'Remarques',
            'it': 'Osservazioni'
        },
        'external_resources': {
            'ca': 'Bibliografia i webgrafia',
            'de': 'Bibliographie',
            'en': 'External resources',
            'es': 'Bibliografía y webgrafía',
            'eu': 'Bibliografia et webografia',
            'fr': 'Bibliographie et webographie',
            'it': 'Bibliografia e riferimenti web'
        },
        'site_history': {
            'ca': 'Històric',
            'de': 'Geschichte des Klettersektors',
            'en': 'Site history',
            'es': 'Historia',
            'eu': 'Historia',
            'fr': 'Historique du site',
            'it': 'Cenni storici'
        }
    }

    equipment_ratings = {
        '4': 'P1',
        '5': 'P1',  # from v4?
        '6': 'P1+',
        '7': 'P1+',  # from v4?
        '8': 'P2',
        '10': 'P2+',
        '12': 'P3',
        '14': 'P3+',
        '16': 'P4',
        '18': 'P4+'
    }

    climbing_styles = {
        '2': 'slab',
        '3': 'vertical',
        '4': 'overhang',
        '6': 'roof',
        '8': 'small_pillar',
        '10': 'crack_dihedral'
    }

    rock_types = {
        '2': 'basalte',
        '4': 'calcaire',
        '6': 'conglomerat',
        '8': 'craie',
        '10': 'gneiss',
        '12': 'gres',
        '14': 'granit',
        '16': 'migmatite',
        '18': 'mollasse_calcaire',
        '22': 'quartzite',
        '24': 'rhyolite',
        '26': 'schiste',
        '28': 'trachyte',
        '30': 'artificial'
    }

    children_proof_types = {
        '2': 'very_safe',
        '4': 'safe',
        '6': 'dangerous',
        '8': 'very_dangerous'
    }

    rain_proof_types = {
        '2': 'exposed',
        '4': 'partly_protected',
        '6': 'protected'
    }

    # orientation types for sites (not the same codes for routes!)
    orientation_types = {
        '2': 'N',
        '16': 'NE',
        '14': 'E',
        '12': 'SE',
        '10': 'S',
        '8': 'SW',
        '6': 'W',
        '4': 'NW'
    }

    best_periods = {
        '1': 'jan',
        '2': 'feb',
        '3': 'mar',
        '4': 'apr',
        '5': 'may',
        '6': 'jun',
        '7': 'jul',
        '8': 'aug',
        '9': 'sep',
        '10': 'oct',
        '11': 'nov',
        '12': 'dec'
    }

    climbing_ratings = {
        '2': '2',
        '3': '3a',
        '4': '3b',
        '6': '3c',
        '8': '4a',
        '10': '4b',
        '12': '4c',
        '14': '5a',
        '15': '5a+',
        '16': '5b',
        '17': '5b+',
        '18': '5c',
        '19': '5c+',
        '20': '6a',
        '22': '6a+',
        '24': '6b',
        '26': '6b+',
        '28': '6c',
        '30': '6c+',
        '32': '7a',
        '34': '7a+',
        '36': '7b',
        '38': '7b+',
        '40': '7c',
        '42': '7c+',
        '44': '8a',
        '46': '8a+',
        '48': '8b',
        '50': '8b+',
        '52': '8c',
        '54': '8c+',
        '56': '9a',
        '58': '9a+',
        '60': '9b',
        '62': '9b+',
        '64': '9c',
        '66': '9c+'
    }
