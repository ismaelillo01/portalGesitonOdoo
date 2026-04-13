# -*- coding: utf-8 -*-
import re
from datetime import timedelta

from odoo import fields, http
from odoo.tests import tagged
from odoo.tests.common import HOST, HttpCase, Opener, TransactionCase, get_db_name, new_test_user


@tagged('-at_install', 'post_install')
class TestPortalAPService(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service = cls.env['portal.ap.service']
        cls.ap_service = cls.env.ref('usuarios.usuarios_servicio_ap')
        cls.zone = cls.env['zonastrabajo.zona'].create({
            'name': 'Zona Portal AP',
            'code': 'ZONA_PORTAL_AP',
        })
        cls.worker = cls.env['trabajadores.trabajador'].create({
            'name': 'AP Portal',
            'apellido1': 'Prueba',
            'dni_nie': '12345678X',
            'grupo': 'agusto',
            'zona_trabajo_ids': [(6, 0, [cls.zone.id])],
        })
        cls.usuario_a = cls.env['usuarios.usuario'].create({
            'name': 'Usuario Portal',
            'apellido1': 'Uno',
            'grupo': 'agusto',
            'zona_trabajo_id': cls.zone.id,
            'servicio_ids': [(6, 0, [cls.ap_service.id])],
        })
        cls.usuario_b = cls.env['usuarios.usuario'].create({
            'name': 'Usuario Portal',
            'apellido1': 'Dos',
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
        worker, error = self.service._find_worker_by_dni(' 1234-5678x ')

        self.assertFalse(error)
        self.assertEqual(worker, self.worker)

    def test_dni_lookup_rejects_missing_and_duplicate(self):
        worker, error = self.service._find_worker_by_dni('00000000T')
        self.assertFalse(worker)
        self.assertEqual(error, 'not_found')

        self.env['trabajadores.trabajador'].create({
            'name': 'AP Portal Duplicado A',
            'dni_nie': 'DUP0001A',
            'grupo': 'agusto',
            'zona_trabajo_ids': [(6, 0, [self.zone.id])],
        })
        self.env['trabajadores.trabajador'].create({
            'name': 'AP Portal Duplicado B',
            'dni_nie': 'dup-0001a',
            'grupo': 'agusto',
            'zona_trabajo_ids': [(6, 0, [self.zone.id])],
        })
        worker, error = self.service._find_worker_by_dni('DUP 0001A')
        self.assertFalse(worker)
        self.assertEqual(error, 'duplicate')

    def test_month_calendar_shows_confirmed_lines_and_vacations(self):
        self._create_assignment(self.usuario_a, '2026-04-06', confirmed=True, start=8.0, end=10.5)
        self._create_assignment(self.usuario_b, '2026-04-06', confirmed=True, start=12.0, end=13.0)
        self._create_assignment(self.usuario_b, '2026-04-07', confirmed=False, start=9.0, end=10.0)
        self.env['trabajadores.vacacion'].create({
            'trabajador_id': self.worker.id,
            'date_start': fields.Date.to_date('2026-04-08'),
            'date_stop': fields.Date.to_date('2026-04-10'),
        })

        calendar_data = self.service._get_worker_month_calendar(self.worker, 2026, 4)
        days_by_date = {
            day['date_string']: day
            for week in calendar_data['weeks']
            for day in week
            if day['in_month']
        }

        self.assertEqual(calendar_data['month_label'], 'Abril')
        self.assertEqual(len(days_by_date['2026-04-06']['work_items']), 2)
        self.assertEqual(days_by_date['2026-04-06']['work_items'][0]['time_range'], '08:00 - 10:30')
        self.assertIn('Usuario Portal', days_by_date['2026-04-06']['work_items'][0]['label'])
        self.assertFalse(days_by_date['2026-04-07']['work_items'])
        self.assertTrue(days_by_date['2026-04-08']['vacations'])
        self.assertTrue(days_by_date['2026-04-10']['vacations'])

    def test_user_month_calendar_returns_worker_labels(self):
        self._create_assignment(self.usuario_a, '2026-04-11', confirmed=True, start=17.5, end=18.5)

        calendar_data = self.service._get_user_month_calendar(self.usuario_a, 2026, 4, viewer=self.env.user)
        days_by_date = {
            day['date_string']: day
            for day in calendar_data['month_days']
        }

        self.assertEqual(calendar_data['user_name'], self.usuario_a.display_name)
        self.assertEqual(days_by_date['2026-04-11']['work_items'][0]['time_range'], '17:30 - 18:30')
        self.assertIn('AP Portal', days_by_date['2026-04-11']['work_items'][0]['label'])

    def test_manager_worker_cards_return_workers(self):
        cards = self.service._get_manager_worker_cards(viewer=self.env.user, search='portal')

        self.assertTrue(cards)
        self.assertEqual(cards[0]['id'], self.worker.id)
        self.assertEqual(cards[0]['url'], f'/consultar-horario/ap/{self.worker.id}')
        self.assertIn('AP Portal', cards[0]['display_name'])


@tagged('-at_install', 'post_install')
class TestPortalAPRoutes(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ap_service = cls.env.ref('usuarios.usuarios_servicio_ap')
        cls.zone = cls.env['zonastrabajo.zona'].create({
            'name': 'Zona Portal AP HTTP',
            'code': 'ZONA_PORTAL_AP_HTTP',
        })
        cls.worker = cls.env['trabajadores.trabajador'].create({
            'name': 'AP Portal HTTP',
            'dni_nie': '87654321Z',
            'grupo': 'agusto',
            'zona_trabajo_ids': [(6, 0, [cls.zone.id])],
        })
        cls.usuario = cls.env['usuarios.usuario'].create({
            'name': 'Usuario HTTP',
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
        cls.env['trabajadores.vacacion'].create({
            'trabajador_id': cls.worker.id,
            'date_start': fields.Date.today() + timedelta(days=2),
            'date_stop': fields.Date.today() + timedelta(days=2),
        })
        cls.manager_user = new_test_user(
            cls.env,
            login='manager_schedule_user',
            password='manager_schedule_user',
            groups='gestores.group_gestores_agusto',
        )

    def setUp(self):
        super().setUp()
        self.session = http.root.session_store.new()
        self.session.update(http.get_default_session(), db=get_db_name())
        self.opener = Opener(self.env.cr)
        self.opener.cookies.set('session_id', self.session.sid, domain=HOST, path='/')

    def _get_login_csrf_token(self):
        response = self.url_open('/ap')
        token_match = re.search(r'name="csrf_token"\s+value="([^"]+)"', response.text)
        self.assertTrue(token_match, 'El formulario de login debe incluir csrf_token.')
        return token_match.group(1)

    def _login_internal_manager(self):
        response = self.url_open('/web/login', data={
            'login': 'manager_schedule_user',
            'password': 'manager_schedule_user',
            'csrf_token': http.Request.csrf_token(self),
            'redirect': '/odoo',
        }, allow_redirects=False)
        self.assertIn(response.status_code, (303, 200))
        return response

    def test_schedule_without_session_redirects_to_login(self):
        self.opener.cookies.clear()
        response = self.url_open('/ap/horario', allow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.headers.get('Location', '').endswith('/ap'))

    def test_login_by_dni_opens_schedule(self):
        response = self.url_open('/ap/login', data={
            'dni_nie': '8765 4321-z',
            'csrf_token': self._get_login_csrf_token(),
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn('Horario AP', response.text)
        self.assertIn('AP Portal HTTP', response.text)

    def test_login_unknown_dni_shows_generic_error(self):
        response = self.url_open('/ap/login', data={
            'dni_nie': 'NOEXISTE',
            'csrf_token': self._get_login_csrf_token(),
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn('No se ha encontrado ningun AP', response.text)

    def test_manager_schedule_pages_render_for_internal_manager(self):
        self._login_internal_manager()

        index_response = self.url_open('/consultar-horario')
        self.assertEqual(index_response.status_code, 200)
        self.assertIn('APs', index_response.text)
        self.assertIn('AP Portal HTTP', index_response.text)

        schedule_response = self.url_open(f'/consultar-horario/ap/{self.worker.id}')
        self.assertEqual(schedule_response.status_code, 200)
        self.assertIn('Horario AP', schedule_response.text)
        self.assertIn('Usuario HTTP', schedule_response.text)
        self.assertIn('Vacaciones', schedule_response.text)
