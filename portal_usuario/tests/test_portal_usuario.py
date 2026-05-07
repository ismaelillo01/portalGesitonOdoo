# -*- coding: utf-8 -*-
import re
from datetime import timedelta

from odoo import fields, http
from odoo.tests import tagged
from odoo.tests.common import HOST, HttpCase, Opener, TransactionCase, get_db_name, new_test_user


@tagged('-at_install', 'post_install')
class TestPortalUsuarioService(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service = cls.env['portal.usuario.service']
        cls.ap_service = cls.env.ref('usuarios.usuarios_servicio_ap')
        cls.zone = cls.env['zonastrabajo.zona'].create({
            'name': 'Zona Portal Usuario',
            'code': 'ZONA_PORTAL_USR',
        })
        cls.worker = cls.env['trabajadores.trabajador'].create({
            'name': 'AP Test',
            'apellido1': 'Prueba',
            'dni_nie': 'WORKER001X',
            'grupo': 'agusto',
            'zona_trabajo_ids': [(6, 0, [cls.zone.id])],
        })
        cls.usuario = cls.env['usuarios.usuario'].create({
            'name': 'Usuario Test',
            'apellido1': 'Portal',
            'dni_nie': '99887766A',
            'grupo': 'agusto',
            'zona_trabajo_id': cls.zone.id,
            'servicio_ids': [(6, 0, [cls.ap_service.id])],
        })

    def _create_assignment(self, usuario, date_value, confirmed=True, start=8.0, end=10.0):
        assignment = self.env['portalgestor.asignacion'].create({
            'usuario_id': usuario.id,
            'fecha': fields.Date.to_date(date_value),
            'confirmado': confirmed,
        })
        self.env['portalgestor.asignacion.linea'].create({
            'asignacion_id': assignment.id,
            'hora_inicio': start,
            'hora_fin': end,
            'trabajador_id': self.worker.id,
        })
        return assignment

    def test_dni_lookup_normalizes_spaces_hyphens_and_case(self):
        usuario, error = self.service._find_usuario_by_dni(' 9988-7766a ')

        self.assertFalse(error)
        self.assertEqual(usuario, self.usuario)

    def test_dni_lookup_rejects_missing_and_duplicate(self):
        usuario, error = self.service._find_usuario_by_dni('00000000T')
        self.assertFalse(usuario)
        self.assertEqual(error, 'not_found')

        self.env['usuarios.usuario'].create({
            'name': 'Usuario Dup A',
            'dni_nie': 'DUP9991A',
            'grupo': 'agusto',
            'zona_trabajo_id': self.zone.id,
        })
        self.env['usuarios.usuario'].create({
            'name': 'Usuario Dup B',
            'dni_nie': 'dup-9991a',
            'grupo': 'agusto',
            'zona_trabajo_id': self.zone.id,
        })
        usuario, error = self.service._find_usuario_by_dni('DUP 9991A')
        self.assertFalse(usuario)
        self.assertEqual(error, 'duplicate')

    def test_month_calendar_shows_confirmed_lines(self):
        self._create_assignment(self.usuario, '2026-04-06', confirmed=True, start=8.0, end=10.5)
        self._create_assignment(self.usuario, '2026-04-07', confirmed=False, start=9.0, end=10.0)

        calendar_data = self.service._get_usuario_month_calendar(self.usuario, 2026, 4)
        days_by_date = {
            day['date_string']: day
            for week in calendar_data['weeks']
            for day in week
            if day['in_month']
        }

        self.assertEqual(calendar_data['month_label'], 'Abril')
        self.assertEqual(len(days_by_date['2026-04-06']['work_items']), 1)
        self.assertEqual(days_by_date['2026-04-06']['work_items'][0]['time_range'], '08:00 - 10:30')
        self.assertIn('AP Test', days_by_date['2026-04-06']['work_items'][0]['label'])
        # Unconfirmed should not appear
        self.assertFalse(days_by_date['2026-04-07']['work_items'])

    def test_navigation_urls_use_usuario_pattern(self):
        calendar_data = self.service._get_usuario_month_calendar(self.usuario, 2026, 4)

        self.assertEqual(calendar_data['previous']['url'], '/usuario/horario/2026/3')
        self.assertEqual(calendar_data['next']['url'], '/usuario/horario/2026/5')


@tagged('-at_install', 'post_install')
class TestPortalUsuarioRoutes(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ap_service = cls.env.ref('usuarios.usuarios_servicio_ap')
        cls.zone = cls.env['zonastrabajo.zona'].create({
            'name': 'Zona Portal Usr HTTP',
            'code': 'ZONA_PORTAL_USR_HTTP',
        })
        cls.worker = cls.env['trabajadores.trabajador'].create({
            'name': 'AP Portal Usr HTTP',
            'dni_nie': 'WORKERHTTP',
            'grupo': 'agusto',
            'zona_trabajo_ids': [(6, 0, [cls.zone.id])],
        })
        cls.usuario = cls.env['usuarios.usuario'].create({
            'name': 'Usuario HTTP',
            'apellido1': 'Test',
            'dni_nie': '11223344B',
            'grupo': 'agusto',
            'zona_trabajo_id': cls.zone.id,
            'servicio_ids': [(6, 0, [cls.ap_service.id])],
        })
        assignment = cls.env['portalgestor.asignacion'].create({
            'usuario_id': cls.usuario.id,
            'fecha': fields.Date.today() + timedelta(days=1),
            'confirmado': True,
        })
        cls.env['portalgestor.asignacion.linea'].create({
            'asignacion_id': assignment.id,
            'hora_inicio': 8.0,
            'hora_fin': 9.0,
            'trabajador_id': cls.worker.id,
        })

    def setUp(self):
        super().setUp()
        self.session = http.root.session_store.new()
        self.session.update(http.get_default_session(), db=get_db_name())
        self.opener = Opener(self.env.cr)
        self.opener.cookies.set('session_id', self.session.sid, domain=HOST, path='/')

    def _get_login_csrf_token(self):
        response = self.url_open('/usuario')
        token_match = re.search(r'name="csrf_token"\s+value="([^"]+)"', response.text)
        self.assertTrue(token_match, 'El formulario de login debe incluir csrf_token.')
        return token_match.group(1)

    def test_schedule_without_session_redirects_to_login(self):
        self.opener.cookies.clear()
        response = self.url_open('/usuario/horario', allow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.headers.get('Location', '').endswith('/usuario'))

    def test_login_by_dni_opens_schedule(self):
        response = self.url_open('/usuario/login', data={
            'dni_nie': '1122 3344-b',
            'csrf_token': self._get_login_csrf_token(),
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn('Mi Atencion', response.text)
        self.assertIn('Usuario HTTP', response.text)

    def test_login_unknown_dni_shows_generic_error(self):
        response = self.url_open('/usuario/login', data={
            'dni_nie': 'NOEXISTE',
            'csrf_token': self._get_login_csrf_token(),
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn('No se ha encontrado ningun usuario', response.text)
