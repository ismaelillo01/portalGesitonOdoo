# -*- coding: utf-8 -*-
from datetime import datetime, time, timedelta

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('-at_install', 'post_install')
class TestPortalAPMobileService(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service = cls.env['portal.ap.service'].sudo()
        cls.ap_service = cls.env.ref('usuarios.usuarios_servicio_ap')
        cls.zone = cls.env['zonastrabajo.zona'].create({
            'name': 'Zona Mobile AP',
            'code': 'ZONA_MOBILE_AP',
        })
        cls.worker = cls.env['trabajadores.trabajador'].create({
            'name': 'AP Mobile',
            'apellido1': 'Prueba',
            'dni_nie': '32165498P',
            'grupo': 'agusto',
            'zona_trabajo_ids': [(6, 0, [cls.zone.id])],
        })
        cls.usuario = cls.env['usuarios.usuario'].create({
            'name': 'Usuario Mobile',
            'apellido1': 'Uno',
            'direccion': 'Calle Mobile 1',
            'grupo': 'agusto',
            'zona_trabajo_id': cls.zone.id,
            'servicio_ids': [(6, 0, [cls.ap_service.id])],
        })
        cls.other_user = cls.env['usuarios.usuario'].create({
            'name': 'Usuario Mobile',
            'apellido1': 'Dos',
            'grupo': 'agusto',
            'zona_trabajo_id': cls.zone.id,
            'servicio_ids': [(6, 0, [cls.ap_service.id])],
        })
        cls.usuario._ensure_portal_ap_qr_token()
        cls.other_user._ensure_portal_ap_qr_token()
        cls.assignment = cls.env['portalgestor.asignacion'].create({
            'usuario_id': cls.usuario.id,
            'fecha': fields.Date.today() + timedelta(days=1),
            'confirmado': True,
        })
        cls.line = cls.env['portalgestor.asignacion.linea'].create({
            'asignacion_id': cls.assignment.id,
            'hora_inicio': 8.0,
            'hora_fin': 10.0,
            'trabajador_id': cls.worker.id,
        })

    def _login(self):
        response = self.service._mobile_login('3216-5498p', device_id='test-device', device_label='Android Test')
        self.assertTrue(response['ok'])
        self.assertTrue(response['session_token'])
        return response['session_token']

    def _line_datetime(self, hour, minute):
        return datetime.combine(fields.Date.to_date(self.line.fecha), time(hour, minute))

    def test_mobile_login_normalizes_dni(self):
        token = self._login()
        session = self.env['portal.ap.mobile.session'].search([('token', '=', token)])
        self.assertEqual(session.trabajador_id, self.worker)
        self.assertEqual(session.device_id, 'test-device')

    def test_mobile_schedule_returns_confirmed_user_qr_scope(self):
        token = self._login()
        month = fields.Date.to_string(self.assignment.fecha)[:7]
        response = self.service._mobile_schedule(token, month)

        self.assertTrue(response['ok'])
        self.assertEqual(len(response['shifts']), 1)
        self.assertEqual(response['shifts'][0]['id'], self.line.id)
        self.assertEqual(response['shifts'][0]['usuario']['id'], self.usuario.id)
        self.assertEqual(response['shifts'][0]['status'], 'pending')

    def test_mobile_check_accepts_qr_for_assignment_user(self):
        token = self._login()
        response = self.service._mobile_check(token, {
            'assignment_line_id': self.line.id,
            'qr_token': self.usuario.portal_ap_qr_token,
            'event_type': 'in',
            'client_event_id': 'event-valid-1',
            'client_datetime': '2026-05-18T10:00:00+02:00',
        })

        self.assertTrue(response['ok'])
        self.assertIn(response['fichaje']['state'], ('valid', 'warning'))
        self.assertEqual(response['fichaje']['event_type'], 'in')

    def test_mobile_check_rejects_qr_from_other_user(self):
        token = self._login()
        response = self.service._mobile_check(token, {
            'assignment_line_id': self.line.id,
            'qr_token': self.other_user.portal_ap_qr_token,
            'event_type': 'in',
            'client_event_id': 'event-rejected-1',
        })

        self.assertFalse(response['ok'])
        self.assertEqual(response['fichaje']['state'], 'rejected')
        self.assertIn('QR', response['error']['message'])

    def test_mobile_time_warning_allows_five_minutes_tolerance(self):
        self.assertFalse(self.service._mobile_time_warning(self.line, self._line_datetime(7, 55)))
        self.assertFalse(self.service._mobile_time_warning(self.line, self._line_datetime(10, 5)))
        self.assertTrue(self.service._mobile_time_warning(self.line, self._line_datetime(7, 54)))
        self.assertTrue(self.service._mobile_time_warning(self.line, self._line_datetime(10, 6)))

    def test_mobile_sync_uses_offline_client_datetime_for_tolerance(self):
        token = self._login()
        planned_date = fields.Date.to_date(self.line.fecha)
        valid_event = {
            'assignment_line_id': self.line.id,
            'qr_token': self.usuario.portal_ap_qr_token,
            'event_type': 'in',
            'client_event_id': 'event-offline-valid-tolerance',
            'client_datetime': '%sT07:55:00+00:00' % planned_date.isoformat(),
            'origin': 'offline',
        }
        warning_event = dict(valid_event, **{
            'client_event_id': 'event-offline-warning-tolerance',
            'client_datetime': '%sT07:54:00+00:00' % planned_date.isoformat(),
        })

        service = self.service.with_context(tz='UTC')
        valid_response = service._mobile_sync(token, [valid_event])
        warning_response = service._mobile_sync(token, [warning_event])

        self.assertTrue(valid_response['ok'])
        self.assertEqual(valid_response['results'][0]['fichaje']['state'], 'valid')
        self.assertTrue(warning_response['ok'])
        self.assertEqual(warning_response['results'][0]['fichaje']['state'], 'warning')
        self.assertIn('rango horario', warning_response['results'][0]['fichaje']['incidence'])

    def test_mobile_sync_is_idempotent_by_client_event_id(self):
        token = self._login()
        event = {
            'assignment_line_id': self.line.id,
            'qr_token': self.usuario.portal_ap_qr_token,
            'event_type': 'out',
            'client_event_id': 'event-offline-1',
            'origin': 'offline',
        }

        first = self.service._mobile_sync(token, [event])
        second = self.service._mobile_sync(token, [event])

        self.assertTrue(first['ok'])
        self.assertTrue(second['ok'])
        checks = self.env['portal.ap.fichaje'].search([('client_event_id', '=', 'event-offline-1')])
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks.origin, 'offline')
